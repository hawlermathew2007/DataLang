import uuid
from enum import Enum
from pydantic import BaseModel, Field


class ConnectorClass(Enum):
    Postgres = "io.debezium.connector.postgresql.PostgresConnector"
    MySQL = ""


# Role and user will both be created (separation may be needed)
class CDCUser(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = "debezium_user"
    password: str = "debezium_user_secret"
    classname: ConnectorClass
    tables: list
