from fastapi import FastAPI

from epc.api import router
from epc.db import EPCRepository
from epc.traffic import get_traffic_manager

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
