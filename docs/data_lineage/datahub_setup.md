## Quick start (advance later ig)

For local access, start DataHub:

```
uv tool install acryl-datahub
datahub docker quickstart --quickstart-compose-file datahub-compose.yml
datahub docker check
```

The quickstart needs ports 9002 (web app) and 8080 (GMS). GMS exposes a health endpoint at `/health`

```
curl http://localhost:8080/health
```

Check GMS access:

```
uv run python test_emit.py
```

Run:

```
uv run -m lineage.main
```

## Test 

In another terminal, change a row so Debezium emits an event.

```
UPDATE orders SET freight = freight + 1
WHERE order_id = (SELECT min(order_id) FROM orders);
```

Check API:

```
curl -s localhost:8000/api/events | python3 -m json.tool
curl -s localhost:8000/api/graph  | python3 -m json.tool
```
