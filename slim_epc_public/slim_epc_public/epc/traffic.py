import asyncio
import threading
import time
from concurrent.futures import Future

from .models import BearerConfig, ThroughputStats
from .db import EPCRepository

# Dedicated background asyncio loop for traffic tasks (works inside test threadpool)
_traffic_loop = asyncio.new_event_loop()


def _run_background_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


_traffic_thread = threading.Thread(target=_run_background_loop, args=(_traffic_loop,), daemon=True)
_traffic_thread.start()


class TrafficGeneratorManager:
    def __init__(self, repo: EPCRepository):
        self.repo = repo
        self.tasks: dict[tuple[int, int], Future] = {}

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

    def stop(self, ue_id: int, bearer_id: int):
        key = (ue_id, bearer_id)
        future = self.tasks.get(key)
        if future:
            future.cancel()
            del self.tasks[key]

    def stop_all(self):
        for key, future in list(self.tasks.items()):
            future.cancel()
            del self.tasks[key]

    def is_running(self, ue_id: int, bearer_id: int) -> bool:
        return (ue_id, bearer_id) in self.tasks


traffic_manager: TrafficGeneratorManager | None = None


def get_traffic_manager(repo: EPCRepository) -> TrafficGeneratorManager:
    global traffic_manager
    if traffic_manager is None:
        traffic_manager = TrafficGeneratorManager(repo)
    return traffic_manager
