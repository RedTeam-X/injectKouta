from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from db import Session
from models import Member
from config import BOT_TOKEN, OTP_EXPIRY, MIN_TOPUP, ADMIN_CHAT_ID
import random, datetime, json

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    session = Session()
    member = session.query(Member).filter_by(telegram_id=telegram_id).first()
    if not member:
        otp = str(random.randint(100000, 999999))
        expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=OTP_EXPIRY)
        member = Member(telegram_id=telegram_id, otp=otp, otp_expiry=expiry)
        session.add(member)
        session.commit()
        await update.message.reply_text(f"Kode OTP kamu: {otp}\nKirim kode ini untuk login.")
    else:
        await update.message.reply_text("Kamu sudah terdaftar. Kirim OTP untuk login.")

async def otp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp_input = update.message.text.strip()
    telegram_id = str(update.effective_user.id)
    session = Session()
    member = session.query(Member).filter_by(telegram_id=telegram_id).first()
    if member and member.otp == otp_input and datetime.datetime.utcnow() < member.otp_expiry:
        member.verified = True
        session.commit()
        await update.message.reply_text("✅ Login berhasil! Ketik /menu untuk melihat produk.")
    else:
        await update.message.reply_text("❌ OTP salah atau kadaluarsa.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    session = Session()
    member = session.query(Member).filter_by(telegram_id=telegram_id).first()
    if not member or not member.verified:
        await update.message.reply_text("Kamu harus login dulu dengan OTP.")
        return
    with open("templates/menu.json") as f:
        menu_data = json.load(f)
    msg = "📦 Menu Produk XL:\n"
    for kategori, items in menu_data.items():
        msg += f"\n*{kategori}*\n"
        for item in items:
            msg += f"• {item}\n"
    await update.message.reply_text(msg)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, otp_handler))
app.run_polling()
