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
            "✅ Laporan kamu sudah dikirim ke admin.\nTerima kasih sudah membantu memperbaiki sistem.",
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
            "📨 Pesan kamu sudah dikirim ke admin.\nAdmin akan membalas secepatnya.",
            reply_markup=main_menu_keyboard()
        )

        context.user_data["state"] = STATE_NONE
        return

    # ---------- STATE: MINTA NOMOR TUJUAN ----------
    if state == STATE_MINTA_NOMOR:
        nomor = text

        if not is_valid_phone(nomor):
            await update.message.reply_text("❌ Format nomor tidak valid. Masukkan nomor XL yang benar.")
            return

        item = context.user_data.get("item_dipilih")
        if not item:
            await update.message.reply_text("❌ Item tidak ditemukan. Silakan ulangi pembelian.")
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

        await update.message.reply_text("❌ Kategori tidak dikenal. Pilih dari daftar.")
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
                        "📱 Masukkan nomor XL tujuan pengiriman kuota:"
                    )
                    return

        await update.message.reply_text("❌ Item tidak ditemukan. Pilih dari daftar.")
        return

    # ================== MENU UTAMA ==================

    # ---------- LAPOR MASALAH ----------
    if text == "Lapor Masalah":
        context.user_data["state"] = STATE_LAPOR_BUG
        await update.message.reply_text(
            "📝 Silakan jelaskan bug, error, atau saran yang kamu temui.\n"
            "Tulis sedetail mungkin."
        )
        return

    # ---------- HUBUNGI ADMIN ----------
    if text == "Hubungi Admin":
        context.user_data["state"] = STATE_HUBUNGI_ADMIN
        await update.message.reply_text(
            "📨 Silakan tulis pesan yang ingin kamu sampaikan ke admin."
        )
        return

    # ---------- TUTORIAL LOGIN ----------
    if text == "Tutorial Login":
        await update.message.reply_text(
            "📘 *Tutorial Login*\n\n"
            "1. Tekan tombol *Login* di menu.\n"
            "2. Bot akan mengirim kode OTP ke DM kamu.\n"
            "3. Masukkan kode OTP di chat dalam waktu 1 menit.\n"
            "4. Jika benar, kamu akan masuk ke Dashboard Member.",
            parse_mode="Markdown"
        )
        return

    # ---------- TUTORIAL TOP UP ----------
    if text == "Tutorial Top Up":
        await update.message.reply_text(
            "📘 *Tutorial Top Up*\n\n"
            "1. Tekan tombol *Top Up* di menu.\n"
            "2. Bot akan menampilkan QRIS.\n"
            "3. Scan QRIS dan lakukan pembayaran.\n"
            "4. Kirim foto bukti transfer ke bot.\n"
            "5. Admin akan memverifikasi dan saldo kamu akan bertambah.",
            parse_mode="Markdown"
        )
        return

    # ---------- XL DOR ----------
    if text == "XL Dor":
        if not member.verified:
            await update.message.reply_text("❌ Kamu harus login dulu sebelum membeli produk.")
            return

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
            text=f"🔐 Kode OTP kamu: {otp}\nBerlaku 1 menit."
        )

        await update.message.reply_text("📩 OTP sudah dikirim ke DM kamu.")
        return

    # ---------- PPOB ----------
    if text == "PPOB":
        await update.message.reply_text("⚠️ Menu PPOB masih *Coming Soon*.", parse_mode="Markdown")
        return

    # ---------- TOP UP ----------
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
            await update.message.reply_text("⚠️ QRIS tidak ditemukan di server.")

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
                "⏰ OTP sudah kadaluarsa. Klik *Login* untuk minta ulang.",
                parse_mode="Markdown"
            )
        return

    if text.isdigit() and not member.verified:
        await update.message.reply_text(
            "❌ OTP salah atau kadaluarsa. Klik *Login* untuk minta ulang.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        "Perintah tidak dikenal. Gunakan menu tombol.",
        reply_markup=main_menu_keyboard()
    )

# ================== HANDLE FOTO (BUKTI TOPUP) ==================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    tg_user = update.effective_user
    member = get_or_create_member(session, tg_user)

    if not context.user_data.get("topup_mode", False):
        await update.message.reply_text("❌ Kamu tidak sedang melakukan top-up.")
        return

    trx_code = f"TOPUP-{member.id}-{int(datetime.datetime.utcnow().timestamp())}"
    bukti_path = generate_bukti_topup_image(trx_code, member.username, member.telegram_id)

    topup = Topup(
        member_id=member.id,
        trx_code=trx_code,
        status="pending"
    )
    session.add(topup)
    session.commit()

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

# ================== ADMIN: VERIFIKASI TOPUP ==================

async def approvetopup(update: Update, context: ContextTypes.DEFAULTTYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
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

================== ADMIN: VERIFIKASI PEMBELIAN ==================

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

================== ADMIN: BALAS USER ==================

async def balas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
        return

    session = SessionLocal()
    args = update.message.text.split(" ", 2)
    if len(args) < 3:
        await update.message.replytext("Format: /balas <telegramid> <pesan>")
        return

    , userid, pesan = args

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

================== ADMIN: BROADCAST ==================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effectiveuser.id != ADMINCHAT_ID:
        return

    session = SessionLocal()
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
                chatid=int(m.telegramid),
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

================== MAIN ==================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.addhandler(CommandHandler("approvetopup", approve_topup))
    app.addhandler(CommandHandler("rejecttopup", reject_topup))
    app.addhandler(CommandHandler("approvebeli", approve_beli))
    app.addhandler(CommandHandler("rejectbeli", reject_beli))
    app.add_handler(CommandHandler("balas", balas))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.addhandler(MessageHandler(filters.PHOTO, handlephoto))
    app.addhandler(MessageHandler(filters.TEXT & ~filters.COMMAND, handletext))

    app.run_polling()

if name == "main":
    main()
