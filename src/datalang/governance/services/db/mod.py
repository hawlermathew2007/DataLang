from psycopg2 import sql


def grant_table_access(
    conn,
    username: str,
    schema_name: str,
    table_names: list[str],
):
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema_name),
                sql.Identifier(username),
            )
        )

        for table_name in table_names:
            cur.execute(
                sql.SQL(
                    "GRANT SELECT ON TABLE {}.{} TO {}"
                ).format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(username),
                )
            )

    conn.commit()


def validate_tables(conn, schema_name, table_names):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = %s
            """,
            (schema_name,),
        )

        existing = {row[0] for row in cur.fetchall()}

    missing = set(table_names) - existing

    if missing:
        raise ValueError(
            f"Tables not found in schema {schema_name!r}: "
            f"{sorted(missing)}"
        )


def create_publication(
    conn,
    publication_name: str,
    schema_name: str,
    table_names: list[str],
):
    if not table_names:
        raise ValueError("At least one table is required")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM pg_publication
            WHERE pubname = %s
            """,
            (publication_name,),
        )

        if cur.fetchone():
            raise ValueError(
                f"Publication {publication_name!r} already exists; "
                "inspect and reconcile it explicitly"
            )

        table_identifiers = [
            sql.SQL("{}.{}").format(
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
            )
            for table_name in table_names
        ]

        statement = sql.SQL(
            "CREATE PUBLICATION {} FOR TABLE {}"
        ).format(
            sql.Identifier(publication_name),
            sql.SQL(", ").join(table_identifiers),
        )

        cur.execute(statement)

    conn.commit()
