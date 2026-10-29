from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import text

from governance.schemas.database import DatabaseCredentials, WALSettings
from governance.schemas.cache import create_cache, get_cache
from governance.services.db.conn import get_engine, get_db_session
from governance.services.db.config import read_wal, config_wal
from governance.services.session import create_app_session, get_cache_id

database_router = APIRouter(prefix="/api/v1/database", tags=["Database"])


@database_router.post("/connect")
async def connect_postgres_db(
    credentials: DatabaseCredentials,
    response: Response
):
    try:
        with get_db_session(credentials) as db:
            info = db.execute(text("""
                SELECT current_database() AS database_name,
                       current_user AS username,
                       rolsuper
                FROM pg_roles
                WHERE rolname = current_user
            """)).mappings().one()

            if not info["rolsuper"]:
                raise HTTPException(
                    status_code=HTTP_403_FORBIDDEN,
                    detail="A PostgreSQL superuser is required "
                           "for this workflow.",
                )
        # TODO: Validate whether the DB is registered in datalang DB or not

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not connect to PostgreSQL. Error: {e}",
        )

    cache = create_cache(
        holder=credentials,
    )

    create_app_session(response, cache)

    return {
        # "cache_id": cache.id,
        "status": "connected",
        "database": info["database_name"],
        "admin_verified": True,
    }


@database_router.get("/config/wal/view")
def inspect_wal(request: Request):
    cache_id = get_cache_id(request)
    cache = get_cache(cache_id)

    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cache not found or expired.",
        )

    credentials = cache.holder

    with get_db_session(credentials) as db:
        rows = read_wal(db)

        return rows,


@database_router.post("/config/wal/update")
def update_wal(request: Request, wal_settings: WALSettings):
    cache_id = get_cache_id(request)
    cache = get_cache(cache_id)

    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cache not found or expired.",
        )

    credentials = cache.holder

    # PostgreSQL rejects this statement if it runs inside a transaction block
    # which is not in autocommit mode (implicit transaction block)
    engine = get_engine(credentials)
    result = config_wal(engine, wal_settings)

    return result


# 1. Load a registered database connection profile.
# 2. Obtain an authorized provisioning connection.
# 3. Inspect PostgreSQL settings and capabilities.
# 4. If approved, configure WAL and flag restart requirements.
# 5. Create or reconcile the dedicated CDC role.
# 6. Validate selected tables and apply minimal grants.
# 7. Create or reconcile the publication.
# 8. Register the connector and verify task status.
# 9. Persist an audit record and build the summary.
