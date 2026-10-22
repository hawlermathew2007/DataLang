# Yugabyte
Potentially be gone in the future and get replaced by PostgreSQL since it is a distributed PostgreSQL for microservices and AI native platform kind of ah, so not we do not necessary need it.

View database and tables:

```
SELECT version();
SELECT current_database();

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
```

At ~/var/data/pg_data/ysql_hba.conf (get by `SHOW hba_file;` in ysqlsh), pls remember to config the trust mechanism of yugabyte since it allows any client IP address that can reach the database to connect without a password bruhhhhhhhh.

For temporary change, `ysql_hba.conf`

```
# TYPE    DATABASE        USER            ADDRESS                 METHOD
hostssl   all             all             0.0.0.0/0               scram-sha-256

```

Persistance

```
sudo ./bin/yb-tserver \
  --fs_data_dirs="/var/data" \
  --tserver_master_addrs="127.0.0.1:7100" \
  --rpc_bind_addresses="0.0.0.0:9100" \
  --ysql_hba_conf_csv="host all all 127.0.0.1/32 trust,host all all ::1/128 trust,host all all 0.0.0.0/0 scram-sha-256,host all all ::0/0 scram-sha-256"
```

Also at ~/var/conf/yugabyted.conf set:

```
"ysql_enable_auth": true,
```

Note: I overengineered, since we not gonna use YugabyteDB in the future :)

## Start KafKa Connect and Yugabyte connector plugin

```
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f connect
```

Check REST API and correct plugins:

```
curl -s http://localhost:8083/ | python3 -m json.tool

curl -s http://localhost:8083/connector-plugins \
  | python3 -m json.tool
```

## Register the connector

Create publication

```
CREATE PUBLICATION yb_test_publication FOR TABLE public.categories, public.customer_customer_demo, public.customer_demographics,  public.customers, public.employee_territories, public.employees,  public.order_details, public.orders, public.products, public.region,  public.shippers, public.suppliers, public.territories, public.us_states;
```

Check publication:

```
northwind=# \dRp+
                      Publication yb_test_publication
  Owner   | All tables | Inserts | Updates | Deletes | Truncates | Via root 
----------+------------+---------+---------+---------+-----------+----------
 yugabyte | f          | t       | t       | t       | t         | f
Tables:
    "public.categories"
    "public.customer_customer_demo"
    "public.customer_demographics"
    "public.customers"
    "public.employee_territories"
    "public.employees"
    "public.order_details"
    "public.orders"
    "public.products"
    "public.region"
    "public.shippers"
    "public.suppliers"
    "public.territories"
    "public.us_states"
```

Confirm that the existing sample tables are in the public schema

```
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
```

Suppose u will get this:

```
 table_schema |       table_name       
--------------+------------------------
 public       | categories
 public       | customer_customer_demo
 public       | customer_demographics
 public       | customers
 public       | employee_territories
 public       | employees
 public       | order_details
 public       | orders
 public       | products
 public       | region
 public       | shippers
 public       | suppliers
 public       | territories
 public       | us_states
```

Register:

```
set -a
source .env
set +a

envsubst < register-connector.json |
jq '.config' |
curl -i -X PUT \
  "http://localhost:8083/connectors/${CONNECTOR_NAME}/config" \
  -H "Content-Type: application/json" \
  -d @-
```

View connectors:

```
curl -s http://localhost:8083/connectors
```

Connector status:

```
curl -s \
  http://localhost:8083/connectors/yugabyte-cdc/status \
  | python3 -m json.tool
```

Meaning of Noice

```
{
    "name": "yugabyte-cdc",
    "connector": {
        "state": "RUNNING",
        "worker_id": "null:-1"
    },
    "tasks": [
        {
            "id": 0,
            "state": "RUNNING",
            "worker_id": "null:-1"
        }
    ],
    "type": "source"
}
```

View connectors config:

```
curl -s http://localhost:8083/connectors/yugabyte
-cdc/config \
  | python3 -m json.tool
{
  "connector.class": "io.debezium.connector.postgresql.YugabyteDBConnector",
  "publication.autocreate.mode": "filtered",
  "database.user": "yugabyte",
  "database.dbname": "northwind",
  "slot.name": "yb_test_slot",
  "tasks.max": "1",
  "publication.name": "yb_test_publication",
  "schema.include.list": "public",
  "database.port": "5433",
  "plugin.name": "yboutput",
  "topic.prefix": "yb_test",
  "database.hostname": "127.0.0.1",
  "database.password": "<REDACTED>",
  "name": "yugabyte-cdc",
  "table.include.list": "public.categories,public.customer_customer_demo,public.customer_demographics,public.customers,public.employee_territories,public.employees,public.order_details,public.orders,public.products,public.region,public.shippers,public.suppliers,public.territories,public.us_states",
  "snapshot.mode": "initial"
}
```

## Explore

Check topics:

```
sudo docker compose exec kafka \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list

# OR this to use it everywhere in terminal

sudo docker exec "$(sudo docker ps -q --filter name=kafka | head -n1)" \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
```

Viewing the events stream:

```
sudo docker compose exec kafka \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic yb_test.public.orders \      
  --from-beginning

# OR 

sudo docker exec "$(sudo docker ps -q --filter ancestor=apache/kafka:3.9.1 | head -n1)" \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic yb_test.public.orders \      
  --from-beginning
```

## Troubleshooting

```
docker compose logs --tail=200 connect
curl -s http://localhost:8083/connectors/yugabyte-cdc/status
```

## Source
https://docs.yugabyte.com/stable/integrations/cdc/debezium/

# PostgreSQL

## Start Kafka Connect (with Kraft mode) and the Debezium connector plugin within

```
docker compose up -d
docker compose ps
docker compose logs -f kafka connect
```

Checks:
```
curl http://localhost:8083/
```

List installed connector:
```
curl -s http://localhost:8083/connector-plugins | python3 -m json.tool
```

Seeing Kafka topics:
```
docker compose exec kafka \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:9092 --list
```

## Config PostgreSQL and Yugabyte DB

At PostgreSQL client (psql)

```
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW config_file;
```

At `postgresql.conf`:

```
wal_level = logical
max_replication_slots = 10
max_wal_senders = 10
```

Restart DB if needed.

## Create dedicated 

Run as PostgreSQL admin and add debezium user

```
CREATE ROLE debezium_user
    WITH LOGIN REPLICATION
    PASSWORD 'replace-with-a-strong-secret';
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
```

## Create a publication

```
CREATE PUBLICATION dbz_publication
    FOR TABLE public.users;

# OR

CREATE PUBLICATION dbz_publication
    FOR ALL TABLES;
```

Check:

```
SELECT pubname, puballtables
FROM pg_publication;

SELECT schemaname, tablename
FROM pg_publication_tables
WHERE pubname = 'dbz_publication';
```

## Register the connector

```
curl -i -X POST \
  http://localhost:8083/connectors \
  -H 'Content-Type: application/json' \
  --data @postgres-connector.json
```

Check status:

```
curl -s \
  http://localhost:8083/connectors/postgres-cdc/status \
  | python3 -m json.tool
```

## Test

List the topics:

```
docker compose exec kafka \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:9092 --list
```

Consume events from the table topic:

```
docker compose exec kafka \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic yb_test.public.orders \
  --from-beginning
```

1. Confirm that tables are ready
2. Check Kafka topics
3. Test if the stream is real
