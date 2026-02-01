from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import ProgrammingError
import os

from models import Base  # gunakan Base dari models.py

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ✅ Tambahkan expire_on_commit=False agar objek tidak detached
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Buat semua tabel sesuai models.py
Base.metadata.create_all(bind=engine)

def migrate_ppob_add_kategori():
    """Menambahkan kolom kategori jika belum ada."""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE ppob_items ADD COLUMN kategori VARCHAR"))
            conn.commit()
            print("Kolom kategori berhasil ditambahkan.")
        except ProgrammingError as e:
            if "already exists" in str(e):
                print("Kolom kategori sudah ada.")
            else:
                raise

def migrate_xldor_add_kategori():
    """Menambahkan kolom kategori ke XL Dor jika belum ada."""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE xldor_items ADD COLUMN kategori VARCHAR"))
            conn.commit()
            print("Kolom kategori berhasil ditambahkan.")
        except ProgrammingError as e:
            if "already exists" in str(e):
                print("Kolom kategori sudah ada.")
            else:
                raise
