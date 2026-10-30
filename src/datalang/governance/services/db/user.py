from sqlalchemy import text

from governance.services.db.conn import get_db_session
from governance.schemas.cdc import CDCUser
from governance.schemas.database import DatabaseCredentials
from governance.error_handling.cdc import CDCUsernameDuplicated


def is_replication_user_exist(credentials: DatabaseCredentials) -> bool:
    # query = text("""
    #     SELECT
    #         rolname,
    #         rolcanlogin
    #         rolreplication
    #     FROM pg_roles
    #     WHERE rolname = :username
    # """)
    #
    # existing = db.execute(
    #     query,
    #     {"username": cdc_user.name}
    # ).fetchone()
    #
    # if existing is None and (existing.rolcanlogin and existing.rolreplication):
    #     print(f"Replication user {cdc_user.name!r} already exists")
    # Seems like already exists... Proceed?
    # Check if in datalang DB too
    pass


def is_replication_username_duplicated(db_session, cdc_user: CDCUser) -> bool:
    existing = db_session.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_roles
                WHERE rolname = :username
            )
        """),
        {"username": cdc_user.name}
    ).scalar_one()

    return existing


def create_replication_user(
    credentials: DatabaseCredentials,
    cdc_user: CDCUser
):
    # TODO: Ask user if they need to select existing replication user
    with get_db_session(credentials) as db:
        if is_replication_username_duplicated(db, cdc_user):
            raise CDCUsernameDuplicated(
                f"Replication username {cdc_user.name!r} is duplicated."
            )
        db.execute(
            text("""
                CREATE ROLE :username
                WITH LOGIN REPLICATION PASSWORD :password
            """),
            {
                "username": cdc_user.name,
                "password": cdc_user.password
            }
        )
