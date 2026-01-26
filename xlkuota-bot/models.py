from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String)
    otp = Column(String, nullable=True)
    verified = Column(Boolean, default=False)
    saldo = Column(Float, default=0)
    transaksi = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Topup(Base):
    __tablename__ = "topups"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members.id"))
    trx_code = Column(String, unique=True, index=True)
    amount = Column(Float, nullable=True)
    status = Column(String, default="pending")  # pending, success, rejected
    bukti_file_id = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)

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
