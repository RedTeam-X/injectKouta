from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from models import Base
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

def ensure_kategori_column_exists():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE ppob_items ADD COLUMN kategori VARCHAR"))
        except ProgrammingError as e:
            if "already exists" in str(e):
                pass  # kolom sudah ada, aman
            else:
                raise
              
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)
