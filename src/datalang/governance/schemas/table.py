import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    JSON,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.types import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    connector_class: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    db_tables: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    db_publication: Mapped[str] = mapped_column(
        String(63),  # PostgreSQL identifiers are limited to 63 bytes
        nullable=False,
    )
    db_replication_slot: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
    )
    kafka_topic_prefix: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="not_registered",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    db: Mapped["Database"] = relationship(back_populates="connector")


class Database(Base):
    __tablename__ = "databases"
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    db_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    db_host: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    db_port: Mapped[int] = mapped_column(
        Integer,
        default=5432,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("connectors.id"), unique=True)
    connector: Mapped["Connector"] = relationship(back_populates="db", single_parent=True)
