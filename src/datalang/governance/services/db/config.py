from sqlalchemy import bindparam, text
from governance.schemas.database import WALSettings
from pint import UnitRegistry

ALLOWED_WAL_SETTINGS = (
    "wal_level",
    "max_wal_size",
    "min_wal_size",
    "wal_keep_size",
    "max_slot_wal_keep_size",
    "max_replication_slots",
    "max_wal_senders",
    "wal_sender_timeout",
    "idle_replication_slot_timeout",
    "checkpoint_completion_target",
    "wal_buffers",
    "track_commit_timestamp",
)

ureg = UnitRegistry()


def wal_values_match(name: str, requested: str, current: dict) -> bool:
    setting = current["setting"]
    unit = current["unit"]

    if unit is None:
        return str(setting).lower() == str(requested).lower()

    try:
        current_value = float(setting) * ureg(unit)
        requested_value = ureg(requested)

        return current_value.to_base_units() == requested_value.to_base_units()
    except (ValueError, TypeError, ureg.UndefinedUnitError):
        return str(setting) == str(requested)  # questionable...


def read_wal(db_session) -> list[dict]:
    query = text("""
        SELECT name, setting, unit, context, pending_restart
        FROM pg_settings
        WHERE name IN :names
        ORDER BY name
    """).bindparams(
        # Expands the tuple into individual SQL parameters.
        bindparam("names", expanding=True)
    )

    rows = db_session.execute(
        query, {"names": ALLOWED_WAL_SETTINGS}
    ).mappings().all()

    return [dict(row) for row in rows]


def config_wal(engine, config: WALSettings):
    changes = []

    settings = config.model_dump(exclude_none=True)

    with engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        before = read_wal(conn)
        before_dict = {item["name"]: item for item in before}

        for name, value in settings.items():
            if name not in ALLOWED_WAL_SETTINGS:
                continue

            current = before_dict.get(name)

            if current and wal_values_match(name, str(value), current):
                continue

            conn.execute(
                text(f"ALTER SYSTEM SET {name} = :value"),
                {"value": str(value)},
            )

            changes.append({
                "setting": name,
                "previous": current["setting"] if current else None,
                "requested": value,
            })

        reload_result = conn.execute(
            text("SELECT pg_reload_conf()")
        ).scalar_one()

        after = read_wal(conn)

    return {
        "before": before,
        "after": after,
        "changes": changes,
        "reload_requested": reload_result,
        "restart_required": any(
            setting.get("pending_restart", False)
            for setting in after
        ),
    }
