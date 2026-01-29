from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

# ================== MEMBER ==================
class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String)
    verified = Column(Boolean, default=False)
    saldo = Column(Float, default=0)
    transaksi = Column(Integer, default=0)
    otp = Column(String, nullable=True)
    otp_created_at = Column(DateTime, nullable=True)

# ================== TOPUP ==================
class Topup(Base):
    __tablename__ = "topups"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer)
    trx_code = Column(String, unique=True, index=True)
    amount = Column(Float, nullable=True)
    status = Column(String, default="pending")
    verified_at = Column(DateTime, nullable=True)

# ================== PURCHASE ==================
class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer)
    trx_code = Column(String, unique=True, index=True)
    product_name = Column(String)
    price = Column(Float)
    status = Column(String, default="pending")
    verified_at = Column(DateTime, nullable=True)

# ================== REPORT ==================
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer)
    category = Column(String)
    message = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ================== MESSAGE LOG ==================
class MessageLog(Base):
    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(String)
    receiver_id = Column(String)
    message = Column(String)
    direction = Column(String)  # user_to_admin / admin_to_user
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ================== XL DOR ITEM ==================
class XLDorItem(Base):
    __tablename__ = "xldor_items"

    id = Column(Integer, primary_key=True, index=True)
    nama_item = Column(String, unique=True, index=True)
    harga = Column(Float)
    deskripsi = Column(String)
    masa_aktif = Column(Integer)  # dalam hari
    aktif = Column(Boolean, default=True)

# ================== PPOB ITEM ==================
class PPOBItem(Base):
    __tablename__ = "ppob_items"

    id = Column(Integer, primary_key=True, index=True)
    nama_item = Column(String, unique=True, index=True)
    harga = Column(Float)
    deskripsi = Column(String)
    masa_aktif = Column(Integer)  # dalam hari
    aktif = Column(Boolean, default=True)
