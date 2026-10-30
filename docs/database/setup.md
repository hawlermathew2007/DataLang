## Set up PostgreSQL DB with northwind sample

Go to `src/datalang/backend/database/samples/northwind`, open PostgreSQL shell:

```
# Install PostgreSQL if don't have:
sudo apt update
sudo apt install postgresql postgresql-contrib -y

# Check status to make postgresql is active
systemctl status postgresql

# If not:
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Access psql shell
sudo -i -u postgres
psql
```

Make sure u in the sample directory that have northwind sample. Now load northwind sample to postgresql db.

```
# Create home directory for postgresql
sudo su
cd /home
mdkir postgres
exit

sudo -i -u postgres
cd /home/postgres
mkdir -p Documents/sample/northwind && cd $_
exit

sudo su
cd /home/postgres/Documents/sample/northwind/
cp -r $USER/projects/DataLang/src/datalang/backend/databases/samples/northwind/* .  # Custom your directory to ger .sql files
sudo chown postgres:postgres *
exit

sudo -i -u postgres
cd Documents/sample/northwind
psql
```

In the shell, run:

```
northwind=# \c northwind
northwind=# \i northwind_ddl.sql
northwind=# \d
                 List of relations
 Schema |          Name          | Type  |  Owner   
--------+------------------------+-------+----------
 public | categories             | table | postgres
 public | customer_customer_demo | table | postgres
 public | customer_demographics  | table | postgres
 public | customers              | table | postgres
 public | employee_territories   | table | postgres
 public | employees              | table | postgres
 public | order_details          | table | postgres
 public | orders                 | table | postgres
 public | products               | table | postgres
 public | region                 | table | postgres
 public | shippers               | table | postgres
 public | suppliers              | table | postgres
 public | territories            | table | postgres
 public | us_states              | table | postgres
(14 rows)
northwind=# \i northwind_data.sql
northwind=# select count(*) from customers;
 count 
-------
    91
(1 row)
```

For more sample or u just wanna know where the hell I got the sample, download the [Yugabyte](https://docs.yugabyte.com/stable/quick-start/linux/) to get samples within.

## Configuration

At PostgreSQL client (psql)

```
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW config_file;
```

At `postgresql.conf` gotten by the directory from `SHOW config_file;`, modify:

```
wal_level = logical
max_replication_slots = 10
max_wal_senders = 10
listen_addresses="*"
```

At `pg_hba.conf` gotten by the directory from `SHOW hba_file;`, add:

```
host    northwind    debezium_user      172.18.0.0/16           scram-sha-256
```

Restart DB if needed. We need pay attention to this and other configs in postgres to make it to production ig.

```
max_wal_size = 1GB
min_wal_size = 80MB
```

## Create dedicated users

Run as PostgreSQL admin and add debezium user. Use your custom password.

```
CREATE ROLE debezium_user
    WITH LOGIN REPLICATION
    PASSWORD 'debezium';
```

Check new user info:

```
# Check
postgres=# SELECT usename, usecreatedb, usesuper FROM pg_catalog.pg_user;
    usename    | usecreatedb | usesuper 
---------------+-------------+----------
 postgres      | t           | t
 debezium_user | f           | f
(2 rows)

SELECT rolname, rolcanlogin, rolreplication
FROM pg_roles
WHERE rolname = 'debezium_user';
    rolname    | rolcanlogin | rolreplication 
---------------+-------------+----------------
 debezium_user | t           | t
```

Grant access to the database that contains sample tables:

```
GRANT CONNECT ON DATABASE northwind TO debezium_user;
```

Connect to "northwind" and grant access to the schema and table that is used to capture:

```
GRANT USAGE ON SCHEMA public TO debezium_user;

GRANT SELECT ON ALL TABLES IN SCHEMA public
    TO debezium_user;

# Check
SELECT
    has_database_privilege(
        'debezium_user', 'northwind', 'CONNECT'
    ) AS can_connect;

SELECT
    has_table_privilege(
        'debezium_user',
        'public.categories',
        'SELECT'
    ) AS categories_select,
    has_table_privilege(
        'debezium_user',
        'public.orders',
        'SELECT'
    ) AS orders_select;
```

## Create a publication

Do this if you set `publication.autocreate.mode` to be `disable`, this would be better:

```
CREATE PUBLICATION db_test_publication
FOR TABLE
    public.categories,
    public.customer_customer_demo,
    public.customer_demographics,
    public.customers,
    public.employee_territories,
    public.employees,
    public.order_details,
    public.orders,
    public.products,
    public.region,
    public.shippers,
    public.suppliers,
    public.territories,
    public.us_states;

# OR, probably bad ideas

CREATE PUBLICATION db_test_publication
    FOR ALL TABLES;
```

Check:

```
SELECT pubname, puballtables
FROM pg_publication;

SELECT schemaname, tablename
FROM pg_publication_tables
WHERE pubname = 'db_test_publication';
```

## Transfer ownership

Do this if you set `publication.autocreate.mode` to be `filtered`:

```
ALTER TABLE public.categories OWNER TO debezium_user;
ALTER TABLE public.customer_customer_demo OWNER TO debezium_user;
ALTER TABLE public.customer_demographics OWNER TO debezium_user;
ALTER TABLE public.customers OWNER TO debezium_user;
ALTER TABLE public.employee_territories OWNER TO debezium_user;
ALTER TABLE public.employees OWNER TO debezium_user;
ALTER TABLE public.order_details OWNER TO debezium_user;
ALTER TABLE public.orders OWNER TO debezium_user;
ALTER TABLE public.products OWNER TO debezium_user;
ALTER TABLE public.region OWNER TO debezium_user;
ALTER TABLE public.shippers OWNER TO debezium_user;
ALTER TABLE public.suppliers OWNER TO debezium_user;
ALTER TABLE public.territories OWNER TO debezium_user;
ALTER TABLE public.us_states OWNER TO debezium_user;
```
