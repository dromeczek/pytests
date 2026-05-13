# Slim EPC v2 — Code Walkthrough

> A study guide for the `slim_epc_v2` repository.
>
> **Goal:** by the end of this document you should understand every moving part well enough to design unit tests on your own.

---

## Table of contents

1. [What is this application?](#1-what-is-this-application)
2. [Technology stack](#2-technology-stack)
3. [Repository layout](#3-repository-layout)
4. [High-level architecture](#4-high-level-architecture)
5. [Module-by-module deep dive](#5-module-by-module-deep-dive)
   - [5.1 `epc/models.py` — Pydantic data contracts](#51-epcmodelspy--pydantic-data-contracts)
   - [5.2 `epc/db.py` — the SQLite repository](#52-epcdbpy--the-sqlite-repository)
   - [5.3 `epc/traffic.py` — async traffic simulation](#53-epctrafficpy--async-traffic-simulation)
   - [5.4 `epc/api.py` — FastAPI router and endpoints](#54-epcapipy--fastapi-router-and-endpoints)
   - [5.5 `main.py` — application composition](#55-mainpy--application-composition)
6. [End-to-end request flows (short form)](#6-end-to-end-request-flows-short-form)
7. [FastAPI TestClient quick note](#7-fastapi-testclient-quick-note)
8. [Testing clues](#8-testing-clues)

---

## 1. What is this application?

A **toy simulator of an EPC** (Evolved Packet Core).

In a real LTE network, the EPC is the “brain” that tracks which devices (called **UEs** — User Equipment) are connected, what data flows (called **bearers**) they have open, and how much traffic flows on each.

This repository is **not** a real network function. It is a small HTTP service that:

- attaches / detaches UEs (IDs `1..100`),
- adds / removes bearers for a UE (IDs `1..9`),
- starts / stops a fake traffic flow on a bearer at a chosen rate (`Mbps`, `kbps`, or `bps`),
- counts simulated bytes in a background loop so throughput statistics can be read back,
- exposes everything as a REST API documented automatically via OpenAPI/Swagger.

There is no real packet generation, no `iperf`, no networking — the whole “traffic” is a Python coroutine that increments two integers (`bytes_tx`, `bytes_rx`) on a timer.

---

## 2. Technology stack

| Layer | Tool |
|---|---|
| Language | **Python 3.12** (pinned via `requires-python = "==3.12.*"`) |
| Web framework | **FastAPI** 0.110.x |
| ASGI server | **Uvicorn** 0.29.x |
| Data validation | **Pydantic v2** (transitive dependency of FastAPI) |
| Storage | **SQLite** via the `sqlite3` standard library module |
| Concurrency | `asyncio` running in a **dedicated background thread** + `concurrent.futures.Future` |
| Packaging | **uv** (Astral’s fast resolver, used in the Dockerfile) |
| Containerisation | `Dockerfile` based on `python:3.12-slim` |

There is no ORM. Database access is hand-rolled with the standard `sqlite3` module — a deliberate “slim” choice that makes everything visible.

---

## 3. Repository layout

```
slim_epc_v2/
├── main.py                # FastAPI app instance, wiring, lifecycle hooks
├── epc/                   # Application package
│   ├── api.py             # HTTP layer: APIRouter + endpoint handlers
│   ├── db.py              # Persistence layer: EPCRepository (SQLite)
│   ├── models.py          # Pydantic models: data + request/response schemas
│   └── traffic.py         # Background async traffic generator
├── pyproject.toml         # Project metadata + dependencies
├── ruff.toml              # Linting rules
├── Dockerfile             # Container image
└── README.md              # User-facing docs
```

---

## 4. High-level architecture

The codebase is organised in **three layers**:

```
   ┌────────────────────────────────────┐
   │   HTTP layer   (epc/api.py)        │   ← FastAPI router, validation,
   │                                    │     turning ValueError → HTTP 400
   └──────────────────┬─────────────────┘
                      │ uses
                      ▼
   ┌────────────────────────────────────┐
   │   Domain + persistence             │
   │   (epc/db.py, epc/models.py)       │   ← Pydantic models = the data
   │                                    │     EPCRepository = the storage
   └──────────────────┬─────────────────┘
                      │ used by
                      ▼
   ┌────────────────────────────────────┐
   │   Background traffic engine        │
   │   (epc/traffic.py)                 │   ← async coroutine in its own
   │                                    │     thread, mutates DB via repo
   └────────────────────────────────────┘
```

The **only state** lives in:

1. **SQLite** (`epc.db` by default, overridable via `EPC_DB_PATH`) — UE/bearer/stats records persisted across restarts.
2. **In-memory dict** `TrafficGeneratorManager.tasks` — maps `(ue_id, bearer_id)` to a running `Future`. **Not persisted**: after a restart, bearers may be marked `active=True` in SQLite but nothing is actually running.

Two **module-level singletons** glue everything together:

- `_repo_singleton` in `epc/api.py`, returned by `get_repo()` and injected via `Depends`.
- `traffic_manager` in `epc/traffic.py`, returned by `get_traffic_manager(repo)`.

---

## 5. Module-by-module deep dive

### 5.1 `epc/models.py` — Pydantic data contracts

`epc/models.py` contains two groups:

- **Domain state**: `UEState`, `BearerConfig`, `ThroughputStats`.
- **HTTP schemas**: `AttachUERequest`, `AddBearerRequest`, `StartTrafficRequest`, and response models.

Key points:

- `ue_id` is constrained to `1..100`, `bearer_id` to `1..9`.
- Protocol is constrained to `tcp|udp`.
- `StartTrafficRequest` enforces exactly one of `Mbps/kbps/bps`, then normalizes to canonical `target_bps`.
- Throughput in API responses is computed from byte counters and elapsed duration:
  - `tx_bps = bytes_tx * 8 / duration`
  - `rx_bps = bytes_rx * 8 / duration`
- `UEState` is the aggregate serialized as one JSON document in SQLite.

Key code entry:

```45:63:epc/models.py
class StartTrafficRequest(BaseModel):
    protocol: str = Field(pattern="^(tcp|udp)$")
    Mbps: float | None = None
    kbps: float | None = None
    bps: float | None = None

    @model_validator(mode="after")
    def exactly_one_throughput(self):
        provided = [v for v in [self.Mbps, self.kbps, self.bps] if v is not None]
        if len(provided) != 1:
            raise ValueError("Provide exactly one throughput value (Mbps, kbps, or bps)")
        return self

    def target_bps(self) -> int:
        if self.Mbps is not None:
            return int(self.Mbps * 1_000_000)
        if self.kbps is not None:
            return int(self.kbps * 1_000)
        return int(self.bps or 0)
```

---

### 5.2 `epc/db.py` — the SQLite repository

`epc/db.py` implements `EPCRepository` on top of one SQLite table:

- Table `ue_state(ue_id PRIMARY KEY, data TEXT)`.
- `data` is JSON (`UEState.model_dump_json()` / `model_validate_json()`).
- Each operation opens a fresh SQLite connection; commits/rollbacks are handled by the context manager.

Important repository rules:

- Attaching a UE auto-creates default bearer `9`.
- Bearer `9` cannot be deleted.
- Repository raises `ValueError` for domain errors (`UE not found`, duplicates, missing bearer).
- API layer maps those exceptions to HTTP 400.

Key code entries:

```45:54:epc/db.py
def attach_ue(self, ue_id: int) -> None:
    if self.ue_exists(ue_id):
        raise ValueError("UE already attached")
    state = UEState(ue_id=ue_id)
    state.bearers[9] = BearerConfig(bearer_id=9)
    with self._conn() as c:
        c.execute(
            "INSERT INTO ue_state (ue_id, data) VALUES (?, ?)",
            (ue_id, state.model_dump_json()),
        )
```

```99:107:epc/db.py
def delete_bearer(self, ue_id: int, bearer_id: int) -> None:
    if bearer_id == 9:
        raise ValueError("Cannot remove default bearer")
    state = self.get_ue(ue_id)
    if bearer_id not in state.bearers:
        raise ValueError("Bearer not found")
    state.bearers.pop(bearer_id, None)
    state.stats.pop(bearer_id, None)
    self.save_ue(state)
```

---

### 5.3 `epc/traffic.py` — async traffic simulation

`epc/traffic.py` handles simulated throughput updates:

- Creates one background asyncio loop in a daemon thread.
- `TrafficGeneratorManager.start()` schedules one coroutine per `(ue_id, bearer_id)`.
- The coroutine runs every second and increments both `bytes_tx` and `bytes_rx` by `target_bps / 8`.
- `stop()` and `stop_all()` cancel scheduled futures.
- `is_running()` checks task presence in the manager map.

Design note:

- Traffic runtime state (running tasks) is in memory only.
- Persisted stats are in SQLite.

Key code entries:

```27:43:epc/traffic.py
async def _run_simulated_bearer(self, ue_id: int, bearer_id: int, target_bps: int, protocol: str):
    interval = 1.0  # seconds per update
    bytes_per_interval = int(target_bps / 8 * interval)  # convert bps to bytes/sec
    while True:
        state = self.repo.get_ue(ue_id)
        stats = state.stats.get(bearer_id)
        if not stats:
            stats = ThroughputStats(bearer_id=bearer_id, ue_id=ue_id, start_ts=time.time())
        if stats.start_ts is None:
            stats.start_ts = time.time()
        stats.last_update_ts = time.time()
        stats.bytes_tx += bytes_per_interval
        stats.bytes_rx += bytes_per_interval
        stats.protocol = protocol
        stats.target_bps = target_bps
        self.repo.update_stats(ue_id, stats)
        await asyncio.sleep(interval)
```

```45:56:epc/traffic.py
def start(self, ue_id: int, bearer: BearerConfig):
    key = (ue_id, bearer.bearer_id)
    if key in self.tasks:
        raise ValueError("Traffic already running")
    if not bearer.target_bps or not bearer.protocol:
        raise ValueError("Bearer not configured for traffic")
    future = asyncio.run_coroutine_threadsafe(
        self._run_simulated_bearer(ue_id, bearer.bearer_id, bearer.target_bps, bearer.protocol),
        _traffic_loop,
    )
    self.tasks[key] = future
```

---

### 5.4 `epc/api.py` — FastAPI router and endpoints

`epc/api.py` is the HTTP layer:

- Declares FastAPI routes in `router`.
- Injects `EPCRepository` via `Depends(get_repo)`.
- Converts repository `ValueError` to `HTTPException(status_code=400)`.
- Uses Pydantic request/response models to enforce schema and produce OpenAPI docs.

Important behavior:

- Validation failures are mainly **422**.
- Domain-rule failures are mainly **400**.
- `/ues/stats` supports `ue_id` filter and optional detail output.
- `/ues/stats` is declared before `/ues/{ue_id}` to avoid routing ambiguity.

Key code entries:

```30:35:epc/api.py
def get_repo() -> EPCRepository:
    global _repo_singleton
    if _repo_singleton is None:
        _repo_singleton = EPCRepository()
    return _repo_singleton
```

```84:90:epc/api.py
@router.post("/ues", response_model=AttachResponse)
def attach_ue(body: AttachUERequest, repo: Annotated[EPCRepository, Depends(get_repo)]):
    try:
        repo.attach_ue(body.ue_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AttachResponse(status="attached", ue_id=body.ue_id)
```

---

### 5.5 `main.py` — application composition

`main.py` wires the app:

- Creates `FastAPI` application and docs endpoints.
- Includes `epc.api.router`.
- Exposes `/` health message endpoint.
- On shutdown, calls `tm.stop_all()` to cancel running traffic tasks cleanly.

Key code entry:

```7:25:main.py
app = FastAPI(
    title="Simple EPC Simulator",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)
app.include_router(router)


@app.get("/")
async def root():
    return {"message": "EPC Simulator running"}


@app.on_event("shutdown")
def shutdown_event():
    repo = EPCRepository()
    tm = get_traffic_manager(repo)
    tm.stop_all()
```

---

## 6. End-to-end request flows (short form)

Compact endpoint map (CRUD + handler + effect):

| CRUD | Method | Endpoint | Handler | Effect |
|---|---|---|---|---|
| Read | `GET` | `/ues` | `list_ues` | Returns attached UE IDs. |
| Create | `POST` | `/ues` | `attach_ue` | Creates UE row and default bearer `9`. |
| Read | `GET` | `/ues/{ue_id}` | `get_ue` | Returns full UE state (bearers + stats). |
| Delete | `DELETE` | `/ues/{ue_id}` | `detach_ue` | Removes UE row. |
| Create | `POST` | `/ues/{ue_id}/bearers` | `add_bearer` | Adds bearer under UE. |
| Delete | `DELETE` | `/ues/{ue_id}/bearers/{bearer_id}` | `delete_bearer` | Removes bearer and its stats (except bearer `9`). |
| Create | `POST` | `/ues/{ue_id}/bearers/{bearer_id}/traffic` | `start_traffic` | Activates bearer traffic and starts stats updates. |
| Delete | `DELETE` | `/ues/{ue_id}/bearers/{bearer_id}/traffic` | `stop_traffic` | Stops stats updates and deactivates bearer. |
| Read | `GET` | `/ues/{ue_id}/bearers/{bearer_id}/traffic` | `get_traffic_stats` | Computes throughput from bytes/time. |
| Read | `GET` | `/ues/stats` | `get_ues_stats` | Aggregates stats globally or per UE. |
| Delete | `POST` | `/reset` | `reset_all` | Stops all traffic and clears UE data. |

Quick notes:

- `422` is mainly request validation/schema failures.
- `400` is mainly domain-rule failures from repository checks.
- `/ues/stats` must stay above `/ues/{ue_id}` in route declaration order.

---

## 7. FastAPI TestClient quick note

For synchronous HTTP tests, use FastAPI’s in-process client:

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
resp = client.get("/ues")
assert resp.status_code == 200
```

Recommended pattern:

- Use `TestClient` for endpoint-level tests (`status_code`, response JSON, and state transitions).
- Override repository dependency for isolated DB data:
  - `app.dependency_overrides[get_repo] = lambda: test_repo`
- Clear dependency overrides in teardown/fixture cleanup to avoid test leakage.

---

## 8. Testing clues

Treat this as a checklist of **areas** to cover, not a required test list.

1. **Request validation**
   - Invalid UE and bearer ID ranges.
   - Invalid traffic payload shape (protocol/unit combinations).
2. **Repository behavior**
   - Attach/detach lifecycle.
   - Default bearer `9` creation and protection.
   - Add/remove bearer and unknown-entity handling.
3. **Endpoint contracts**
   - Happy-path responses for main routes.
   - Consistent error status behavior (`400` vs `422`).
   - Response body shape for `/ues`, `/ues/{ue_id}`, `/ues/stats`, and traffic stats.
4. **State transitions**
   - Attach -> add bearer -> start -> read -> stop -> detach.
   - Reset restores a clean state.
5. **Edge conditions**
   - Duplicate attach / duplicate bearer.
   - Removing missing bearer.
   - Route specificity around `/ues/stats` vs `/ues/{ue_id}`.

Focus on regular sync pytest tests around repository and HTTP behavior; **no special async test setup is required**.

---
