# Indonesia Shipping Intelligence — Static Dashboard

Live: https://moon470an-sys.github.io/Indonesia-Shipping-Intelligence/

This folder is deployed as-is by GitHub Pages. JSON snapshots in `data/`
are rebuilt monthly from the SQLite ingestion DB:

```
python -m backend.build_static
```
