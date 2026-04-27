from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from db.session import get_database_url

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
ALEMBIC_INI_PATH = BASE_DIR / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION = BASE_DIR / "alembic"


def _read_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%s; using default=%s", name, value, default)
        return default


def _read_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid float for %s=%s; using default=%s", name, value, default)
        return default


def _build_alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    return config


def _wait_for_postgres(
    database_url: str,
    *,
    max_attempts: int,
    retry_seconds: float,
) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True, future=True)

    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("Database is reachable.")
            return engine
        except OperationalError as exc:
            if attempt == max_attempts:
                engine.dispose()
                raise RuntimeError(
                    f"Database is unreachable after {max_attempts} attempts"
                ) from exc

            logger.warning(
                "Database unavailable (attempt %s/%s): %s",
                attempt,
                max_attempts,
                exc,
            )
            time.sleep(retry_seconds)

    raise RuntimeError("Unexpected wait_for_postgres termination")


def initialize_database() -> None:
    """
    Apply migrations safely.

    Safety features:
    - waits for PostgreSQL readiness
    - acquires a global advisory lock to avoid concurrent migrations
    - runs Alembic upgrade head within the same locked connection
    """
    database_url = get_database_url()
    if not database_url.startswith("postgresql"):
        raise RuntimeError(
            "This project expects PostgreSQL for long-term memory checkpointing."
        )

    max_attempts = _read_int_env("DB_INIT_MAX_ATTEMPTS", 30)
    retry_seconds = _read_float_env("DB_INIT_RETRY_SECONDS", 2.0)
    lock_key = _read_int_env("DB_MIGRATION_LOCK_KEY", 742159)

    logger.info("Initializing database and applying migrations...")
    engine = _wait_for_postgres(
        database_url,
        max_attempts=max_attempts,
        retry_seconds=retry_seconds,
    )

    alembic_config = _build_alembic_config(database_url)

    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
            try:
                alembic_config.attributes["connection"] = connection
                command.upgrade(alembic_config, "head")
                logger.info("Database migrations are up to date.")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key}
                )
    finally:
        engine.dispose()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    initialize_database()


if __name__ == "__main__":
    main()