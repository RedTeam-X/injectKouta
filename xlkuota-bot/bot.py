from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import random, datetime, os

from config import BOT_TOKEN, ADMIN_CHAT_ID, MIN_TOPUP, QRIS_IMAGE_PATH
from db import SessionLocal
from models import Member, Topup

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

# ================== HANDLER START ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📲 Silakan pilih menu:",
        reply_markup=main_menu_keyboard()
    )

# ================== HANDLER TEKS / BUTTON ===================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    text = update.message.text
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    # ========== XL Dor ==========
    if text == "XL Dor":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu sebelum membeli produk.")
        else:
            # Di step berikutnya kita isi list produk & proses beli
            await update.message.reply_text("📦 Menu XL Dor akan diisi produk sesuai flowchart.")
        return

    # ========== Login ==========
    if text == "Login":
        if member.verified:
            await update.message.reply_text("✅ Kamu sudah login.", reply_markup=main_menu_keyboard())
            return

        otp = str(random.randint(100000, 999999))
        member.otp = otp
        session.commit()

        # kirim OTP ke DM user
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

    # ========== Top Up ==========
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

        # tandai user sedang mode topup
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

    # OTP salah
    if text.isdigit() and not member.verified:
        await update.message.reply_text(
            "❌ OTP salah atau kadaluarsa. Klik *Login* untuk minta ulang.",
            parse_mode="Markdown"
        )
        return

    # fallback
    await update.message.reply_text(
        "Perintah tidak dikenal. Gunakan menu button.",
        reply_markup=main_menu_keyboard()
    )

# ================== HANDLER FOTO (BUKTI TRANSFER) ===================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    # hanya proses jika user sedang mode topup
    if not context.user_data.get("topup_mode", False):
        await update.message.reply_text("❌ Kamu tidak sedang melakukan top-up.")
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    # generate kode transaksi unik
    trx_code = f"TOPUP-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"

    topup = Topup(
        member_id=member.id,
        trx_code=trx_code,
        status="pending",
        bukti_file_id=file_id
    )
    session.add(topup)
    session.commit()

    # reset mode topup
    context.user_data["topup_mode"] = False

    # kirim ke admin
    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=file_id,
        caption=(
            f"📥 *Transaksi Top-Up Baru*\n"
            f"ID: `{topup.trx_code}`\n"
            f"User: {member.username} (ID: {member.telegram_id})\n\n"
            f"Gunakan format:\n"
            f"/verifikasi {topup.trx_code} <jumlah>\n"
            f"contoh: /verifikasi {topup.trx_code} 50000"
        ),
        parse_mode="Markdown"
    )

    await update.message.reply_text(
        "📨 Bukti transfer sudah dikirim ke admin.\n"
        "Mohon tunggu verifikasi.",
        parse_mode="Markdown"
    )

# ================== ADMIN VERIFIKASI ===================

async def verifikasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 3:
        await update.message.reply_text("Format: /verifikasi <TRX_CODE> <jumlah>")
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

    # update saldo & transaksi
    member.saldo += amount
    member.transaksi += 1
    topup.amount = amount
    topup.status = "success"
    topup.verified_at = datetime.datetime.utcnow()
    session.commit()

    await update.message.reply_text(
        f"✅ Top-up {trx_code} sebesar Rp{int(amount)} berhasil diverifikasi."
    )

    # kabari user
    await context.bot.send_message(
        chat_id=int(member.telegram_id),
        text=f"🎉 Top-up Rp{int(amount)} berhasil! Saldo kamu sekarang Rp{int(member.saldo)}"
    )

# ================== MAIN ===================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("verifikasi", verifikasi))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
