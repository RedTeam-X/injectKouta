from models import Member, Topup, Purchase, Report, MessageLog, XLDorItem, PPOBItem
import os
import random
import datetime

from db import SessionLocal, migrate_ppob_add_kategori

from telegram import Update, ReplyKeyboardMarkup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from PIL import Image, ImageDraw, ImageFont

from config import BOT_TOKEN, ADMIN_CHAT_ID, MIN_TOPUP, QRIS_IMAGE_PATH

# ================== STATE MACHINE ==================

STATE_NONE = "none"
STATE_PILIH_KATEGORI = "pilih_kategori"
STATE_PILIH_ITEM = "pilih_item"
STATE_MINTA_NOMOR = "minta_nomor"
STATE_LAPOR_BUG = "lapor_bug"
STATE_HUBUNGI_ADMIN = "hubungi_admin"

# ================== MENU UTAMA ==================

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["XL Dor", "Login", "PPOB"],
            ["Top Up", "Lapor Masalah", "Hubungi Admin"],
            ["Tutorial Login", "Tutorial Top Up"]
        ],
        resize_keyboard=True
    )

# # ================== MENU XL DOR (KATEGORI) ==================
async def menu_xldor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("XTRA DIGITAL", callback_data="xldorcat_XTRA"),
            InlineKeyboardButton("FLEX MAXX", callback_data="xldorcat_FLEX")
        ],
        [
            InlineKeyboardButton("AKRAB", callback_data="xldorcat_AKRAB")
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📦 Silakan pilih kategori XL Dor:",
        reply_markup=reply_markup
    )
    
# ================== PPOB MENU ==================
async def menu_ppob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Axis", callback_data="ppobmain_Axis"),
            InlineKeyboardButton("Indosat", callback_data="ppobmain_Indosat")
        ],
        [
            InlineKeyboardButton("Telkomsel", callback_data="ppobmain_Telkomsel"),
            InlineKeyboardButton("Masa Aktif", callback_data="ppobmain_MasaAktif")
        ],
        [
            InlineKeyboardButton("XL Dor", callback_data="ppobmain_XLDor")
        ]
    ]

    await update.message.reply_text(
        "📦 Silakan pilih kategori PPOB:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================== PPOB MAIN CATEGORY CALLBACK ==================
async def callback_ppob_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    kategori = query.data.split("_")[1]

    subkategori_map = {
        "Axis": ["AXIS GAME", "Mini YouTube & Sosmed", "Sosmed & Chat", "Kuota Nasional Harian"],
        "Indosat": ["Freedom U", "Freedom Internet Lokal"],
        "Telkomsel": ["Combo Data", "Ilmupedia"],
        "MasaAktif": ["Telkomsel", "XL", "Indosat", "Axis"],
        "XLDor": ["XTRA DIGITAL", "FLEX MAXX", "AKRAB"]
    }

    if kategori not in subkategori_map:
        await query.edit_message_text("❌ Kategori tidak ditemukan.")
        return

    keyboard = []
    for sub in subkategori_map[kategori]:
        keyboard.append([
            InlineKeyboardButton(
                text=sub,
                callback_data=f"ppobsub_{kategori}_{sub}"
            )
        ])

    await query.edit_message_text(
        f"📦 PPOB: {kategori}\nPilih sub‑kategori:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================== PPOB SUB CATEGORY CALLBACK ==================
async def callback_ppob_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, kategori, subkategori = query.data.split("_")

    session = SessionLocal()
    items = session.query(PPOBItem).filter_by(
        kategori=f"{kategori} - {subkategori}",
        aktif=True
    ).all()

    if not items:
        await query.edit_message_text(f"❌ Tidak ada item untuk {subkategori}.")
        return

    keyboard = []
    for item in items:
        keyboard.append([
            InlineKeyboardButton(
                text=f"{item.deskripsi} - Rp{int(item.harga)}",
                callback_data=f"ppobitem_{item.id}"
            )
        ])

    await query.edit_message_text(
        f"📦 PPOB: {kategori} → {subkategori}\nPilih item:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================== PPOB ITEM CALLBACK ==================
async def callback_ppob_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.split("_")[1])

    session = SessionLocal()
    item = session.query(PPOBItem).filter_by(id=item_id).first()

    if not item:
        await query.edit_message_text("❌ Item tidak ditemukan.")
        return

    text = (
        f"📦 *{item.deskripsi}*\n"
        f"💰 Harga: Rp {int(item.harga)}\n"
        f"⏳ Masa Aktif: {item.masa_aktif} Hari\n\n"
        f"Masukkan nomor tujuan untuk pembelian."
    )

    await query.edit_message_text(text, parse_mode="Markdown")

    context.user_data["ppob_item"] = item_id
    context.user_data["state"] = "input_nomor_ppob"
    
# ================== CALLBACK KATEGORI XL DOR ==================
async def callback_xldor_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    kategori = query.data.split("_")[1]

    session = SessionLocal()

    if kategori == "XTRA":
        items = session.query(XLDorItem).filter(
            XLDorItem.deskripsi.ilike("%Xtra%"), 
            XLDorItem.aktif == True
        ).all()

    elif kategori == "FLEX":
        items = session.query(XLDorItem).filter(
            XLDorItem.deskripsi.ilike("%Flex Max%"),
            XLDorItem.aktif == True
        ).all()

    elif kategori == "AKRAB":
        items = session.query(XLDorItem).filter(
            XLDorItem.deskripsi.ilike("%VIP%"),
            XLDorItem.aktif == True
        ).all()

    else:
        await query.edit_message_text("❌ Kategori tidak ditemukan.")
        return

    keyboard = []
    for item in items:
        keyboard.append([
            InlineKeyboardButton(
                text=f"{item.deskripsi} - Rp{int(item.harga)}",
                callback_data=f"xldoritem_{item.id}"
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📦 XL Dor: {kategori}\nPilih paket:",
        reply_markup=reply_markup
    )
# ================== CALLBACK ITEM XL DOR ==================
async def callback_xldor_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.split("_")[1])

    session = SessionLocal()
    item = session.query(XLDorItem).filter_by(id=item_id).first()

    text = (
        f"📦 *{item.deskripsi}*\n"
        f"💰 Harga: Rp {int(item.harga)}\n"
        f"⏳ Masa Aktif: {item.masa_aktif} Hari\n\n"
        f"Masukkan nomor tujuan untuk pembelian."
    )

    await query.edit_message_text(text, parse_mode="Markdown")

    context.user_data["xldor_item"] = item_id
    context.user_data["state"] = "input_nomor_xldor"

# ================== UTIL & HELPER ==================

def get_or_create_member(session, tg_user):
    member = session.query(Member).filter_by(telegram_id=str(tg_user.id)).first()
    if not member:
        member = Member(
            telegram_id=str(tg_user.id),
            username=tg_user.username or str(tg_user.id),
            verified=False,
            saldo=0,
            transaksi=0
        )
        session.add(member)
        session.commit()
    return member

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

    path = f"bukti_{trx_code}.png"
    img.save(path)
    return path

def is_valid_phone(number: str) -> bool:
    return number.isdigit() and 10 <= len(number) <= 15

def auto_tag_report(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["bug", "error", "crash", "traceback"]):
        return "BUG"
    if any(k in t for k in ["saran", "suggest", "ide", "fitur"]):
        return "SUGGESTION"
    if any(k in t for k in ["gagal", "tidak bisa", "masalah", "trouble"]):
        return "ERROR"
    return "BUG"
    # ================== START ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = STATE_NONE
    context.user_data["topup_mode"] = False

    await update.message.reply_text(
        "📲 Silakan pilih menu:",
        reply_markup=main_menu_keyboard()
    )


# ================== HANDLE TEXT ==================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # WAJIB: buat session dan ambil member
    session = SessionLocal()
    member = session.query(Member).filter_by(
        telegram_id=str(update.effective_user.id)
    ).first()

    if text == "XL Dor":
        await menu_xldor(update, context)
    # tambahkan menu lain sesuai kebutuhan...

# ---------- STATE: LAPOR BUG ----------
    if context.user_data.get("state") == STATE_LAPOR_BUG:
        laporan = text
        kategori = auto_tag_report(laporan)

        report = Report(
            member_id=member.id,
            category=kategori,
            message=laporan,
            created_at=datetime.datetime.utcnow()
        )
        session.add(report)
        session.commit()

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "🐞 *Laporan Baru dari User*\n"
                f"Kategori: {kategori}\n"
                f"User: {member.username} (ID: {member.telegram_id})\n\n"
                f"Isi laporan:\n{laporan}"
            ),
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            "✅ Laporan kamu sudah dikirim ke admin.",
            reply_markup=main_menu_keyboard()
        )

        context.user_data["state"] = STATE_NONE
        return

    # ---------- STATE: HUBUNGI ADMIN ----------
    if context.user_data.get("state") == STATE_HUBUNGI_ADMIN:
        pesan = text

        msg_log = MessageLog(
            sender_id=str(member.telegram_id),
            receiver_id=str(ADMIN_CHAT_ID),
            message=pesan,
            direction="user_to_admin",
            created_at=datetime.datetime.utcnow()
        )
        session.add(msg_log)
        session.commit()

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "📩 *Pesan Baru dari User*\n"
                f"User: {member.username} (ID: {member.telegram_id})\n\n"
                f"Pesan:\n{pesan}\n\n"
                f"Balas dengan format:\n"
                f"/balas {member.telegram_id} <pesan>"
            ),
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            "📨 Pesan kamu sudah dikirim ke admin.",
            reply_markup=main_menu_keyboard()
        )

        context.user_data["state"] = STATE_NONE
        return

    # ---------- STATE: MINTA NOMOR TUJUAN ----------
    if context.user_data.get("state") == STATE_MINTA_NOMOR:
        nomor = text

        if not is_valid_phone(nomor):
            await update.message.reply_text("❌ Format nomor tidak valid.")
            return

        item = context.user_data.get("item_dipilih")
        if not item:
            await update.message.reply_text("❌ Item tidak ditemukan.")
            context.user_data["state"] = STATE_NONE
            return

        nama, harga = item

        if member.saldo < harga:
            await update.message.reply_text(
                f"❌ Saldo tidak cukup.\nSaldo kamu: Rp{int(member.saldo)}\nHarga: Rp{harga}"
            )
            context.user_data["state"] = STATE_NONE
            context.user_data["item_dipilih"] = None
            return

        trx_code = f"BUY-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"

        pembelian = Purchase(
            member_id=member.id,
            trx_code=trx_code,
            product_name=nama,
            price=harga,
            status="pending"
        )
        session.add(pembelian)
        session.commit()

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                "🧾 *Transaksi Pembelian Baru*\n"
                f"ID: `{trx_code}`\n"
                f"User: {member.username} (ID: {member.telegram_id})\n"
                f"Produk: {nama}\n"
                f"Harga: Rp{harga}\n"
                f"Nomor Tujuan: {nomor}\n\n"
                f"/approve_beli {trx_code}\n"
                f"/reject_beli {trx_code}"
            ),
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            f"📨 Permintaan pembelian dikirim ke admin.",
            reply_markup=main_menu_keyboard()
        )

        context.user_data["state"] = STATE_NONE
        context.user_data["item_dipilih"] = None
        return

    # ---------- STATE: PILIH KATEGORI ----------
    if context.user_data.get("state") == STATE_PILIH_KATEGORI:
        if text in PRODUCTS:
            items = PRODUCTS[text]
            item_buttons = [[p[0]] for p in items]

            reply = ReplyKeyboardMarkup(
                item_buttons + [["⬅️ Kembali"]],
                resize_keyboard=True
            )

            context.user_data["kategori"] = text
            context.user_data["state"] = STATE_PILIH_ITEM

            await update.message.reply_text(
                f"📄 List item {text}:",
                reply_markup=reply
            )
            return

        if text == "⬅️ Kembali":
            context.user_data["state"] = STATE_NONE
            await update.message.reply_text(
                "📲 Silakan pilih menu:",
                reply_markup=main_menu_keyboard()
            )
            return

        await update.message.reply_text("❌ Kategori tidak dikenal.")
        return

    # ---------- STATE: PILIH ITEM ----------
    if context.user_data.get("state") == STATE_PILIH_ITEM:
        kategori = context.user_data.get("kategori")

        if text == "⬅️ Kembali":
            kategori_buttons = [[k] for k in PRODUCTS.keys()]
            reply = ReplyKeyboardMarkup(
                kategori_buttons + [["⬅️ Kembali"]],
                resize_keyboard=True
            )

            context.user_data["state"] = STATE_PILIH_KATEGORI

            await update.message.reply_text(
                "📦 Pilih kategori produk XL:",
                reply_markup=reply
            )
            return

        if kategori in PRODUCTS:
            for nama, harga in PRODUCTS[kategori]:
                if nama == text:
                    context.user_data["item_dipilih"] = (nama, harga)
                    context.user_data["state"] = STATE_MINTA_NOMOR

                    await update.message.reply_text(
                        "📱 Masukkan nomor XL tujuan:"
                    )
                    return

        await update.message.reply_text("❌ Item tidak ditemukan.")
        return

    # ================== MENU UTAMA ==================

    # ---------- LAPOR MASALAH ----------
    if text == "Lapor Masalah":
        context.user_data["state"] = STATE_LAPOR_BUG
        await update.message.reply_text("📝 Tulis laporan kamu.")
        return

    # ---------- HUBUNGI ADMIN ----------
    if text == "Hubungi Admin":
        context.user_data["state"] = STATE_HUBUNGI_ADMIN
        await update.message.reply_text("📨 Tulis pesan untuk admin.")
        return

    # ---------- TUTORIAL LOGIN ----------
    if text == "Tutorial Login":
        await update.message.reply_text(
            "📘 *Tutorial Login*\n"
            "1. Tekan *Login*\n"
            "2. Bot kirim OTP ke DM\n"
            "3. Masukkan OTP dalam 1 menit\n"
            "4. Selesai",
            parse_mode="Markdown"
        )
        return

    # ---------- TUTORIAL TOP UP ----------
    if text == "Tutorial Top Up":
        await update.message.reply_text(
            "📘 *Tutorial Top Up*\n"
            "1. Tekan *Top Up*\n"
            "2. Scan QRIS\n"
            "3. Transfer\n"
            "4. Kirim foto bukti\n"
            "5. Admin verifikasi",
            parse_mode="Markdown"
        )
        return

    # ---------- XL DOR ----------
    if text == "XL Dor":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu.")
            return

        kategori_buttons = [[k] for k in PRODUCTS.keys()]
        reply = ReplyKeyboardMarkup(
            kategori_buttons + [["⬅️ Kembali"]],
            resize_keyboard=True
        )

        context.user_data["state"] = STATE_PILIH_KATEGORI

        await update.message.reply_text(
            "📦 Pilih kategori produk:",
            reply_markup=reply
        )
        return

    # ---------- LOGIN ----------
    if text == "Login":
        total_member = session.query(Member).count()

        if member.verified:
            await update.message.reply_text(
                "*Dashboard Member:*\n"
                f"🪪 Username: {member.username}\n"
                f"💵 Saldo: Rp{int(member.saldo)}\n"
                f"📊 Transaksi: {member.transaksi}\n"
                f"💲 Minimal Top-Up: Rp{MIN_TOPUP}\n"
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

    # ---------- PPOB ----------
    if text == "PPOB":
        await update.message.reply_text("⚠️ Menu PPOB masih *Coming Soon*.")
        return

    # ---------- TOP UP ----------
    if text == "Top Up":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu.")
            return

        await update.message.reply_text(
            f"💰 *Top Up Saldo*\nMinimal: Rp{MIN_TOPUP}\n\n"
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

    # ---------- OTP VALIDASI ----------
    if text.isdigit() and member.otp == text and not member.verified:
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
                f"💵 Saldo: Rp{int(member.saldo)}\n"
                f"📊 Transaksi: {member.transaksi}\n"
                f"💲 Minimal Top-Up: Rp{MIN_TOPUP}\n"
                f"👁️ Jumlah Member: {total_member}",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            member.otp = None
            member.otp_created_at = None
            session.commit()

            await update.message.reply_text(
                "⏰ OTP kadaluarsa. Klik *Login* untuk minta ulang.",
                parse_mode="Markdown"
            )
        return

    if text.isdigit() and not member.verified:
        await update.message.reply_text(
            "❌ OTP salah atau kadaluarsa.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "Perintah tidak dikenal.",
        reply_markup=main_menu_keyboard()
    )
    # ================== HANDLE FOTO (BUKTI TOPUP) ==================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    # User tidak sedang top-up
    if not context.user_data.get("topup_mode", False):
        await update.message.reply_text("❌ Kamu tidak sedang melakukan top-up.")
        return

    # Generate kode transaksi
    trx_code = f"TOPUP-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"

    # Generate gambar bukti untuk admin
    bukti_path = generate_bukti_topup_image(
        trx_code,
        member.username,
        member.telegram_id
    )

    # Simpan transaksi ke database
    topup = Topup(
        member_id=member.id,
        trx_code=trx_code,
        status="pending"
    )
    session.add(topup)
    session.commit()

    # Kirim ke admin
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

    # Balas ke user
    await update.message.reply_text(
        "📨 Bukti transfer sudah dikirim ke admin.\nMohon tunggu verifikasi.",
        parse_mode="Markdown"
    )

    # Reset mode top-up
    context.user_data["topup_mode"] = False
    # ================== ADMIN: VERIFIKASI TOPUP ==================

async def approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 3:
        await update.message.reply_text("Format: /approve_topup <TRX_CODE> <jumlah>")
        return

    _, trx_code, amount_str = args

    try:
        amount = float(amount_str)
    except ValueError:
        await update.message.reply_text("Jumlah tidak valid.")
        return

    topup = session.query(Topup).filter_by(trx_code=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    member = session.query(Member).filter_by(id=topup.member_id).first()
    if not member:
        await update.message.reply_text("Member tidak ditemukan.")
        return

    # Update saldo
    member.saldo += amount
    member.transaksi += 1
    topup.amount = amount
    topup.status = "success"
    topup.verified_at = datetime.datetime.utcnow()
    session.commit()

    await update.message.reply_text(
        f"✅ Top-up {trx_code} sebesar Rp{int(amount)} berhasil diverifikasi."
    )

    await context.bot.send_message(
        chat_id=int(member.telegram_id),
        text=f"🎉 Top-up Rp{int(amount)} berhasil! Saldo kamu sekarang Rp{int(member.saldo)}"
    )


async def reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.reply_text("Format: /reject_topup <TRX_CODE>")
        return

    _, trx_code = args

    topup = session.query(Topup).filter_by(trx_code=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    # ✅ Indentasi harus sejajar dengan baris di atas
    topup.status = "rejected"
    topup.verified_at = datetime.datetime.utcnow()
    session.commit()

    member = session.query(Member).filter_by(id=topup.member_id).first()
    if member:
        await context.bot.send_message(
            chat_id=int(member.telegram_id),
            text=f"❌ Top-up {trx_code} ditolak admin. Saldo kamu tidak berubah."
        )

    await update.message.reply_text(f"❌ Top-up {trx_code} ditolak.")

    await update.message.reply_text(f"❌ Top-up {trx_code} ditolak.")
    # ================== ADMIN: VERIFIKASI TOPUP ==================

async def approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 3:
        await update.message.reply_text("Format: /approve_topup <TRX_CODE> <jumlah>")
        return

    _, trx_code, amount_str = args

    try:
        amount = float(amount_str)
    except ValueError:
        await update.message.reply_text("Jumlah tidak valid.")
        return

    topup = session.query(Topup).filter_by(trx_code=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    member = session.query(Member).filter_by(id=topup.member_id).first()
    if not member:
        await update.message.reply_text("Member tidak ditemukan.")
        return

    # Update saldo
    member.saldo += amount
    member.transaksi += 1
    topup.amount = amount
    topup.status = "success"
    topup.verified_at = datetime.datetime.utcnow()
    session.commit()

    await update.message.reply_text(
        f"✅ Top-up {trx_code} sebesar Rp{int(amount)} berhasil diverifikasi."
    )

    await context.bot.send_message(
        chat_id=int(member.telegram_id),
        text=f"🎉 Top-up Rp{int(amount)} berhasil! Saldo kamu sekarang Rp{int(member.saldo)}"
    )


async def reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.reply_text("Format: /reject_topup <TRX_CODE>")
        return

    _, trx_code = args

    topup = session.query(Topup).filter_by(trx_code=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    topup.status = "rejected"
    topup.verified_at = datetime.datetime.utcnow()
    session.commit()

    member = session.query(Member).filter_by(id=topup.member_id).first()
    if member:
        await context.bot.send_message(
            chat_id=int(member.telegram_id),
            text=f"❌ Top-up {trx_code} ditolak admin. Saldo kamu tidak berubah."
        )

    await update.message.reply_text(f"❌ Top-up {trx_code} ditolak.")
    # ================== ADMIN: VERIFIKASI PEMBELIAN ==================

async def approve_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.reply_text("Format: /approve_beli <TRX_CODE>")
        return

    _, trx_code = args

    pembelian = session.query(Purchase).filter_by(trx_code=trx_code).first()
    if not pembelian:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if pembelian.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    member = session.query(Member).filter_by(id=pembelian.member_id).first()
    if not member:
        await update.message.reply_text("Member tidak ditemukan.")
        return

    # Cek saldo saat verifikasi
    if member.saldo < pembelian.price:
        pembelian.status = "rejected"
        pembelian.verified_at = datetime.datetime.utcnow()
        session.commit()

        await update.message.reply_text("Saldo user tidak cukup saat verifikasi.")

        await context.bot.send_message(
            chat_id=int(member.telegram_id),
            text=f"❌ Pembelian {pembelian.product_name} dibatalkan karena saldo tidak cukup."
        )
        return

    # Potong saldo
    member.saldo -= pembelian.price
    member.transaksi += 1
    pembelian.status = "success"
    pembelian.verified_at = datetime.datetime.utcnow()
    session.commit()

    await update.message.reply_text(
        f"✅ Pembelian {trx_code} disetujui. Saldo user dipotong Rp{int(pembelian.price)}."
    )

    await context.bot.send_message(
        chat_id=int(member.telegram_id),
        text=(
            f"🎉 Pembelian {pembelian.product_name} berhasil!\n"
            f"Saldo terpotong Rp{int(pembelian.price)}.\n"
            f"Saldo sekarang: Rp{int(member.saldo)}"
        )
    )


async def reject_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.reply_text("Format: /reject_beli <TRX_CODE>")
        return

    _, trx_code = args

    pembelian = session.query(Purchase).filter_by(trx_code=trx_code).first()
    if not pembelian:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if pembelian.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    pembelian.status = "rejected"
    pembelian.verified_at = datetime.datetime.utcnow()
    session.commit()

    member = session.query(Member).filter_by(id=pembelian.member_id).first()
    if member:
        await context.bot.send_message(
            chat_id=int(member.telegram_id),
            text=f"❌ Pembelian {pembelian.product_name} ditolak admin."
        )

    await update.message.reply_text(f"❌ Pembelian {trx_code} ditolak.")
  # ================== ADMIN: BALAS USER ==================
async def balas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split(" ", 3)

    if len(args) < 3:
        await update.message.reply_text(
            "Format: /balas <telegram_id> <pesan> atau /balas <telegram_id> <kirim_gambar> <pesan>"
        )
        return

    _, user_id, mode_or_pesan, *rest = args

    # Mode kirim gambar
    if mode_or_pesan.lower() == "kirim_gambar":
        if len(rest) < 1:
            await update.message.reply_text("Format: /balas <telegram_id> <kirim_gambar> <pesan>")
            return

        pesan = rest[0]

        # Simpan log pesan
        msg_log = MessageLog(
            sender_id=str(ADMIN_CHAT_ID),
            receiver_id=str(user_id),
            message=f"[GAMBAR] {pesan}",
            direction="admin_to_user",
            created_at=datetime.datetime.utcnow()
        )
        session.add(msg_log)
        session.commit()

        # Kirim gambar + pesan
        await context.bot.send_photo(
            chat_id=int(user_id),
            photo=open("qris.png", "rb"),  # contoh gambar statis
            caption=f"📬 Balasan dari Admin:\n{pesan}",
            parse_mode="Markdown"
        )

        await update.message.reply_text(f"✅ Gambar + pesan terkirim ke user {user_id}.")
        return

    # Mode pesan teks biasa
    pesan = mode_or_pesan if not rest else mode_or_pesan + " " + " ".join(rest)

    msg_log = MessageLog(
        sender_id=str(ADMIN_CHAT_ID),
        receiver_id=str(user_id),
        message=pesan,
        direction="admin_to_user",
        created_at=datetime.datetime.utcnow()
    )
    session.add(msg_log)
    session.commit()

    await context.bot.send_message(
        chat_id=int(user_id),
        text=f"📬 Balasan dari Admin:\n{pesan}",
        parse_mode="Markdown"
    )

    await update.message.reply_text("✅ Pesan teks terkirim ke user.")


# ================== ADMIN: UPDATE DATA (MULTI-LINE FINAL) ==================
async def update_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    message = update.message.text.strip()

    # Pisahkan pesan menjadi banyak baris
    lines = message.split("\n")

    results = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Hanya proses baris yang dimulai dengan /update
        if not line.startswith("/update"):
            continue

        import shlex
        try:
            args = shlex.split(line)
        except:
            results.append(f"❌ Gagal parsing: {line}")
            continue

        if len(args) < 2:
            results.append(f"❌ Format salah: {line}")
            continue

        mode = args[1].lower()

        # ==========================
        # PPOB UPDATE
        # ==========================
        if mode == "ppob":
            if len(args) < 8:
                results.append(
                    f"❌ Format PPOB salah:\n{line}\n"
                    "Contoh:\n"
                    '/update ppob AXIS_Game_05GB_7H 5049 "Kuota Game 0.5GB, 7 Hari" 7 "Axis - AXIS GAME" aktif'
                )
                continue

            nama_item = args[2]
            harga = args[3]
            deskripsi = args[4]
            masa_aktif = args[5]
            kategori = args[6]
            status = args[7].lower()

            try:
                harga = int(harga)
                masa_aktif = int(masa_aktif)
            except:
                results.append(f"❌ Harga/masa aktif harus angka: {line}")
                continue

            aktif = True if status == "aktif" else False

            item = session.query(PPOBItem).filter_by(nama_item=nama_item).first()

            if item:
                item.harga = harga
                item.deskripsi = deskripsi
                item.masa_aktif = masa_aktif
                item.kategori = kategori
                item.aktif = aktif
                results.append(f"✔ Update PPOB: {nama_item}")
            else:
                new_item = PPOBItem(
                    nama_item=nama_item,
                    harga=harga,
                    deskripsi=deskripsi,
                    masa_aktif=masa_aktif,
                    kategori=kategori,
                    aktif=aktif
                )
                session.add(new_item)
                results.append(f"➕ Tambah PPOB: {nama_item}")

            continue

        # ==========================
        # UPDATE SALDO USER
        # ==========================
        if mode == "saldo":
            if len(args) < 4:
                results.append(f"❌ Format saldo salah: {line}")
                continue

            user_id = args[2]
            jumlah = args[3]

            try:
                jumlah = int(jumlah)
            except:
                results.append(f"❌ Jumlah saldo harus angka: {line}")
                continue

            member = session.query(Member).filter_by(telegram_id=str(user_id)).first()
            if member:
                saldo_awal = member.saldo
                member.saldo += jumlah
                results.append(f"✔ Saldo {user_id}: {saldo_awal} → {member.saldo}")
            else:
                results.append(f"❌ User tidak ditemukan: {user_id}")

            continue

        # ==========================
        # UPDATE XL DOR
        # ==========================
        if mode == "xldor":
            if len(args) < 7:
                results.append(f"❌ Format XL Dor salah: {line}")
                continue

            nama_item = args[2]
            harga = args[3]
            deskripsi = args[4]
            masa_aktif = args[5]
            status = args[6].lower()

            try:
                harga = int(harga)
                masa_aktif = int(masa_aktif)
            except:
                results.append(f"❌ Harga/masa aktif harus angka: {line}")
                continue

            aktif = True if status == "aktif" else False

            item = session.query(XLDorItem).filter_by(nama_item=nama_item).first()

            if item:
                item.harga = harga
                item.deskripsi = deskripsi
                item.masa_aktif = masa_aktif
                item.aktif = aktif
                results.append(f"✔ Update XL Dor: {nama_item}")
            else:
                new_item = XLDorItem(
                    nama_item=nama_item,
                    harga=harga,
                    deskripsi=deskripsi,
                    masa_aktif=masa_aktif,
                    aktif=aktif
                )
                session.add(new_item)
                results.append(f"➕ Tambah XL Dor: {nama_item}")

            continue

        # ==========================
        # MODE TIDAK DIKENAL
        # ==========================
        results.append(f"❌ Mode tidak dikenal: {line}")

    session.commit()
    session.close()

    await update.message.reply_text("\n".join(results))
    
# ================== BULK UPDATE XL DOR ==================
async def bulk_update_xldor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    text = update.message.text

    # Pisahkan setiap baris, abaikan baris pertama "/bulk_update_xldor"
    lines = text.split("\n")[1:]

    success = []
    failed = []

    for line in lines:
        try:
            parts = line.strip().split()
            if len(parts) < 6:
                failed.append(f"❌ Format salah: {line}")
                continue

            nama_item = parts[0]
            harga = int(parts[1])

            # Ambil deskripsi di dalam tanda kutip
            if '"' in line:
                deskripsi = line.split('"')[1]
            else:
                failed.append(f"❌ Deskripsi tidak ditemukan: {line}")
                continue

            # Ambil masa aktif dan status dari bagian akhir
            tail = line.strip().split()[-2:]
            masa_aktif = int(tail[0])
            status = tail[1].lower()

            item = session.query(XLDorItem).filter_by(nama_item=nama_item).first()
            if item:
                item.harga = harga
                item.deskripsi = deskripsi
                item.masa_aktif = masa_aktif
                item.aktif = True if status == "aktif" else False
            else:
                item = XLDorItem(
                    nama_item=nama_item,
                    harga=harga,
                    deskripsi=deskripsi,
                    masa_aktif=masa_aktif,
                    aktif=True if status == "aktif" else False
                )
                session.add(item)

            session.commit()
            success.append(f"✅ {nama_item}")
        except Exception as e:
            failed.append(f"❌ {line} → {str(e)}")

    result = "📦 Hasil Bulk Update XL Dor:\n\n"
    if success:
        result += "✅ Berhasil disimpan:\n" + "\n".join(success) + "\n\n"
    if failed:
        result += "❌ Gagal diproses:\n" + "\n".join(failed)

    await update.message.reply_text(result)
            
    # ================== ADMIN: BROADCAST ==================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()

    # Format: /broadcast <pesan>
    args = update.message.text.split(" ", 1)
    if len(args) < 2:
        await update.message.reply_text("Format: /broadcast <pesan>")
        return

    pesan = args[1]
    members = session.query(Member).all()

    sukses = 0
    gagal = 0

    for m in members:
        try:
            await context.bot.send_message(
                chat_id=int(m.telegram_id),
                text=pesan
            )
            sukses += 1
        except:
            gagal += 1

    await update.message.reply_text(
        f"📢 Broadcast selesai.\n"
        f"Berhasil: {sukses}\n"
        f"Gagal: {gagal}"
    )
    # ================== MAIN ==================
def main():
    migrate_ppob_add_kategori()   # WAJIB DI SINI

    application = Application.builder().token(BOT_TOKEN).build()

    # ================== HANDLER COMMAND ==================
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balas", balas))
    application.add_handler(CommandHandler("update", update_data))
    application.add_handler(CommandHandler("bulk_update_xldor", bulk_update_xldor))
    application.add_handler(CommandHandler("approve_topup", approve_topup))
    application.add_handler(CommandHandler("reject_topup", reject_topup))
    application.add_handler(CommandHandler("approve_beli", approve_beli))
    application.add_handler(CommandHandler("reject_beli", reject_beli))
    application.add_handler(CommandHandler("xldor", menu_xldor))

    # ================== HANDLER PPOB ==================
    application.add_handler(CommandHandler("ppob", menu_ppob))
    application.add_handler(CallbackQueryHandler(callback_ppob_main, pattern="^ppobmain_"))
    application.add_handler(CallbackQueryHandler(callback_ppob_sub, pattern="^ppobsub_"))
    application.add_handler(CallbackQueryHandler(callback_ppob_item, pattern="^ppobitem_"))
    application.add_handler(CallbackQueryHandler(callback_xldor_kategori, pattern="^xldorcat_"))
    application.add_handler(CallbackQueryHandler(callback_xldor_item, pattern="^xldoritem_"))

    # ================== HANDLER MESSAGE ==================
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # ================== JALANKAN BOT ==================
    application.run_polling()


if __name__ == "__main__":
    main()
