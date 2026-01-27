from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import random
import datetime
import os
from PIL import Image, ImageDraw, ImageFont

from config import BOT_TOKEN, ADMIN_CHAT_ID, MIN_TOPUP, QRIS_IMAGE_PATH
from db import SessionLocal
from models import Member, Topup, Purchase

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

# ================== MENU UTAMA ==================

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [["XL Dor", "Login", "PPOB"], ["Top Up"]],
        resize_keyboard=True
    )

# ================== HELPER DB ===================

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

# ================== GENERATE GAMBAR BUKTI ===================

def generate_bukti_topup_image(trx_code, username, telegram_id):
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    font = ImageFont.load_default()

    draw.text((50, 50), "BUKTI TRANSAKSI TOP-UP", fill="black", font=font)
    draw.text((50, 150), f"ID Transaksi : {trx_code}", fill="black", font=font)
    draw.text((50, 200), f"User : {username}", fill="black", font=font)
    draw.text((50, 250), f"Telegram ID : {telegram_id}", fill="black", font=font)
    draw.text((50, 350), "Silakan verifikasi apakah bukti transfer valid.", fill="black", font=font)

    path = f"bukti_{trx_code}.png"
    img.save(path)
    return path

# ================== START ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📲 Silakan pilih menu:",
        reply_markup=main_menu_keyboard()
    )

# ================== HANDLE TEKS ===================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    text = update.message.text
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)
    state = context.user_data.get("state")

    # ---------- STATE: MINTA NOMOR ----------
    if state == "minta_nomor":
        nomor = text.strip()

        if not nomor.isdigit() or len(nomor) < 10:
            await update.message.reply_text("❌ Format nomor tidak valid. Masukkan nomor XL yang benar.")
            return

        nama, harga = context.user_data.get("item_dipilih", (None, None))

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
                "Setelah kuota dikirim ke nomor tujuan, gunakan:\n"
                f"/approve_beli {trx_code}\n"
                f"/reject_beli {trx_code}"
            ),
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            f"📨 Permintaan pembelian dikirim ke admin.\nNomor tujuan: {nomor}",
            reply_markup=main_menu_keyboard()
        )

        context.user_data["state"] = None
        return

    # ---------- STATE: PILIH KATEGORI ----------
    if state == "pilih_kategori":
        if text in PRODUCTS:
            items = PRODUCTS[text]
            item_buttons = [[p[0]] for p in items]
            reply = ReplyKeyboardMarkup(item_buttons + [["⬅️ Kembali"]], resize_keyboard=True)

            context.user_data["kategori"] = text
            context.user_data["state"] = "pilih_item"

            await update.message.reply_text(f"📄 List item {text}:", reply_markup=reply)
            return

    # ---------- STATE: PILIH ITEM ----------
    if state == "pilih_item":
        kategori = context.user_data.get("kategori")

        if kategori in PRODUCTS:
            for nama, harga in PRODUCTS[kategori]:
                if nama == text:
                    context.user_data["item_dipilih"] = (nama, harga)
                    context.user_data["state"] = "minta_nomor"

                    await update.message.reply_text("📱 Masukkan nomor XL tujuan pengiriman kuota:")
                    return

    # ---------- LOGIN ----------
    if text == "Login":
        if member.verified:
            await update.message.reply_text(
                "📊 Dashboard Member:\n"
                f"- Username: {member.username}\n"
                f"- Saldo: Rp{int(member.saldo)}\n"
                f"- Transaksi: {member.transaksi}",
                reply_markup=main_menu_keyboard()
            )
            return

        otp = str(random.randint(100000, 999999))
        member.otp = otp
        member.otp_created_at = datetime.datetime.utcnow()
        session.commit()

        await context.bot.send_message(
            chat_id=tg_user.id,
            text=f"🔐 Kode OTP kamu: {otp}\nBerlaku 1 menit."
        )

        await update.message.reply_text("📩 OTP sudah dikirim ke DM kamu.")
        return

    # ---------- TOP UP ----------
    if text == "Top Up":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu.")
            return

        await update.message.reply_text(
            f"💰 *Top Up Saldo*\nMinimal: Rp{MIN_TOPUP}\nKirim bukti transfer berupa foto.",
            parse_mode="Markdown"
        )

        with open(QRIS_IMAGE_PATH, "rb") as f:
            await context.bot.send_photo(
                chat_id=tg_user.id,
                photo=f,
                caption="🔶 Scan QRIS ini untuk top-up saldo."
            )

        context.user_data["topup_mode"] = True
        return

    await update.message.reply_text("Gunakan menu tombol.")

# ================== HANDLE FOTO (BUKTI TOPUP) ===================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    if not context.user_data.get("topup_mode", False):
        await update.message.reply_text("❌ Kamu tidak sedang top-up.")
        return

    trx_code = f"TOPUP-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"

    # Buat gambar bukti transaksi
    bukti_path = generate_bukti_topup_image(trx_code, member.username, member.telegram_id)

    # Simpan transaksi
    topup = Topup(
        member_id=member.id,
        trx_code=trx_code,
        status="pending"
    )
    session.add(topup)
    session.commit()

    # Kirim gambar ke admin
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

    await update.message.reply_text("📨 Bukti transfer sudah dikirim ke admin.")

    context.user_data["topup_mode"] = False

# ================== ADMIN COMMANDS ===================
# (approve_topup, reject_topup, approve_beli, reject_beli)
# ——— (kode sama seperti versi sebelumnya, tidak dihapus)

# ================== MAIN ===================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
