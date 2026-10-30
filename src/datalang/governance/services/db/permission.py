from governance.schemas.permission import (
    GrantRequest,
    GrantRequestMultiObj,
    GrantPrivilege,
    GrantObject
)


def grant_access(
    db_session,
    grant_request: GrantRequest
):
    pass


def grant_multi_accesses(
    db_session,
    grant_request: GrantRequestMultiObj
):
    pass


def apply_column_filters():
    pass


def view_user_grant_privilege(
    username: str,
    grant_privileges: list[GrantPrivilege],
    grant_objnames: list[GrantObject]
):
    pass
