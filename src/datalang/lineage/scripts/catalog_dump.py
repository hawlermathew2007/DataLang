"""
Read-only: it only runs SELECT statements against the system catalogs
(plus SELECT count(*) on each table).

Usage:
YB_PASSWORD=yugabyte uv run --with psycopg2-binary lineage/scripts/catalog_dump.py \
  --host 127.0.0.1 --port 5433 --dbname northwind --user yugabyte | cat >> catalog_dump.txt
"""
import argparse
import os
from collections import defaultdict

import psycopg2
from psycopg2 import sql

TABLES_SQL = """
SELECT c.relname, obj_description(c.oid, 'pg_class')
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
ORDER BY c.relname
"""

COLUMNS_SQL = """
SELECT c.relname,
       a.attname,
       format_type(a.atttypid, a.atttypmod),
       NOT a.attnotnull,
       col_description(c.oid, a.attnum)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
ORDER BY c.relname, a.attnum
"""

# contype 'p' = primary key, 'f' = foreign key. Column lists keep their order.
CONSTRAINTS_SQL = """
SELECT con.contype,
       con.conname,
       cl.relname,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum),
       fcl.relname,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum)
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
LEFT JOIN pg_class fcl ON fcl.oid = con.confrelid
WHERE con.contype IN ('p', 'f') AND n.nspname = %s
ORDER BY cl.relname, con.conname
"""


def dataset_urn(dbname, schema, table, platform="postgres", env="PROD"):
    return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{dbname}.{schema}.{table},{env})"


def print_table(headers, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print("  " + line)
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5433)
    ap.add_argument("--dbname", default="northwind")
    ap.add_argument("--user", default="yugabyte")
    ap.add_argument("--schema", default="public")
    ap.add_argument("--platform", default="postgres",
                    help="DataHub platform used in the printed URNs")
    args = ap.parse_args()

    conn = psycopg2.connect(host=args.host, port=args.port, dbname=args.dbname,
                            user=args.user, password=os.getenv("YB_PASSWORD"))
    conn.set_session(readonly=True, autocommit=True)

    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]

        cur.execute(TABLES_SQL, (args.schema,))
        tables = cur.fetchall()

        cur.execute(COLUMNS_SQL, (args.schema,))
        columns = defaultdict(list)
        for table, col, typ, nullable, comment in cur.fetchall():
            columns[table].append((col, typ, nullable, comment))

        cur.execute(CONSTRAINTS_SQL, (args.schema,))
        pks, fks = defaultdict(list), defaultdict(list)
        for contype, name, table, cols, ptable, pcols in cur.fetchall():
            if contype == "p":
                pks[table] = cols
            else:
                fks[table].append((name, cols, ptable, pcols))

        counts = {}
        for table, _ in tables:
            cur.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(args.schema), sql.Identifier(table)))
            counts[table] = cur.fetchone()[0]

    print(f"=== Catalog: {args.dbname} (schema: {args.schema}) ===")
    print(f"Server : {version}")
    print(f"Tables : {len(tables)}\n")

    for table, table_comment in tables:
        print(f"--- {args.schema}.{table} ---")
        print(f"URN     : {dataset_urn(args.dbname, args.schema, table, args.platform)}")
        print(f"Rows    : {counts[table]}")
        print(f"Comment : {table_comment or '-'}")
        rows = [
            (i, col, typ, "YES" if nullable else "NO",
             "PK" if col in pks.get(table, []) else "", comment or "")
            for i, (col, typ, nullable, comment) in enumerate(columns[table], 1)
        ]
        print_table(["#", "column", "type", "nullable", "key", "comment"], rows)
        for name, cols, ptable, pcols in fks.get(table, []):
            print(f"  FK {name}: ({', '.join(cols)}) -> {ptable}({', '.join(pcols)})")
        print()

    print("=== Table-level edges derived from foreign keys (parent -> child) ===")
    edges = sorted({(ptable, table)
                    for table, lst in fks.items()
                    for _, _, ptable, _ in lst if ptable != table})
    for parent, child in edges:
        print(f"  {parent} -> {child}")
    self_refs = sorted({t for t, lst in fks.items() for _, _, p, _ in lst if p == t})
    if self_refs:
        print(f"  (self-references skipped: {', '.join(self_refs)})")


if __name__ == "__main__":
    main()
