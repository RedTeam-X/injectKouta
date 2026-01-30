from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

def migrate_ppob_add_kategori():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE ppob_items ADD COLUMN kategori VARCHAR"))
            print("Kolom kategori berhasil ditambahkan.")
        except ProgrammingError as e:
            if "already exists" in str(e):
                print("Kolom kategori sudah ada.")
            else:
                raise
