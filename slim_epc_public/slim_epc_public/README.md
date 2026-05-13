# Simple EPC Simulator

A minimal Evolved Packet Core (EPC) simulator with FastAPI, SQLite and simulated traffic generation.

## Features
- Attach / detach UE (IDs 1-100)
- Add bearer (IDs 1-9)
- Start / stop simulated throughput (TCP/UDP, set via Mbps/kbps/bps)
- Query throughput stats per bearer
- Aggregate stats across UEs or one UE (`/ues/stats`)
- Display UE state
- List attached UEs
- Reset all state

## API (REST-style)

Resource IDs are in the URL path; request bodies use JSON where needed.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Service check (`{"message": "EPC Simulator running"}`) |
| GET | `/ues` | List attached UE IDs |
| POST | `/ues` | Attach UE (body: `{"ue_id": <1-100>}`) |
| GET | `/ues/{ue_id}` | Get UE state (bearers, stats) |
| DELETE | `/ues/{ue_id}` | Detach UE |
| POST | `/ues/{ue_id}/bearers` | Add bearer (body: `{"bearer_id": <1-9>}`) |
| DELETE | `/ues/{ue_id}/bearers/{bearer_id}` | Delete bearer |
| POST | `/ues/{ue_id}/bearers/{bearer_id}/traffic` | Start simulated traffic (JSON: `protocol` is `"tcp"` or `"udp"`; include exactly one of `Mbps`, `kbps`, or `bps`) |
| DELETE | `/ues/{ue_id}/bearers/{bearer_id}/traffic` | Stop traffic |
| GET | `/ues/{ue_id}/bearers/{bearer_id}/traffic` | Get throughput stats |
| GET | `/ues/stats` | Aggregate stats (query: `?ue_id=<int>&include_details=true` optional) |
| POST | `/reset` | Reset all state |

Traffic is always simulated in-process (async loop updating byte counters); there is no separate “live” traffic mode in the API.

## Interactive API documentation (OpenAPI)

The app is built with FastAPI, which exposes the schema and two UIs (enabled in `main.py`):

| URL | Purpose |
|-----|---------|
| [http://localhost:8000/docs](http://localhost:8000/docs) | **Swagger UI** — try endpoints, see request/response models |
| [http://localhost:8000/redoc](http://localhost:8000/redoc) | **ReDoc** — read-only reference layout |
| [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json) | Raw **OpenAPI 3** JSON (for codegen or other tools) |

Use the same host/port as your server (e.g. inside Docker, replace `localhost` with the host that maps to port 8000).

## Storage

State is stored in SQLite. The database file is created automatically.

- **Default path:** `epc.db` in the current working directory.
- **Override:** set `EPC_DB_PATH` (e.g. `EPC_DB_PATH=/data/epc.db` in Docker for a persistent volume).

## Running

### Local

Python **3.12** is required (`requires-python` in `pyproject.toml`).

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```
Service at `http://localhost:8000`.

### Docker (single container)

No Docker Compose is required; SQLite uses a file inside the container.

```bash
docker build -t epc-sim .
docker run -p 8000:8000 -v epc-data:/data -e EPC_DB_PATH=/data/epc.db epc-sim
```
Use the volume `epc-data` to persist the database across container restarts.

## Example
```bash
curl -X POST http://localhost:8000/ues -H "Content-Type: application/json" -d '{"ue_id": 1}'
curl -X POST http://localhost:8000/ues/1/bearers -H "Content-Type: application/json" -d '{"bearer_id": 1}'
curl -X POST http://localhost:8000/ues/1/bearers/1/traffic -H "Content-Type: application/json" -d '{"protocol": "tcp", "Mbps": 1}'
curl -X GET http://localhost:8000/ues/1
curl -X GET http://localhost:8000/ues/stats
```

## Tests
```bash
uv sync --group dev
uv run pytest -q
```
Tests use a temporary SQLite file per test app instance (see `tests/test_epc.py`), not the default `epc.db` in the project directory.

## Notes
Traffic is simulated with an asyncio loop updating counters in SQLite, representing both UL and DL directions.
