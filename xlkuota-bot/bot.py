# ================== IMPORTS ==================
import os
import random
import datetime

from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, ADMIN_CHAT_ID, MIN_TOPUP, QRIS_IMAGE_PATH
from db import SessionLocal, migrate_ppob_add_kategori
from models import Member, Topup, Report, MessageLog, XLDorItem, PPOBItem, Transaction


# ================== HELPER: MAIN MENU ==================
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["XL Dor", "PPOB"],
            ["Cek Saldo", "Top Up Saldo"],
            ["Lapor Masalah", "Hubungi Admin"],
        ],
        resize_keyboard=True,
    )


# ================== STATE MACHINE ==================
STATE_NONE = "none"
STATE_LAPOR_BUG = "lapor_bug"
STATE_HUBUNGI_ADMIN = "hubungi_admin"
STATE_INPUT_NOMOR_XLDOR = "input_nomor_xldor"


# ================== HELPER: VALIDASI NOMOR ==================
def is_valid_phone(number: str) -> bool:
    number = number.replace(" ", "").replace("+", "")
    return number.isdigit() and 9 <= len(number) <= 15


# ================== HELPER: AUTO TAG REPORT ==================
def auto_tag_report(text: str) -> str:
    t = text.lower()

    if any(k in t for k in ["crash", "traceback", "error", "bug"]):
        return "BUG"

    if any(k in t for k in ["saran", "suggest", "ide", "fitur", "usulan"]):
        return "SUGGESTION"

    if any(k in t for k in ["gagal", "tidak bisa", "masalah", "trouble"]):
        return "ERROR"

    return "INFO"


# ================== HELPER: MEMBER ==================
def get_or_create_member(session, tg_user):
    member = session.query(Member).filter_by(telegram_id=str(tg_user.id)).first()
    if not member:
        member = Member(
            telegram_id=str(tg_user.id),
            username=tg_user.username or str(tg_user.id),
            verified=False,
            saldo=0,
            transaksi=0,
        )
        session.add(member)
        session.commit()
    return member


# ================== HELPER: BUKTI TOPUP IMAGE ==================
def generate_bukti_topup_image(trx_code, username, telegram_id):
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    draw.text((50, 50), "BUKTI TRANSAKSI TOP-UP", fill="black", font=font)
    draw.text((50, 150), f"ID Transaksi : {trx_code}", fill="black", font=font)
    draw.text((50, 200), f"User        : {username}", fill="black", font=font)
    draw.text((50, 250), f"Telegram ID : {telegram_id}", fill="black", font=font)
    draw.text((50, 350), "Silakan verifikasi apakah bukti transfer valid.", fill="black", font=font)
    draw.text((50, 420), "SanStore", fill="gray", font=font)

    path = f"/tmp/bukti_{trx_code}.png"
    img.save(path)
    return path


# ================== MENU UTAMA (INLINE) ==================
async def menu_utama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📱 PPOB", callback_data="menu_ppob")],
            [InlineKeyboardButton("📦 XL Dor", callback_data="menu_xldor")],
        ]
    )

    if query:
        await query.answer()
        await query.edit_message_text("📲 Silakan pilih menu:", reply_markup=keyboard)
    else:
        await update.message.reply_text("📲 Silakan pilih menu:", reply_markup=keyboard)


# ================== MENU PPOB (KATEGORI LANGSUNG) ==================
async def menu_ppob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query:
        await query.answer()
        sender = query.message
    else:
        sender = update.message

    session = SessionLocal()
    try:
        kategori_list = session.query(PPOBItem.kategori).filter(PPOBItem.aktif == True).distinct().all()
    finally:
        session.close()

    if not kategori_list:
        await sender.reply_text("❌ Tidak ada kategori PPOB tersedia.")
        return

    keyboard = [
        [InlineKeyboardButton(k[0], callback_data=f"ppobcat_{k[0]}")]
        for k in kategori_list
    ]

    await sender.reply_text(
        "📱 Silakan pilih kategori PPOB:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ================== PPOB: KATEGORI → ITEM ==================
async def callback_ppob_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    kategori = query.data.replace("ppobcat_", "")

    session = SessionLocal()
    try:
        items = (
            session.query(PPOBItem)
            .filter_by(kategori=kategori, aktif=True)
            .order_by(PPOBItem.harga.asc())
            .all()
        )
    finally:
        session.close()

    if not items:
        await query.edit_message_text(f"❌ Tidak ada item di kategori *{kategori}*.", parse_mode="Markdown")
        return

    keyboard = [
        [
            InlineKeyboardButton(
                f"{item.nama_item} - Rp{int(item.harga):,}",
                callback_data=f"ppobitem_{item.id}",
            )
        ]
        for item in items
    ]

    await query.edit_message_text(
        f"📂 PPOB: *{kategori}*\nPilih item:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ================== PPOB: ITEM DETAIL ==================
async def callback_ppob_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = query.data.replace("ppobitem_", "")

    session = SessionLocal()
    try:
        item = session.query(PPOBItem).filter_by(id=item_id, aktif=True).first()
    finally:
        session.close()

    if not item:
        await query.edit_message_text("❌ Item PPOB tidak ditemukan.")
        return

    text = (
        f"📦 *{item.nama_item}*\n"
        f"💰 Harga: Rp{int(item.harga):,}\n"
        f"📝 {item.deskripsi}\n"
        f"⏳ Masa Aktif: {item.masa_aktif} Hari\n"
        f"📂 Kategori: {item.kategori}\n"
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Beli Sekarang", callback_data=f"ppobbeli_{item.id}")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data=f"ppobcat_{item.kategori}")],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ================== PPOB: KONFIRMASI BELI ==================
async def callback_ppob_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = query.data.replace("ppobbeli_", "")

    session = SessionLocal()
    try:
        item = session.query(PPOBItem).filter_by(id=item_id, aktif=True).first()
    finally:
        session.close()

    if not item:
        await query.edit_message_text("❌ Item PPOB tidak ditemukan.")
        return

    text = (
        f"🛒 *Konfirmasi Pembelian PPOB*\n\n"
        f"📦 {item.nama_item}\n"
        f"💰 Harga: Rp{int(item.harga):,}\n\n"
        f"Jika setuju, admin akan memproses pembelian."
    )

    keyboard = [
        [InlineKeyboardButton("✔️ Setuju", callback_data=f"ppobconfirm_{item.id}")],
        [InlineKeyboardButton("❌ Batal", callback_data=f"ppobcat_{item.kategori}")],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ================== PPOB: BUAT TRANSAKSI + TIKET ADMIN ==================
async def callback_ppob_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = query.data.replace("ppobconfirm_", "")

    session = SessionLocal()
    try:
        item = session.query(PPOBItem).filter_by(id=item_id, aktif=True).first()
        if not item:
            await query.edit_message_text("❌ Item PPOB tidak ditemukan.")
            return

        user = query.from_user

        trx = Transaction(
            user_id=str(user.id),
            jenis="PPOB",
            item_nama=item.nama_item,
            item_id=item.id,
            harga=item.harga,
            status="pending",
        )
        session.add(trx)
        session.commit()
        trx_id = trx.id
    finally:
        session.close()

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            f"📩 *Tiket Pembelian PPOB*\n\n"
            f"🧾 ID: {trx_id}\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📦 Item: {item.nama_item}\n"
            f"💰 Harga: Rp{int(item.harga):,}\n\n"
            f"Pilih aksi:"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✔ Approve", callback_data=f"adminapprove_{trx_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"adminreject_{trx_id}"),
                ]
            ]
        ),
        parse_mode="Markdown",
    )

    await query.edit_message_text(
        "🎉 Permintaan pembelian PPOB sudah dikirim ke admin.\nStatus: *pending*.",
        parse_mode="Markdown",
    )
    # ================== MENU XL DOR (KATEGORI) ==================
async def menu_xldor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query:
        await query.answer()
        sender = query.message
    else:
        sender = update.message

    session = SessionLocal()
    try:
        kategori_list = (
            session.query(XLDorItem.kategori)
            .filter(XLDorItem.aktif == True)
            .distinct()
            .all()
        )
    finally:
        session.close()

    if not kategori_list:
        await sender.reply_text("❌ Tidak ada kategori XL Dor tersedia.")
        return

    keyboard = [
        [InlineKeyboardButton(k[0], callback_data=f"xldorcat_{k[0]}")]
        for k in kategori_list
    ]

    await sender.reply_text(
        "📦 Silakan pilih kategori XL Dor:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ================== XL DOR: KATEGORI → ITEM ==================
async def callback_xldor_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    kategori = query.data.replace("xldorcat_", "")

    session = SessionLocal()
    try:
        items = (
            session.query(XLDorItem)
            .filter_by(kategori=kategori, aktif=True)
            .order_by(XLDorItem.harga.asc())
            .all()
        )
    finally:
        session.close()

    if not items:
        await query.edit_message_text(
            f"❌ Tidak ada item untuk kategori *{kategori}*.",
            parse_mode="Markdown",
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                f"{item.nama_item} - Rp{int(item.harga):,}",
                callback_data=f"xldoritem_{item.id}",
            )
        ]
        for item in items
    ]

    await query.edit_message_text(
        f"📦 XL Dor: *{kategori}*\nPilih paket:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ================== XL DOR: ITEM DETAIL ==================
async def callback_xldor_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = query.data.replace("xldoritem_", "")

    session = SessionLocal()
    try:
        item = session.query(XLDorItem).filter_by(id=item_id, aktif=True).first()
    finally:
        session.close()

    if not item:
        await query.edit_message_text("❌ Item XL Dor tidak ditemukan.")
        return

    text = (
        f"📦 *{item.nama_item}*\n"
        f"💰 Harga: Rp{int(item.harga):,}\n"
        f"📝 {item.deskripsi}\n"
        f"⏳ Masa Aktif: {item.masa_aktif} Hari\n"
        f"📂 Kategori: {item.kategori}\n"
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Beli Sekarang", callback_data=f"xldorbeli_{item.id}")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data=f"xldorcat_{item.kategori}")],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


# ================== XL DOR: BELI → INPUT NOMOR ==================
async def callback_xldor_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = query.data.replace("xldorbeli_", "")

    context.user_data["xldor_item"] = item_id
    context.user_data["state"] = STATE_INPUT_NOMOR_XLDOR

    await query.edit_message_text("📱 Masukkan nomor tujuan XL Dor:")


# ================== XL DOR: PROSES NOMOR ==================
async def proses_xldor_nomor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nomor = update.message.text.strip()

    if not is_valid_phone(nomor):
        await update.message.reply_text("❌ Nomor tidak valid. Masukkan nomor yang benar.")
        return

    item_id = context.user_data.get("xldor_item")

    session = SessionLocal()
    try:
        item = session.query(XLDorItem).filter_by(id=item_id, aktif=True).first()
    finally:
        session.close()

    if not item:
        await update.message.reply_text("❌ Item XL Dor tidak ditemukan.")
        return

    text = (
        f"🛒 *Konfirmasi Pembelian XL Dor*\n\n"
        f"📱 Nomor: {nomor}\n"
        f"📦 {item.nama_item}\n"
        f"💰 Harga: Rp{int(item.harga):,}\n\n"
        f"Jika setuju, admin akan memproses pembelian."
    )

    keyboard = [
        [InlineKeyboardButton("✔️ Setuju", callback_data=f"xldorconfirm_{item.id}")],
        [InlineKeyboardButton("❌ Batal", callback_data=f"xldorcat_{item.kategori}")],
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

    context.user_data["state"] = STATE_NONE


# ================== XL DOR: BUAT TRANSAKSI + TIKET ADMIN ==================
async def callback_xldor_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = query.data.replace("xldorconfirm_", "")

    session = SessionLocal()
    try:
        item = session.query(XLDorItem).filter_by(id=item_id, aktif=True).first()
        if not item:
            await query.edit_message_text("❌ Item XL Dor tidak ditemukan.")
            return

        user = query.from_user

        trx = Transaction(
            user_id=str(user.id),
            jenis="XLDOR",
            item_nama=item.nama_item,
            item_id=item.id,
            harga=item.harga,
            status="pending",
        )
        session.add(trx)
        session.commit()
        trx_id = trx.id
    finally:
        session.close()

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            f"📩 *Tiket Pembelian XL Dor*\n\n"
            f"🧾 ID: {trx_id}\n"
            f"👤 User: {user.full_name} (ID: {user.id})\n"
            f"📦 Item: {item.nama_item}\n"
            f"💰 Harga: Rp{int(item.harga):,}\n\n"
            f"Pilih aksi:"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✔ Approve", callback_data=f"adminapprove_{trx_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"adminreject_{trx_id}"),
                ]
            ]
        ),
        parse_mode="Markdown",
    )

    await query.edit_message_text(
        "🎉 Permintaan pembelian XL Dor sudah dikirim ke admin.\nStatus: *pending*.",
        parse_mode="Markdown",
    )
# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = STATE_NONE
    context.user_data["topup_mode"] = False

    query = update.callback_query

    if query:
        await query.answer()
        sender = query.message
    else:
        sender = update.message

    await sender.reply_text(
        "📲 Silakan pilih menu:",
        reply_markup=main_menu_keyboard()
    )


# ================== HANDLE TEXT (VERSI CLEAN) ==================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip()
    tg_user = update.effective_user
    user_id = str(tg_user.id)

    session = SessionLocal()
    member = get_or_create_member(session, tg_user)

    state = context.user_data.get("state", STATE_NONE)

    # ---------- STATE: INPUT NOMOR XL DOR ----------
    if state == STATE_INPUT_NOMOR_XLDOR:
        await proses_xldor_nomor(update, context)
        return

    # ---------- STATE: LAPOR BUG ----------
    if state == STATE_LAPOR_BUG:
        tag = auto_tag_report(text)

        report = Report(
            user_id=user_id,
            pesan=text,
            tag=tag
        )
        session.add(report)
        session.commit()

        await update.message.reply_text("📩 Laporan kamu sudah dikirim ke admin.")
        context.user_data["state"] = STATE_NONE
        return

    # ---------- STATE: HUBUNGI ADMIN ----------
    if state == STATE_HUBUNGI_ADMIN:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📨 Pesan dari user {tg_user.full_name}:\n\n{text}"
        )
        await update.message.reply_text("📩 Pesan kamu sudah dikirim ke admin.")
        context.user_data["state"] = STATE_NONE
        return

    # ---------- MENU TEKS ----------
    if text.lower() == "xl dor":
        await menu_xldor(update, context)
        return

    if text.lower() == "ppob":
        await menu_ppob(update, context)
        return

    if text.lower() == "lapor masalah":
        context.user_data["state"] = STATE_LAPOR_BUG
        await update.message.reply_text("📝 Silakan tulis laporan kamu.")
        return

    if text.lower() == "hubungi admin":
        context.user_data["state"] = STATE_HUBUNGI_ADMIN
        await update.message.reply_text("✉️ Tulis pesan untuk admin.")
        return

    if text.lower() == "cek saldo":
        await update.message.reply_text(
            f"💵 Saldo kamu: Rp{int(member.saldo):,}"
        )
        return

    if text.lower() == "top up saldo":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu.")
            return

        await update.message.reply_text(
            f"💰 *Top Up Saldo*\nMinimal: Rp{MIN_TOPUP:,}\n\n"
            "Silakan transfer ke QRIS berikut lalu kirim bukti foto.",
            parse_mode="Markdown"
        )

        if os.path.exists(QRIS_IMAGE_PATH):
            with open(QRIS_IMAGE_PATH, "rb") as f:
                await context.bot.send_photo(
                    chat_id=tg_user.id,
                    photo=f,
                    caption="🔶 Scan QRIS ini."
                )
        else:
            await update.message.reply_text("⚠️ QRIS tidak ditemukan.")

        context.user_data["topup_mode"] = True
        return

    # ---------- LOGIN ----------
    if text.lower() == "login":
        total_member = session.query(Member).count()

        if member.verified:
            await update.message.reply_text(
                "*Dashboard Member:*\n"
                f"🪪 Username: {member.username}\n"
                f"💵 Saldo: Rp{int(member.saldo):,}\n"
                f"📊 Transaksi: {member.transaksi}\n"
                f"💲 Minimal Top-Up: Rp{MIN_TOPUP:,}\n"
                f"👁️ Jumlah Member: {total_member}",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
            return

        otp = str(random.randint(100000, 999999))
        member.otp = otp
        member.otp_created_at = datetime.datetime.utcnow()
        session.commit()

        await context.bot.send_message(
            chat_id=tg_user.id,
            text=f"🔐 OTP kamu: {otp}\nBerlaku 1 menit."
        )

        await update.message.reply_text("📩 OTP dikirim ke DM.")
        return

    # ---------- OTP VALIDASI ----------
    if text.isdigit() and not member.verified:
        if member.otp == text:
            now = datetime.datetime.utcnow()

            if member.otp_created_at and (now - member.otp_created_at).total_seconds() <= 60:
                member.verified = True
                member.otp = None
                member.otp_created_at = None
                session.commit()

                total_member = session.query(Member).count()

                await update.message.reply_text(
                    "✅ Login berhasil!\n\n"
                    "*Dashboard Member:*\n"
                    f"🪪 Username: {member.username}\n"
                    f"💵 Saldo: Rp{int(member.saldo):,}\n"
                    f"📊 Transaksi: {member.transaksi}\n"
                    f"💲 Minimal Top-Up: Rp{MIN_TOPUP:,}\n"
                    f"👁️ Jumlah Member: {total_member}",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
                return

            member.otp = None
            member.otp_created_at = None
            session.commit()

            await update.message.reply_text(
                "⏰ OTP kadaluarsa. Klik *Login* untuk minta ulang.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text(
            "❌ OTP salah atau kadaluarsa.",
            parse_mode="Markdown"
        )
        return

    # ---------- DEFAULT ----------
    await update.message.reply_text("❓ Perintah tidak dikenali. Silakan pilih menu.")
    session.close()


# ================== HANDLE FOTO (TOP-UP) ==================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    if not context.user_data.get("topup_mode", False):
        await update.message.reply_text("❌ Kamu tidak sedang melakukan top-up.")
        session.close()
        return

    trx_code = f"TOPUP-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"

    bukti_path = generate_bukti_topup_image(
        trx_code,
        member.username,
        member.telegram_id
    )

    topup = Topup(
        member_id=member.id,
        trx_code=trx_code,
        status="pending"
    )
    session.add(topup)
    session.commit()
    session.close()

    if os.path.exists(bukti_path):
        with open(bukti_path, "rb") as f:
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=f,
                caption=(
                    "📥 *Bukti Transaksi Top-Up Baru*\n"
                    f"ID: `{trx_code}`\n"
                    f"User: {member.username} (ID: {member.telegram_id})\n\n"
                    "Gunakan:\n"
                    f"/approve_topup {trx_code} <jumlah>\n"
                    f"/reject_topup {trx_code}"
                ),
                parse_mode="Markdown"
            )

    await update.message.reply_text(
        "📨 Bukti transfer sudah dikirim ke admin.\nMohon tunggu verifikasi.",
        parse_mode="Markdown"
    )

    context.user_data["topup_mode"] = False
# ================== ADMIN: APPROVE TRANSAKSI (PPOB & XL DOR) ==================
async def adminapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Hanya admin
    if query.from_user.id != ADMIN_CHAT_ID:
        return

    trx_id = query.data.replace("adminapprove_", "")

    session = SessionLocal()
    try:
        trx = session.query(Transaction).filter_by(id=trx_id).first()

        if not trx or trx.status != "pending":
            await query.edit_message_text("❌ Transaksi tidak ditemukan / bukan pending.")
            return

        trx.status = "success"
        trx.keterangan = "Disetujui admin"
        session.commit()

        # Beri tahu user
        await context.bot.send_message(
            chat_id=int(trx.user_id),
            text=(
                f"🎉 Transaksi {trx.jenis} *{trx.item_nama}* berhasil diproses!\n"
                f"Status: Sukses."
            ),
            parse_mode="Markdown"
        )

        # Balas admin
        await query.edit_message_text(f"✅ Transaksi {trx_id} berhasil di-approve.")

    finally:
        session.close()


# ================== ADMIN: REJECT TRANSAKSI (PPOB & XL DOR) ==================
async def adminreject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Hanya admin
    if query.from_user.id != ADMIN_CHAT_ID:
        return

    trx_id = query.data.replace("adminreject_", "")

    session = SessionLocal()
    try:
        trx = session.query(Transaction).filter_by(id=trx_id).first()

        if not trx or trx.status != "pending":
            await query.edit_message_text("❌ Transaksi tidak ditemukan / bukan pending.")
            return

        trx.status = "gagal"
        trx.keterangan = "Ditolak admin"
        session.commit()

        # Beri tahu user
        try:
            await context.bot.send_message(
                chat_id=int(trx.user_id),
                text=(
                    f"❌ Transaksi {trx.jenis} *{trx.item_nama}* ditolak admin.\n"
                    f"Silakan pilih paket lain."
                ),
                parse_mode="Markdown"
            )
        except:
            pass

        # Balas admin
        await query.edit_message_text(f"❌ Transaksi {trx_id} ditolak.")

    finally:
        session.close()


# ================== ADMIN: APPROVE TOPUP ==================
async def approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 3:
        await update.message.reply_text("Format: /approve_topup <TRX_CODE> <jumlah>")
        session.close()
        return

    _, trx_code, amount_str = args

    try:
        amount = float(amount_str)
    except ValueError:
        await update.message.reply_text("Jumlah tidak valid.")
        session.close()
        return

    topup = session.query(Topup).filter_by(trx_code=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        session.close()
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        session.close()
        return

    member = session.query(Member).filter_by(id=topup.member_id).first()
    if not member:
        await update.message.reply_text("Member tidak ditemukan.")
        session.close()
        return

    member.saldo += amount
    member.transaksi += 1

    topup.amount = amount
    topup.status = "success"
    topup.verified_at = datetime.datetime.utcnow()

    session.commit()
    session.close()

    await update.message.reply_text(
        f"✅ Top-up {trx_code} sebesar Rp{int(amount):,} berhasil diverifikasi."
    )

    await context.bot.send_message(
        chat_id=int(member.telegram_id),
        text=f"🎉 Top-up Rp{int(amount):,} berhasil! Saldo kamu sekarang Rp{int(member.saldo):,}"
    )


# ================== ADMIN: REJECT TOPUP ==================
async def reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.reply_text("Format: /reject_topup <TRX_CODE>")
        session.close()
        return

    _, trx_code = args

    topup = session.query(Topup).filter_by(trx_code=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        session.close()
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        session.close()
        return

    topup.status = "gagal"
    topup.verified_at = datetime.datetime.utcnow()
    session.commit()
    session.close()

    await update.message.reply_text(f"❌ Top-up {trx_code} ditolak admin.")


# ================== ADMIN: RIWAYAT TRANSAKSI ==================
async def riwayat_transaksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    try:
        trx_list = (
            session.query(Transaction)
            .order_by(Transaction.id.desc())
            .limit(20)
            .all()
        )
    finally:
        session.close()

    if not trx_list:
        await update.message.reply_text("Tidak ada transaksi.")
        return

    text = "📜 *Riwayat Transaksi Terbaru:*\n\n"

    for trx in trx_list:
        text += (
            f"🧾 ID: {trx.id}\n"
            f"👤 User: {trx.user_id}\n"
            f"📦 {trx.jenis} - {trx.item_nama}\n"
            f"💰 Rp{int(trx.harga):,}\n"
            f"📌 Status: {trx.status}\n"
            f"──────────────\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# ================== ADMIN: BROADCAST ==================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    members = session.query(Member).all()
    session.close()

    pesan = update.message.text.replace("/broadcast", "").strip()

    if not pesan:
        await update.message.reply_text("Format: /broadcast <pesan>")
        return

    count = 0
    for m in members:
        try:
            await context.bot.send_message(chat_id=int(m.telegram_id), text=pesan)
            count += 1
        except:
            pass

    await update.message.reply_text(f"📢 Broadcast terkirim ke {count} member.")
# ================== HANDLER REGISTRATION ==================

def main():
    migrate_ppob_add_kategori()  # jika kamu pakai migrasi kategori PPOB

    application = Application.builder().token(BOT_TOKEN).build()

    # ---------- COMMANDS ----------
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve_topup", approve_topup))
    application.add_handler(CommandHandler("reject_topup", reject_topup))
    application.add_handler(CommandHandler("riwayat", riwayat_transaksi))
    application.add_handler(CommandHandler("broadcast", broadcast))

    # ---------- CALLBACKS ----------
    application.add_handler(CallbackQueryHandler(menu_ppob, pattern="^menu_ppob$"))
    application.add_handler(CallbackQueryHandler(menu_xldor, pattern="^menu_xldor$"))

    # PPOB
    application.add_handler(CallbackQueryHandler(callback_ppob_main, pattern="^ppobcat_"))
    application.add_handler(CallbackQueryHandler(callback_ppob_item, pattern="^ppobitem_"))
    application.add_handler(CallbackQueryHandler(callback_ppob_beli, pattern="^ppobbeli_"))
    application.add_handler(CallbackQueryHandler(callback_ppob_confirm, pattern="^ppobconfirm_"))

    # XL Dor
    application.add_handler(CallbackQueryHandler(callback_xldor_kategori, pattern="^xldorcat_"))
    application.add_handler(CallbackQueryHandler(callback_xldor_item, pattern="^xldoritem_"))
    application.add_handler(CallbackQueryHandler(callback_xldor_beli, pattern="^xldorbeli_"))
    application.add_handler(CallbackQueryHandler(callback_xldor_confirm, pattern="^xldorconfirm_"))

    # Admin approve/reject transaksi
    application.add_handler(CallbackQueryHandler(adminapprove, pattern="^adminapprove_"))
    application.add_handler(CallbackQueryHandler(adminreject, pattern="^adminreject_"))

    # ---------- MESSAGE HANDLERS ----------
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # ---------- RUN BOT ----------
    application.run_polling()


# ================== JALANKAN BOT ==================
if __name__ == "__main__":
    main()