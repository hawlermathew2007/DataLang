from governance.core.config import settings
from governance.schemas.database import DatabaseCredentials
from governance.schemas.table import Base
from governance.services.db.conn import get_engine


def is_database_exists() -> bool:
    pass


def setup_db():
    credentials = DatabaseCredentials(
        database=settings.db_database,
        username=settings.db_user,
        password=settings.db_password,
        hostname=settings.db_host,
        port=settings.db_port
    )
    engine = get_engine(credentials)
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    setup_db()
    print("Successfully created all tables to datalang.")
