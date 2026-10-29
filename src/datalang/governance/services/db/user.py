from psycopg2 import sql


def create_replication_user(
    admin_conn,
    database: str,
    username: str,
    password: str,
):
    # This is a privileged operation.
    # Use only an authorized provisioning connection.

    with admin_conn.cursor() as cur:
        cur.execute(
            """
            SELECT rolreplication, rolcanlogin
            FROM pg_roles
            WHERE rolname = %s
            """,
            (username,),
        )
        existing = cur.fetchone()

        if existing is None:
            cur.execute(
                sql.SQL(
                    "CREATE ROLE {} WITH LOGIN REPLICATION PASSWORD %s"
                ).format(sql.Identifier(username)),
                (password,),
            )
        elif not (existing[0] and existing[1]):
            raise ValueError(
                f"Existing role {username!r} does not "
                "have the required LOGIN and REPLICATION attributes"
            )

        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database),
                sql.Identifier(username),
            )
        )

    admin_conn.commit()
