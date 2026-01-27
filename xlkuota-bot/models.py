import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Float, ForeignKey, Text
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# ================== MEMBER ==================

class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String)
    otp = Column(String, nullable=True)
    otp_created_at = Column(DateTime, nullable=True)
    verified = Column(Boolean, default=False)
    saldo = Column(Float, default=0)
    transaksi = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ================== TOPUP ==================

class Topup(Base):
    __tablename__ = "topups"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members.id"))
    trx_code = Column(String, unique=True, index=True)
    amount = Column(Float, nullable=True)
    status = Column(String, default="pending")  # pending, success, rejected
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)


# ================== PURCHASE ==================

class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members.id"))
    trx_code = Column(String, unique=True, index=True)
    product_name = Column(String)
    price = Column(Float)
    status = Column(String, default="pending")  # pending, success, rejected
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)


# ================== REPORT (LAPOR BUG) ==================

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members.id"))
    category = Column(String)  # BUG / SUGGESTION / ERROR
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ================== MESSAGE LOG (CHAT ADMIN-USER) ==================

class MessageLog(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    sender_id = Column(String)      # telegram_id pengirim
    receiver_id = Column(String)    # telegram_id penerima
    message = Column(Text)
    direction = Column(String)      # user_to_admin / admin_to_user
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
