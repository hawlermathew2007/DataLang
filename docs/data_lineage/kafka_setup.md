## Start Kafka Connect (with Kraft mode) and the Debezium connector plugin within

Run Docker Compose
```
docker compose up -d
docker compose logs -f connect
```

Check if Kafka Connect connects with Kafka Broker from DataHub:

```
curl http://localhost:8083/
```

List installed connector:

```
curl -s http://localhost:8083/connector-plugins | python3 -m json.tool
```

Seeing Kafka topics:

```
docker exec -it datahub-kafka-broker-1 sh -c  'echo "$PATH"; ls -la /opt; ls -la /usr/bin/kafka* 2>/dev/null'  # To view program for interacting with broker

docker exec -it datahub-kafka-broker-1 \
  /usr/bin/kafka-topics \   
  --bootstrap-server broker:29092 \
  --list
```

## Register the connector

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

Check status:

```
curl -s \
  http://localhost:8083/connectors/postgres-cdc/status \
  | python3 -m json.tool
```

## Test

List the topics:

```
docker compose exec datahub-kafka-broker-1 \
  kafka-topics \
  --bootstrap-server broker:29092 --list
```

In another terminal, change a row within PostSQL DB so Debezium emits an event.

```
UPDATE orders SET freight = freight + 1
WHERE order_id = (SELECT min(order_id) FROM orders);
```

Consume events from the table topic:

```
docker exec datahub-kafka-broker-1 \
  kafka-console-consumer \
  --bootstrap-server broker:29092 \
  --topic db_test.public.orders \
  --from-beginning
```

1. Confirm that tables are ready
2. Check Kafka topics
3. Test if the stream is real
