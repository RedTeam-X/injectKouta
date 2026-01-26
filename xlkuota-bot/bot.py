from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import random

BOT_TOKEN = "8544774444:AAH13JEgpbPZfBEdgO6KProb9sSENAWCxFA"

# Simulasi database user
users = {}

# Produk sesuai flowchart (disingkat)
PRODUCTS = [
    "XL XTRA KOUTA CONF 2GB, 1HR Rp.5000",
    "XL XTRA KOUTA YT 2GB, 3HR Rp.7000",
    "XL XTRA KOUTA INSTAGRAM 3GB, 7HR Rp.10.000"
]

# === START COMMAND ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["XL Dor", "Login", "PPOB"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📲 Silakan pilih menu:", reply_markup=reply_markup)

# === HANDLE BUTTON ===
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    choice = update.message.text

    # XL Dor
    if choice == "XL Dor":
        if uid not in users or not users[uid].get("verified", False):
            await update.message.reply_text("❌ Kamu harus login dulu sebelum membeli produk.")
        else:
            msg = "📦 List Produk XL:\n"
            for p in PRODUCTS:
                msg += f"- {p}\n"
            await update.message.reply_text(msg)

    # Login
    elif choice == "Login":
        otp = str(random.randint(100000, 999999))
        users[uid] = {"otp": otp, "verified": False, "saldo": 0, "trx": 0}
        # Kirim OTP ke user via DM (private chat)
        await context.bot.send_message(chat_id=uid, text=f"🔐 Kode OTP kamu: {otp}\nKirim kode ini di chat bot untuk login.")
        await update.message.reply_text("📩 OTP sudah dikirim ke akun Telegram kamu.")

    # PPOB
    elif choice == "PPOB":
        await update.message.reply_text("⚠️ Menu PPOB masih *Coming Soon*.")

    # OTP Input
    elif choice.isdigit():
        if uid in users and users[uid]["otp"] == choice:
            users[uid]["verified"] = True
            await update.message.reply_text(f"""
✅ Login berhasil!
📊 Dashboard Member:
- Nama Akun: {update.effective_user.username}
- Saldo: Rp{users[uid]['saldo']}
- Jumlah Transaksi: {users[uid]['trx']}
- Minimal Top-Up: Rp20.000
""")
        else:
            await update.message.reply_text("❌ OTP salah atau kadaluarsa. Klik Login untuk minta ulang.")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
app.run_polling()
