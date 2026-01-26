from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# SQLite lokal (Railway juga bisa pakai ini untuk awal)
engine = create_engine("sqlite:///xlkuota.db")
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)
