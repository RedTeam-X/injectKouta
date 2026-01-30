from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def migrate_ppob_add_kategori():
    """Menambahkan kolom kategori jika belum ada."""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE ppob_items ADD COLUMN kategori VARCHAR"))
            print("Kolom kategori berhasil ditambahkan.")
        except ProgrammingError as e:
            if "already exists" in str(e):
                print("Kolom kategori sudah ada.")
            else:
                raise
