import os
import random
import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from PIL import Image, ImageDraw, ImageFont

from config import BOTTOKEN, ADMINCHATID, MINTOPUP, QRISIMAGEPATH
from db import SessionLocal
from models import Member, Topup, Purchase, Report, MessageLog

================== KONSTAN & STATE ==================

STATE_NONE = None
STATEPILIHKATEGORI = "pilih_kategori"
STATEPILIHITEM = "pilih_item"
STATEMINTANOMOR = "minta_nomor"
STATELAPORBUG = "lapor_bug"
STATEHUBUNGIADMIN = "hubungi_admin"

def mainmenukeyboard():
    return ReplyKeyboardMarkup(
        [
            ["XL Dor", "Login", "PPOB"],
            ["Top Up", "Lapor Masalah", "Hubungi Admin"]
        ],
        resize_keyboard=True
    )

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

================== HELPER DB & UTIL ==================

def getorcreatemember(session, tguser):
    member = session.query(Member).filterby(telegramid=str(tg_user.id)).first()
    if not member:
        member = Member(
            telegramid=str(tguser.id),
            username=tguser.username or str(tguser.id),
            verified=False,
            saldo=0,
            transaksi=0
        )
        session.add(member)
        session.commit()
    return member

def generatebuktitopupimage(trxcode, username, telegram_id):
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    draw.text((50, 50), "BUKTI TRANSAKSI TOP-UP", fill="black", font=font)
    draw.text((50, 150), f"ID Transaksi : {trx_code}", fill="black", font=font)
    draw.text((50, 200), f"User        : {username}", fill="black", font=font)
    draw.text((50, 250), f"Telegram ID : {telegram_id}", fill="black", font=font)
    draw.text((50, 350), "Silakan verifikasi apakah bukti transfer valid.", fill="black", font=font)
    draw.text((50, 420), "SanStore", fill="gray", font=font)

    path = f"bukti{trxcode}.png"
    img.save(path)
    return path

def isvalidphone(number: str) -> bool:
    number = number.strip()
    return number.isdigit() and 10 <= len(number) <= 15

def autotagreport(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["bug", "error", "gak jalan", "ga jalan", "crash", "traceback"]):
        return "BUG"
    if any(k in t for k in ["saran", "suggest", "ide", "fitur baru"]):
        return "SUGGESTION"
    if any(k in t for k in ["gagal", "tidak bisa", "masalah", "trouble"]):
        return "ERROR"
    return "BUG"  # default aman

================== START ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.userdata["state"] = STATENONE
    context.userdata["topupmode"] = False
    await update.message.reply_text(
        "📲 Silakan pilih menu:",
        replymarkup=mainmenu_keyboard()
    )

================== HANDLE TEKS ==================

async def handletext(update: Update, context: ContextTypes.DEFAULTTYPE):
    session = SessionLocal()
    text = (update.message.text or "").strip()
    tguser = update.effectiveuser
    member = getorcreatemember(session, tguser)
    state = context.userdata.get("state", STATENONE)

    # ---------- STATE: LAPOR BUG / MASALAH ----------
    if state == STATELAPORBUG:
        laporan = text
        kategori = autotagreport(laporan)

        # simpan ke DB
        report = Report(
            member_id=member.id,
            category=kategori,
            message=laporan,
            created_at=datetime.datetime.utcnow()
        )
        session.add(report)
        session.commit()

        # kirim ke admin
        await context.bot.send_message(
            chatid=ADMINCHAT_ID,
            text=(
                "🐞 Laporan Baru dari User\n"
                f"Kategori: {kategori}\n"
                f"User: {member.username} (ID: {member.telegram_id})\n\n"
                f"Isi laporan:\n{laporan}"
            ),
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            "✅ Laporan kamu sudah dikirim ke admin.\nTerima kasih sudah membantu memperbaiki sistem.",
            replymarkup=mainmenu_keyboard()
        )

        context.userdata["state"] = STATENONE
        return

    # ---------- STATE: HUBUNGI ADMIN ----------
    if state == STATEHUBUNGIADMIN:
        pesan = text

        # log ke DB
        msg_log = MessageLog(
            senderid=str(member.telegramid),
            receiverid=str(ADMINCHAT_ID),
            message=pesan,
            direction="usertoadmin",
            created_at=datetime.datetime.utcnow()
        )
        session.add(msg_log)
        session.commit()

        await context.bot.send_message(
            chatid=ADMINCHAT_ID,
            text=(
                "📩 Pesan Baru dari User\n"
                f"User: {member.username} (ID: {member.telegram_id})\n\n"
                f"Pesan:\n{pesan}\n\n"
                f"Balas dengan format:\n"
                f"/balas {member.telegram_id} <pesan>"
            ),
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            "📨 Pesan kamu sudah dikirim ke admin.\nAdmin akan membalas secepatnya.",
            replymarkup=mainmenu_keyboard()
        )

        context.userdata["state"] = STATENONE
        return

    # ---------- STATE: MINTA NOMOR TUJUAN ----------
    if state == STATEMINTANOMOR:
        nomor = text
        if not isvalidphone(nomor):
            await update.message.reply_text("❌ Format nomor tidak valid. Masukkan nomor XL yang benar.")
            return

        item = context.userdata.get("itemdipilih")
        if not item:
            await update.message.reply_text("❌ Item tidak ditemukan. Silakan ulangi pembelian.")
            context.userdata["state"] = STATENONE
            return

        nama, harga = item

        if member.saldo < harga:
            await update.message.reply_text(
                f"❌ Saldo tidak cukup.\nSaldo kamu: Rp{int(member.saldo)}\nHarga: Rp{harga}"
            )
            context.userdata["state"] = STATENONE
            context.userdata["itemdipilih"] = None
            return

        trx_code = f"BUY-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"
        pembelian = Purchase(
            member_id=member.id,
            trxcode=trxcode,
            product_name=nama,
            price=harga,
            status="pending"
        )
        session.add(pembelian)
        session.commit()

        await context.bot.send_message(
            chatid=ADMINCHAT_ID,
            text=(
                "🧾 Transaksi Pembelian Baru\n"
                f"ID: {trx_code}\n"
                f"User: {member.username} (ID: {member.telegram_id})\n"
                f"Produk: {nama}\n"
                f"Harga: Rp{harga}\n"
                f"Nomor Tujuan: {nomor}\n\n"
                "Setelah kuota dikirim ke nomor tujuan, gunakan:\n"
                f"/approvebeli {trxcode}\n"
                f"/rejectbeli {trxcode}"
            ),
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            f"📨 Permintaan pembelian dikirim ke admin.\nNomor tujuan: {nomor}",
            replymarkup=mainmenu_keyboard()
        )

        context.userdata["state"] = STATENONE
        context.userdata["itemdipilih"] = None
        return

    # ---------- STATE: PILIH KATEGORI ----------
    if state == STATEPILIHKATEGORI:
        if text in PRODUCTS:
            items = PRODUCTS[text]
            item_buttons = [[p[0]] for p in items]
            reply = ReplyKeyboardMarkup(itembuttons + [["⬅️ Kembali"]], resizekeyboard=True)

            context.user_data["kategori"] = text
            context.userdata["state"] = STATEPILIH_ITEM

            await update.message.replytext(f"📄 List item {text}:", replymarkup=reply)
            return

        if text == "⬅️ Kembali":
            context.userdata["state"] = STATENONE
            await update.message.replytext("📲 Silakan pilih menu:", replymarkup=mainmenukeyboard())
            return

        await update.message.reply_text("❌ Kategori tidak dikenal. Pilih dari daftar.")
        return

    # ---------- STATE: PILIH ITEM ----------
    if state == STATEPILIHITEM:
        kategori = context.user_data.get("kategori")
        if text == "⬅️ Kembali":
            kategori_buttons = [[k] for k in PRODUCTS.keys()]
            reply = ReplyKeyboardMarkup(kategoributtons + [["⬅️ Kembali"]], resizekeyboard=True)
            context.userdata["state"] = STATEPILIH_KATEGORI
            await update.message.replytext("📦 Pilih kategori produk XL:", replymarkup=reply)
            return

        if kategori in PRODUCTS:
            for nama, harga in PRODUCTS[kategori]:
                if nama == text:
                    context.userdata["itemdipilih"] = (nama, harga)
                    context.userdata["state"] = STATEMINTA_NOMOR
                    await update.message.reply_text("📱 Masukkan nomor XL tujuan pengiriman kuota:")
                    return

        await update.message.reply_text("❌ Item tidak ditemukan. Pilih dari daftar.")
        return

    # ================== MENU UTAMA ==================

    # ---------- LAPOR MASALAH ----------
    if text == "Lapor Masalah":
        context.userdata["state"] = STATELAPOR_BUG
        await update.message.reply_text(
            "📝 Silakan jelaskan bug, error, atau saran yang kamu temui.\n"
            "Tulis sedetail mungkin."
        )
        return

    # ---------- HUBUNGI ADMIN ----------
    if text == "Hubungi Admin":
        context.userdata["state"] = STATEHUBUNGI_ADMIN
        await update.message.reply_text(
            "📨 Silakan tulis pesan yang ingin kamu sampaikan ke admin."
        )
        return

    # ---------- XL DOR ----------
    if text == "XL Dor":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu sebelum membeli produk.")
            return

        kategori_buttons = [[k] for k in PRODUCTS.keys()]
        reply = ReplyKeyboardMarkup(kategoributtons + [["⬅️ Kembali"]], resizekeyboard=True)

        context.userdata["state"] = STATEPILIH_KATEGORI
        await update.message.replytext("📦 Pilih kategori produk XL:", replymarkup=reply)
        return

    # ---------- LOGIN ----------
    if text == "Login":
        if member.verified:
            await update.message.reply_text(
                "📊 Dashboard Member:\n"
                f"- Username: {member.username}\n"
                f"- Saldo: Rp{int(member.saldo)}\n"
                f"- Transaksi: {member.transaksi}\n"
                f"- Minimal Top-Up: Rp{MIN_TOPUP}",
                replymarkup=mainmenu_keyboard()
            )
            return

        otp = str(random.randint(100000, 999999))
        member.otp = otp
        member.otpcreatedat = datetime.datetime.utcnow()
        session.commit()

        await context.bot.send_message(
            chatid=tguser.id,
            text=f"🔐 Kode OTP kamu: {otp}\nBerlaku 1 menit."
        )

        await update.message.reply_text("📩 OTP sudah dikirim ke DM kamu.")
        return

    # ---------- PPOB ----------
    if text == "PPOB":
        await update.message.replytext("⚠️ Menu PPOB masih Coming Soon.", parsemode="Markdown")
        return

    # ---------- TOP UP ----------
    if text == "Top Up":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu.")
            return

        await update.message.reply_text(
            f"💰 Top Up Saldo\nMinimal top-up: Rp{MIN_TOPUP}\n\n"
            "Silakan transfer ke QRIS berikut lalu kirim bukti transfer berupa foto.",
            parse_mode="Markdown"
        )

        if os.path.exists(QRISIMAGEPATH):
            with open(QRISIMAGEPATH, "rb") as f:
                await context.bot.send_photo(
                    chatid=tguser.id,
                    photo=f,
                    caption="🔶 Scan QRIS ini untuk top-up saldo."
                )
        else:
            await update.message.reply_text("⚠️ QRIS belum diset di server (file tidak ditemukan).")

        context.userdata["topupmode"] = True
        return

    # ---------- OTP VALIDASI ----------
    if text.isdigit() and member.otp == text and not member.verified:
        now = datetime.datetime.utcnow()
        if member.otpcreatedat and (now - member.otpcreatedat).total_seconds() <= 60:
            member.verified = True
            member.otp = None
            member.otpcreatedat = None
            session.commit()

            await update.message.reply_text(
                "✅ Login berhasil!\n\n"
                f"📊 Dashboard Member:\n"
                f"- Username: {member.username}\n"
                f"- Saldo: Rp{int(member.saldo)}\n"
                f"- Transaksi: {member.transaksi}\n"
                f"- Minimal Top-Up: Rp{MIN_TOPUP}",
                replymarkup=mainmenu_keyboard()
            )
        else:
            member.otp = None
            member.otpcreatedat = None
            session.commit()
            await update.message.reply_text(
                "⏰ OTP sudah kadaluarsa. Klik Login untuk minta ulang.",
                parse_mode="Markdown"
            )
        return

    if text.isdigit() and not member.verified:
        await update.message.reply_text(
            "❌ OTP salah atau kadaluarsa. Klik Login untuk minta ulang.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "Perintah tidak dikenal. Gunakan menu tombol.",
        replymarkup=mainmenu_keyboard()
    )

================== HANDLE FOTO (BUKTI TOPUP) ===================

async def handlephoto(update: Update, context: ContextTypes.DEFAULTTYPE):
    session = SessionLocal()
    tguser = update.effectiveuser
    member = getorcreatemember(session, tguser)

    if not context.userdata.get("topupmode", False):
        await update.message.reply_text("❌ Kamu tidak sedang melakukan top-up.")
        return

    trx_code = f"TOPUP-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"
    buktipath = generatebuktitopupimage(trxcode, member.username, member.telegramid)

    topup = Topup(
        member_id=member.id,
        trxcode=trxcode,
        status="pending"
    )
    session.add(topup)
    session.commit()

    if os.path.exists(bukti_path):
        with open(bukti_path, "rb") as f:
            await context.bot.send_photo(
                chatid=ADMINCHAT_ID,
                photo=f,
                caption=(
                    "📥 Bukti Transaksi Top-Up Baru\n"
                    f"ID: {trx_code}\n"
                    f"User: {member.username} (ID: {member.telegram_id})\n\n"
                    "Gunakan:\n"
                    f"/approvetopup {trxcode} <jumlah>\n"
                    f"/rejecttopup {trxcode}"
                ),
                parse_mode="Markdown"
            )

    await update.message.reply_text(
        "📨 Bukti transfer sudah dikirim ke admin.\nMohon tunggu verifikasi.",
        parse_mode="Markdown"
    )

    context.userdata["topupmode"] = False

================== ADMIN: VERIFIKASI TOPUP ===================

async def approvetopup(update: Update, context: ContextTypes.DEFAULTTYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 3:
        await update.message.replytext("Format: /approvetopup <TRX_CODE> <jumlah>")
        return

    , trxcode, amount_str = args
    try:
        amount = float(amount_str)
    except ValueError:
        await update.message.reply_text("Jumlah tidak valid.")
        return

    topup = session.query(Topup).filterby(trxcode=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    member = session.query(Member).filterby(id=topup.memberid).first()
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
        chatid=int(member.telegramid),
        text=f"🎉 Top-up Rp{int(amount)} berhasil! Saldo kamu sekarang Rp{int(member.saldo)}"
    )

async def rejecttopup(update: Update, context: ContextTypes.DEFAULTTYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.replytext("Format: /rejecttopup <TRX_CODE>")
        return

    , trxcode = args

    topup = session.query(Topup).filterby(trxcode=trx_code).first()
    if not topup:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if topup.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    topup.status = "rejected"
    topup.verified_at = datetime.datetime.utcnow()
    session.commit()

    member = session.query(Member).filterby(id=topup.memberid).first()
    if member:
        await context.bot.send_message(
            chatid=int(member.telegramid),
            text=f"❌ Top-up {trx_code} ditolak admin. Saldo kamu tidak berubah."
        )

    await update.message.replytext(f"❌ Top-up {trxcode} ditolak.")

================== ADMIN: VERIFIKASI PEMBELIAN ===================

async def approvebeli(update: Update, context: ContextTypes.DEFAULTTYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.replytext("Format: /approvebeli <TRX_CODE>")
        return

    , trxcode = args

    pembelian = session.query(Purchase).filterby(trxcode=trx_code).first()
    if not pembelian:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if pembelian.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    member = session.query(Member).filterby(id=pembelian.memberid).first()
    if not member:
        await update.message.reply_text("Member tidak ditemukan.")
        return

    if member.saldo < pembelian.price:
        pembelian.status = "rejected"
        pembelian.verified_at = datetime.datetime.utcnow()
        session.commit()
        await update.message.reply_text("Saldo user tidak cukup saat verifikasi. Transaksi dibatalkan.")
        await context.bot.send_message(
            chatid=int(member.telegramid),
            text=f"❌ Pembelian {pembelian.product_name} dibatalkan karena saldo tidak cukup saat verifikasi."
        )
        return

    member.saldo -= pembelian.price
    member.transaksi += 1
    pembelian.status = "success"
    pembelian.verified_at = datetime.datetime.utcnow()
    session.commit()

    await update.message.reply_text(
        f"✅ Pembelian {trx_code} disetujui. Saldo user sudah dipotong Rp{int(pembelian.price)}."
    )

    await context.bot.send_message(
        chatid=int(member.telegramid),
        text=(
            f"🎉 Pembelian {pembelian.product_name} berhasil!\n"
            f"Saldo terpotong Rp{int(pembelian.price)}.\n"
            f"Saldo sekarang: Rp{int(member.saldo)}"
        )
    )

async def rejectbeli(update: Update, context: ContextTypes.DEFAULTTYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split()

    if len(args) != 2:
        await update.message.replytext("Format: /rejectbeli <TRX_CODE>")
        return

    , trxcode = args

    pembelian = session.query(Purchase).filterby(trxcode=trx_code).first()
    if not pembelian:
        await update.message.reply_text("ID transaksi tidak ditemukan.")
        return

    if pembelian.status != "pending":
        await update.message.reply_text("Transaksi sudah diproses.")
        return

    pembelian.status = "rejected"
    pembelian.verified_at = datetime.datetime.utcnow()
    session.commit()

    member = session.query(Member).filterby(id=pembelian.memberid).first()
    if member:
        await context.bot.send_message(
            chatid=int(member.telegramid),
            text=f"❌ Pembelian {pembelian.productname} dengan ID {trxcode} ditolak admin. Saldo kamu tidak berubah."
        )

    await update.message.replytext(f"❌ Pembelian {trxcode} ditolak.")

================== ADMIN: BALAS USER ===================

async def balas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split(" ", 2)
    if len(args) < 3:
        await update.message.replytext("Format: /balas <telegramid> <pesan>")
        return

    , userid, pesan = args

    # log ke DB
    msg_log = MessageLog(
        senderid=str(ADMINCHAT_ID),
        receiverid=str(userid),
        message=pesan,
        direction="admintouser",
        created_at=datetime.datetime.utcnow()
    )
    session.add(msg_log)
    session.commit()

    await context.bot.send_message(
        chatid=int(userid),
        text=f"📬 Balasan dari Admin:\n{pesan}",
        parse_mode="Markdown"
    )

    await update.message.reply_text("Pesan terkirim ke user.")

================== MAIN ===================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.addhandler(CommandHandler("approvetopup", approve_topup))
    app.addhandler(CommandHandler("rejecttopup", reject_topup))
    app.addhandler(CommandHandler("approvebeli", approve_beli))
    app.addhandler(CommandHandler("rejectbeli", reject_beli))
    app.add_handler(CommandHandler("balas", balas))
    app.addhandler(MessageHandler(filters.PHOTO, handlephoto))
    app.addhandler(MessageHandler(filters.TEXT & ~filters.COMMAND, handletext))

    app.run_polling()

if name == "main":
    main()
