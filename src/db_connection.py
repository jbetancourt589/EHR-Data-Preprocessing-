
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# Find the project's root directory
ROOT = Path(__file__).resolve().parent.parent

# Load PostgreSQL credentials
load_dotenv(ROOT / ".env")

# Configure PostgreSQL connection
database_url = URL.create(
    "postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME")
)

engine = create_engine(database_url)

if __name__ == "__main__":
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database();")
        )
        print("Connected to:", result.scalar())
