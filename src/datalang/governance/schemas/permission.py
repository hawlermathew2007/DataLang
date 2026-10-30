from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union


class GrantPrivilege(str, Enum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    CONNECT = "CONNECT"
    CREATE = "CREATE"
    USAGE = "USAGE"


class GrantObject(str, Enum):
    DATABASE = "DATABASE"
    SCHEMA = "SCHEMA"
    SEQUENCE = "SEQUENCE"
    TABLE = "TABLE"
    ALL_TABLES = "ALL TABLES IN SCHEMA"


class GrantObjectConfig(BaseModel):
    privileges: List[GrantPrivilege]
    object_names: Union[List[str], str]
    schema_name: Optional[str] = None


class GrantRequest(BaseModel):
    privileges: List[GrantPrivilege]
    object_type: GrantObject
    object_names: Union[List[str], str]
    grantee: str
    schema_name: Optional[str] = None


class GrantRequestMultiObj(BaseModel):
    grants: List[GrantRequest]
    grantee: str


class GrantSchemaObjnamesRequest(BaseModel):
    objnames: Union[List[str], str]
    schema_name: str = "public"


def create_grant_req_multi_obj(
    grantee: str,
    mapped_priv_obj: Dict[GrantObject, GrantObjectConfig]
) -> GrantRequestMultiObj:

    grants = []

    for obj, config in mapped_priv_obj.items():
        grants.append(
            GrantRequest(
                privileges=config.privileges,
                object_type=obj,
                object_names=config.object_names,
                schema_name=config.schema_name,
                grantee=grantee
            )
        )

    return GrantRequestMultiObj(
        grants=grants,
        grantee=grantee
    )
