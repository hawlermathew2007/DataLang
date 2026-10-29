from contextlib import contextmanager
from fastapi import HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from governance.schemas.database import DatabaseCredentials


def is_db_auth_success(engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    except OperationalError as e:
        print(e)
        raw_driver_error = e.orig
        # Check standard Postgres SQLSTATE for 'invalid_password'
        if raw_driver_error and hasattr(raw_driver_error, 'pgcode'):
            if raw_driver_error.pgcode == '28P01':
                return False

        # Check fallback text securely within the isolated driver footprint
        if raw_driver_error and hasattr(raw_driver_error, 'pgerror'):
            pg_msg = str(raw_driver_error.pgerror).lower()
            if "authentication" in pg_msg or "password" in pg_msg:
                return False

    except Exception as e:
        print(e)
        return False


def get_engine(credentials: DatabaseCredentials):
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=credentials.username,
        password=credentials.password,
        host=credentials.hostname,
        port=credentials.port,
        database=credentials.database,
    )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )
    # create_engine is lazy
    # it doesn't test the connection until you use it.
    # Use .connect() to force a handshake check.
    try:
        if not is_db_auth_success(engine):
            engine.dispose()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed. Invalid database credentials.",
            )
        return engine

    except OperationalError:
        # The database server is completely down or unreachable (Network issue)
        engine.dispose()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database server is unreachable. Please try again later.",
        )

    return engine


@contextmanager
def get_db_session(credentials: DatabaseCredentials):
    engine = get_engine(credentials)
    SessionLocal = sessionmaker(bind=engine)
    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()  # consider not disposing for long term use
