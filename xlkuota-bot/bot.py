import os
import random
import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from PIL import Image, ImageDraw, ImageFont

from config import BOT_TOKEN, ADMIN_CHAT_ID, MIN_TOPUP, QRIS_IMAGE_PATH
from db import SessionLocal
from models import Member, Topup, Purchase, Report, MessageLog

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

# ================== DATA PRODUK ==================

PRODUCTS = {
    "XL XTRA DIGITAL": [
        ("XL XTRA KOUTA CONF 2GB, 1HR", 5000),
        ("XL XTRA KOUTA YT 2GB, 3HR", 7000),
        ("XL XTRA KOUTA YT 3GB, 7HR", 10000),
        ("XL XTRA KOUTA INSTAGRAM 3GB, 7HR", 10000),
        ("XL XTRA KOUTA INSTAGRAM 2GB, 30HR", 11000),
        ("XL XTRA KOUTA FACEBOOK 2GB, 30HR", 11000),
        ("XL XTRA KOUTA MIDNIGHT 5GB, 30HR", 12000),
        ("XL XTRA KOUTA FILM 5GB, 30HR", 12000),
        ("XL XTRA KOUTA 30GB, 30HR", 12000)
    ],
    "XL FLEX MAXX": [
        ("XL DATA FLEX MAX 33GB, 14HR", 49000),
        ("XL DATA FLEX MAX 75GB, 14HR", 72000),
        ("XL DATA FLEX MAX 50GB, 28HR", 86000)
    ],
    "XL AKRAB": [
        ("XTRA COMBO VIP 5GB+10GB YT+20mnt", 66000),
        ("XTRA COMBO VIP 10GB+20GB YT+30mnt", 94000),
        ("XTRA COMBO VIP 15GB+30GB YT+40mnt", 131000)
    ]
}

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
    session = SessionLocal()
    text = (update.message.text or "").strip()
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)
    state = context.user_data.get("state", STATE_NONE)

    # ---------- STATE: LAPOR BUG ----------
    if state == STATE_LAPOR_BUG:
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
    if state == STATE_HUBUNGI_ADMIN:
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
    if state == STATE_MINTA_NOMOR:
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
    if state == STATE_PILIH_KATEGORI:
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
    if state == STATE_PILIH_ITEM:
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


# ================== ADMIN: UPDATE DATA ==================
async def update_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Format: /update <saldo|ppob|xldor> ...")
        return

    mode = args[0].lower()
    session = SessionLocal()

    if mode == "saldo":
        if len(args) < 3:
            await update.message.reply_text("Format: /update saldo <id_user> <jumlah>")
            return
        user_id, jumlah = args[1], int(args[2])
        member = session.query(Member).filter_by(telegram_id=str(user_id)).first()
        if member:
            saldo_awal = member.saldo
            member.saldo += jumlah
            session.commit()
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"🎉 Saldo kamu bertambah Rp{jumlah}!\nSaldo awal: Rp{saldo_awal}\nSaldo sekarang: Rp{member.saldo}"
            )
            await update.message.reply_text(f"✅ Saldo user {user_id} berhasil diupdate.")
        else:
            await update.message.reply_text("❌ User tidak ditemukan.")

    elif mode == "ppob":
        if len(args) < 6:
            await update.message.reply_text("Format: /update ppob <nama_item> <harga> <deskripsi> <masa_aktif> <status>")
            return
        _, nama_item, harga, deskripsi, masa_aktif, status = args
        item = session.query(PPOBItem).filter_by(nama_item=nama_item).first()
        if item:
            item.harga = int(harga)
            item.deskripsi = deskripsi
            item.masa_aktif = int(masa_aktif)
            item.aktif = True if status.lower() == "aktif" else False
            session.commit()
            await update.message.reply_text(f"✅ Item PPOB '{nama_item}' berhasil diupdate.")
        else:
            await update.message.reply_text(f"❌ Item PPOB '{nama_item}' tidak ditemukan.")

    elif mode == "xldor":
        if len(args) < 6:
            await update.message.reply_text("Format: /update xldor <nama_item> <harga> <deskripsi> <masa_aktif> <status>")
            return
        _, nama_item, harga, deskripsi, masa_aktif, status = args
        item = session.query(XLDorItem).filter_by(nama_item=nama_item).first()
        if item:
            item.harga = int(harga)
            item.deskripsi = deskripsi
            item.masa_aktif = int(masa_aktif)
            item.aktif = True if status.lower() == "aktif" else False
            session.commit()
            await update.message.reply_text(f"✅ Item XL Dor '{nama_item}' berhasil diupdate.")
        else:
            await update.message.reply_text(f"❌ Item XL Dor '{nama_item}' tidak ditemukan.")

    else:
        await update.message.reply_text("❌ Mode update tidak dikenal.")

# ================== ADMIN: BULK UPDATE XL DOR ==================
async def bulk_update_xldor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    text = update.message.text.split("\n")[1:]  # skip command line
    current_item = None

    for line in text:
        line = line.strip()
        if not line:
            continue

        if line.lower().startswith("harga:"):
            harga = int(line.replace("Harga: Rp", "").replace(".", "").strip())
            if current_item:
                item = session.query(XLDorItem).filter_by(nama_item=current_item).first()
                if item:
                    item.harga = harga
                    session.commit()
                    await update.message.reply_text(f"✅ {current_item} diupdate ke Rp.{harga}")
                else:
                    new_item = XLDorItem(nama_item=current_item, harga=harga, aktif=True)
                    session.add(new_item)
                    session.commit()
                    await update.message.reply_text(f"✅ {current_item} ditambahkan dengan harga Rp.{harga}")
                current_item = None
        else:
            current_item = line
            
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
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ===== COMMAND HANDLERS =====
    application.add_handler(CommandHandler("balas", balas))
    application.add_handler(CommandHandler("update", update_data))
    application.add_handler(CommandHandler("bulk_update_xldor", bulk_update_xldor)).  
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve_topup", approve_topup))
    app.add_handler(CommandHandler("reject_topup", reject_topup))
    app.add_handler(CommandHandler("approve_beli", approve_beli))
    app.add_handler(CommandHandler("reject_beli", reject_beli))
    app.add_handler(CommandHandler("balas", balas))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # ===== MESSAGE HANDLERS =====
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # ===== RUN BOT =====
    app.run_polling()


if __name__ == "__main__":
    main()
