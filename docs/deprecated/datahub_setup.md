## Quick start (advance later ig)

For local access, start DataHub:

```
uv tool install acryl-datahub
datahub docker quickstart --quickstart-compose-file datahub-docker-compose.yml
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
