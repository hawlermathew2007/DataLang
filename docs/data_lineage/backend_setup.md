Run:

```
uv run -m lineage.main
```

Check API:

```
curl -s localhost:8000/api/events | python3 -m json.tool
curl -s localhost:8000/api/graph  | python3 -m json.tool
```
