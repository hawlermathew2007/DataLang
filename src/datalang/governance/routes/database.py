from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import text

from governance.schemas.database import DatabaseCredentials, WALSettings
from governance.schemas.permission import (
    # GrantRequest,
    GrantPrivilege,
    GrantObject,
    GrantObjectConfig,
    GrantSchemaObjnamesRequest,
    create_grant_req_multi_obj
)
from governance.schemas.cdc import CDCUser
from governance.schemas.cache import create_cache
from governance.services.db.conn import get_db_session
from governance.services.db.config import read_wal, config_wal
from governance.services.db.user import create_replication_user
from governance.services.db.permission import (
    # grant_access,
    grant_multi_accesses
)
from governance.services.session import create_app_session
from governance.utils.cache import handle_cache
from governance.error_handling.base import AppError

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
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="A PostgreSQL superuser is required "
                           "for this workflow.",
                )
        # TODO: Validate whether the DB is registered in datalang DB or not
        # TODO: Validate whether a CDC connector is already set here (enabled)
    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not connect to PostgreSQL. Error: {e}",
        )
    except HTTPException:
        raise

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
    try:
        cache = handle_cache(request)
        credentials = cache.holder
        rows = read_wal(credentials)
        return rows
    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e


@database_router.post("/config/wal/update")
def update_wal(request: Request, wal_settings: WALSettings):
    try:
        cache = handle_cache(request)
        credentials = cache.holder
        result = config_wal(credentials, wal_settings)
        return result
    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e


# @database_router.post("/user/grant")
# def grant_user_access(
#     request: Request,
#     grant_request: GrantRequest,
# ):
#     try:
#         cache = handle_cache(request)
#         credentials = cache.holder
#         grant_access(credentials, grant_request)
#     except AppError as e:
#         raise HTTPException(
#             status_code=e.status_code,
#             detail=e.message,
#         ) from e
#
#
# @database_router.post("/user/grant/multi")
# def grant_user_accesses(
#     request: Request,
#     grant_request: GrantRequestMultiObj,
# ):
#     try:
#         cache = handle_cache(request)
#         credentials = cache.holder
#         grant_access(credentials, grant_request)
#     except AppError as e:
#         raise HTTPException(
#             status_code=e.status_code,
#             detail=e.message,
#         ) from e


@database_router.post("/user/grant/multi/cdc_default")
def grant_cdc_user_accesses(
    request: Request,
    cdc_user: CDCUser,
    schema_objnames: GrantSchemaObjnamesRequest
):
    try:
        cache = handle_cache(request)
        credentials = cache.holder

        grant_requests = create_grant_req_multi_obj(
            grantee=cdc_user.name,
            mapped_priv_obj={
                GrantObject.DATABASE: GrantObjectConfig(
                    privileges=[GrantPrivilege.CONNECT],
                    object_names=credentials.database
                ),
                GrantObject.SCHEMA: GrantObjectConfig(
                    privileges=[GrantPrivilege.USAGE],
                    object_names=schema_objnames.schema_name
                ),
                GrantObject.TABLE: GrantObjectConfig(
                    privileges=[GrantPrivilege.SELECT],
                    object_names=schema_objnames.objnames,
                    schema_name=schema_objnames.schema_name
                )
            }
        )
        # TODD: complete the permission.py
        grant_multi_accesses(credentials, grant_requests)

    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        ) from e


@database_router.post("local/user/create")
def create_local_userlogin(request: Request, cdc_user: CDCUser):
    try:
        cache = handle_cache(request)
        credentials = cache.holder
        # TODO: Add cdc user and db info to datalang DB
        return
    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e


@database_router.post("/replication/user/create")
def create_replication_userlogin(request: Request, cdc_user: CDCUser):
    try:
        cache = handle_cache(request)
        credentials = cache.holder
        create_replication_user(credentials, cdc_user)
    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e


@database_router.post("/replication/publication/create")
def create_publication_repuser(request: Request, cdc_user: CDCUser):
    try:
        cache = handle_cache(request)
        credentials = cache.holder
        # TODO: Complete create_publication
    except AppError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e


# Add manage DB options

# View DBs

# Del a DB

# Move connectors

# 5. Create or reconcile the dedicated CDC role.
# 6. Validate selected tables and apply minimal grants.
# 7. Create or reconcile the publication.
# 8. Register the connector and verify task status.
# 9. Persist an audit record and build the summary.
