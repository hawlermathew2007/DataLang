from pydantic import BaseModel

# we might need a list string here


class DatabaseCredentials(BaseModel):
    database: str = "template0"
    username: str = "postgres"
    password: str = "postgres"
    hostname: str = "localhost"
    port: int = 5432


class WALSettings(BaseModel):
    wal_level: str = "logical"
    max_wal_size: str = "1024MB"
    min_wal_size: str = "80MB"
    wal_keep_size: str = "0MB"
    max_slot_wal_keep_size: str = "-1MB"

    max_replication_slots: int = 10
    max_wal_senders: int = 10
    wal_sender_timeout: str = "60s"

    checkpoint_completion_target: float = 0.9
    wal_buffers: str = "4MB"
    track_commit_timestamp: bool = False
