from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class Member(Base):
    __tablename__ = 'members'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    otp = Column(String)
    otp_expiry = Column(DateTime)
    saldo = Column(Float, default=0)
    transaksi = Column(Integer, default=0)
    verified = Column(Boolean, default=False)

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer)
    product = Column(String)
    amount = Column(Float)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
