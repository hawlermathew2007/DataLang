from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from collections.abc import Generator

from governance.schemas.database import DatabaseCredentials
from governance.services.db.auth import is_db_auth_success
from governance.error_handling.database import (
    DatabaseAuthenticationError,
    DatabaseOperationError,
    DatabaseConnectionError
)


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
            raise DatabaseAuthenticationError()
        return engine

    except OperationalError:
        # The database server is completely down or unreachable (Network issue)
        engine.dispose()
        raise DatabaseOperationError()

    return engine


# DB session for DML (select, update, delete,...)
@contextmanager
def get_db_session(credentials: DatabaseCredentials) -> Generator:
    engine = get_engine(credentials)
    SessionLocal = sessionmaker(bind=engine)
    try:
        with SessionLocal() as db:
            yield db
    except Exception:
        raise DatabaseConnectionError(
            "Database Connection session during ORM layer disrupted."
        )
    finally:
        engine.dispose()  # consider not disposing for long term use


# DB session for DDL (create, rename, alter,...)
def get_db_core_session(credentials: DatabaseCredentials) -> Generator:
    engine = get_engine(credentials)

    # Need to be at core layer to perform DDL
    core_session = engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    )

    try:
        with core_session as db:
            yield db
    except Exception:
        raise DatabaseConnectionError(
            "Database Connection session during Core layer disrupted."
        )
    finally:
        engine.dispose()  # consider not disposing for long term use
