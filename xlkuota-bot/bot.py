from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import random, datetime, os

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

# ================== START ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📲 Silakan pilih menu:",
        reply_markup=main_menu_keyboard()
    )

# ================== HANDLE TEKS / BUTTON ===================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    text = update.message.text
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    state = context.user_data.get("state")

    # ========== STATE: PILIH KATEGORI ==========
    if state == "pilih_kategori":
        if text in PRODUCTS:
            items = PRODUCTS[text]
            item_buttons = [[p[0]] for p in items]
            reply = ReplyKeyboardMarkup(item_buttons + [["⬅️ Kembali"]], resize_keyboard=True)

            context.user_data["kategori"] = text
            context.user_data["state"] = "pilih_item"

            await update.message.reply_text(f"📄 List item {text}:", reply_markup=reply)
            return

        if text == "⬅️ Kembali":
            await update.message.reply_text("📲 Silakan pilih menu:", reply_markup=main_menu_keyboard())
            context.user_data["state"] = None
            return

    # ========== STATE: PILIH ITEM ==========
    if state == "pilih_item":
        kategori = context.user_data.get("kategori")

        if text == "⬅️ Kembali":
            kategori_buttons = [[k] for k in PRODUCTS.keys()]
            reply = ReplyKeyboardMarkup(kategori_buttons + [["⬅️ Kembali"]], resize_keyboard=True)
            context.user_data["state"] = "pilih_kategori"
            await update.message.reply_text("📦 Pilih kategori produk XL:", reply_markup=reply)
            return

        # cari item
        if kategori in PRODUCTS:
            for nama, harga in PRODUCTS[kategori]:
                if nama == text:
                    # cek saldo cukup atau tidak
                    if member.saldo < harga:
                        await update.message.reply_text(
                            f"❌ Saldo tidak cukup.\nSaldo kamu: Rp{int(member.saldo)}\nHarga: Rp{harga}"
                        )
                        return

                    # saldo cukup → generate kode pembelian, TAPI saldo belum dipotong
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

                    # kirim bukti transaksi ke admin
                    await update.message.reply_text(
                        f"📨 Permintaan pembelian dikirim ke admin.\n"
                        f"Menunggu admin mengirimkan kuota dan verifikasi.",
                        reply_markup=main_menu_keyboard()
                    )

                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=(
                            f"🧾 *Transaksi Pembelian Baru*\n"
                            f"ID: `{trx_code}`\n"
                            f"User: {member.username} (ID: {member.telegram_id})\n"
                            f"Produk: {nama}\n"
                            f"Harga: Rp{harga}\n\n"
                            f"Setelah kuota dikirim ke user, gunakan:\n"
                            f"/approve_beli {trx_code}\n"
                            f"Jika batal, gunakan:\n"
                            f"/reject_beli {trx_code}"
                        ),
                        parse_mode="Markdown"
                    )

                    context.user_data["state"] = None
                    return

        await update.message.reply_text("❌ Item tidak ditemukan.")
        return

    # ========== XL DOR ==========
    if text == "XL Dor":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu sebelum membeli produk.")
            return

        kategori_buttons = [[k] for k in PRODUCTS.keys()]
        reply = ReplyKeyboardMarkup(kategori_buttons + [["⬅️ Kembali"]], resize_keyboard=True)

        await update.message.reply_text("📦 Pilih kategori produk XL:", reply_markup=reply)
        context.user_data["state"] = "pilih_kategori"
        return

    # ========== LOGIN ==========
    if text == "Login":
        if member.verified:
            await update.message.reply_text("✅ Kamu sudah login.", reply_markup=main_menu_keyboard())
            return

        otp = str(random.randint(100000, 999999))
        member.otp = otp
        session.commit()

        await context.bot.send_message(
            chat_id=tg_user.id,
            text=f"🔐 Kode OTP kamu: {otp}\nKirim kode ini di chat bot."
        )
        await update.message.reply_text("📩 OTP sudah dikirim ke akun Telegram kamu.")
        return

    # ========== PPOB ==========
    if text == "PPOB":
        await update.message.reply_text("⚠️ Menu PPOB masih *Coming Soon*.", parse_mode="Markdown")
        return

    # ========== TOP UP ==========
    if text == "Top Up":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu.")
            return

        await update.message.reply_text(
            f"💰 *Top Up Saldo*\nMinimal top-up: Rp{MIN_TOPUP}\n\n"
            "Silakan transfer ke QRIS berikut lalu kirim bukti transfer berupa foto.",
            parse_mode="Markdown"
        )

        if os.path.exists(QRIS_IMAGE_PATH):
            with open(QRIS_IMAGE_PATH, "rb") as f:
                await context.bot.send_photo(
                    chat_id=tg_user.id,
                    photo=f,
                    caption="🔶 Scan QRIS ini untuk top-up saldo."
                )
        else:
            await update.message.reply_text("⚠️ QRIS belum diset di server (file tidak ditemukan).")

        context.user_data["topup_mode"] = True
        return

    # ========== OTP VALIDASI ==========
    if text.isdigit() and member.otp == text and not member.verified:
        member.verified = True
        member.otp = None
        session.commit()

        await update.message.reply_text(
            f"✅ Login berhasil!\n\n"
            f"📊 Dashboard Member:\n"
            f"- Nama Akun: {member.username}\n"
            f"- Saldo: Rp{int(member.saldo)}\n"
            f"- Jumlah Transaksi: {member.transaksi}\n"
            f"- Minimal Top-Up: Rp{MIN_TOPUP}",
            reply_markup=main_menu_keyboard()
        )
        return

    if text.isdigit() and not member.verified:
        await update.message.reply_text(
            "❌ OTP salah atau kadaluarsa. Klik *Login* untuk minta ulang.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "Perintah tidak dikenal. Gunakan menu button.",
        reply_markup=main_menu_keyboard()
    )

# ================== HANDLE FOTO (BUKTI TOPUP) ===================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    if not context.user_data.get("topup_mode", False):
        await update.message.reply_text("❌ Kamu tidak sedang melakukan top-up.")
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    trx_code = f"TOPUP-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"

    topup = Topup(
        member_id=member.id,
        trx_code=trx_code,
        status="pending",
        bukti_file_id=file_id
    )
    session.add(topup)
    session.commit()

    context.user_data["topup_mode"] = False

    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=file_id,
        caption=(
            f"📥 *Transaksi Top-Up Baru*\n"
            f"ID: `{topup.trx_code}`\n"
            f"User: {member.username} (ID: {member.telegram_id})\n\n"
            f"Gunakan format:\n"
            f"/approve_topup {topup.trx_code} <jumlah>\n"
            f"contoh: /approve_topup {topup.trx_code} 50000\n"
            f"Untuk batal:\n"
            f"/reject_topup {topup.trx_code}"
        ),
        parse_mode="Markdown"
    )

    await update.message.reply_text(
        "📨 Bukti transfer sudah dikirim ke admin.\n"
        "Mohon tunggu verifikasi.",
        parse_mode="Markdown"
    )

# ================== ADMIN: VERIFIKASI TOPUP ===================

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

# ================== ADMIN: VERIFIKASI PEMBELIAN ===================

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

    # cek saldo lagi sebelum potong (jaga-jaga)
    if member.saldo < pembelian.price:
        pembelian.status = "rejected"
        pembelian.verified_at = datetime.datetime.utcnow()
        session.commit()
        await update.message.reply_text("Saldo user tidak cukup saat verifikasi. Transaksi dibatalkan.")
        await context.bot.send_message(
            chat_id=int(member.telegram_id),
            text=f"❌ Pembelian {pembelian.product_name} dibatalkan karena saldo tidak cukup saat verifikasi."
        )
        return

    # potong saldo saat admin approve
    member.saldo -= pembelian.price
    member.transaksi += 1
    pembelian.status = "success"
    pembelian.verified_at = datetime.datetime.utcnow()
    session.commit()

    await update.message.reply_text(
        f"✅ Pembelian {trx_code} disetujui. Saldo user sudah dipotong Rp{int(pembelian.price)}."
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
            text=f"❌ Pembelian {pembelian.product_name} dengan ID {trx_code} ditolak admin. Saldo kamu tidak berubah."
        )

    await update.message.reply_text(f"❌ Pembelian {trx_code} ditolak.")

# ================== MAIN ===================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve_topup", approve_topup))
    app.add_handler(CommandHandler("reject_topup", reject_topup))
    app.add_handler(CommandHandler("approve_beli", approve_beli))
    app.add_handler(CommandHandler("reject_beli", reject_beli))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
