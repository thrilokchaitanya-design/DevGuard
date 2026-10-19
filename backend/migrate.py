"""Run Alembic migrations while serializing concurrent PostgreSQL service starts."""
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, text

from app.config import settings, sqlalchemy_database_url


ROOT = Path(__file__).resolve().parent
MIGRATION_LOCK_ID = 7_314_290_118


def main() -> int:
    settings.validate_security_config()
    database_url = sqlalchemy_database_url(settings.database_url)
    os.environ["DATABASE_URL"] = database_url
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            locked = engine.dialect.name == "postgresql"
            if locked:
                connection.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
            try:
                result = subprocess.run([sys.executable, "-c", "from alembic.config import main; main()", "upgrade", "head"], cwd=ROOT, env=os.environ.copy(), check=False)
                return result.returncode
            finally:
                if locked:
                    connection.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
