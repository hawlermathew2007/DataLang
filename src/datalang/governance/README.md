Setup datalang db

```
uv run -m governance.services.db.setup
```

Run:

```
uv run -m governance.main
```

Go to localhost:8000/docs and play around.

TODO: Password data type may need to be change (current: str)
