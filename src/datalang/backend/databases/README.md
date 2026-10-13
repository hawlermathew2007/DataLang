## Start YugabyteDB

Download with `./databases/download_yugabytedb.sh` first. Then start:

```
./databases/start_yugabytedb.sh
./databases/connect_yugabytedb.sh
```

Load sample data

```
CREATE DATABASE northwind;
\c northwind
\i share/northwind_ddl.sql
\i share/northwind_data.sql
```

Set up test_users table to store temp credentials to test:

```
uv run setup.py
```

## Source
https://docs.yugabyte.com/stable/develop/sample-data/northwind/
