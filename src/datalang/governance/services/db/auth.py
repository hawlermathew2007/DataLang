from sqlalchemy import text
from sqlalchemy.exc import OperationalError


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
        # print(e)
        return False
