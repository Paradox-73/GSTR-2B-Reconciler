"""Worker entry point: python -m api.worker

Jobs run in this process (rq SimpleWorker, no fork per job). A background thread polls the MLflow
registry and swaps the model in place, so a promoted model is used by the next job without a pod
restart (DESIGN.md 9.4). Forking after xgboost and the poller thread have started can deadlock the
child, which is why the default forking worker isn't used.
"""
import os
import threading

from redis import Redis
from rq import SimpleWorker

from api import jobs, logs

POLL_SECONDS = int(os.environ.get("MODEL_POLL_SECONDS", "60"))


def poll(stop: threading.Event) -> None:
    while not stop.wait(POLL_SECONDS):
        jobs.models.refresh()
        try:
            jobs.reap_stuck_runs()
        except Exception:  # a DB blip must not kill the poller thread
            logs.log("reap_failed", 30, exc_info=True)


def main() -> None:
    logs.setup()
    logs.log("app_started", version=os.environ.get("APP_VERSION", "dev"))
    jobs.models.refresh()
    stop = threading.Event()
    threading.Thread(target=poll, args=(stop,), daemon=True, name="model-poller").start()
    try:
        SimpleWorker([jobs.QUEUE], connection=Redis.from_url(os.environ["REDIS_URL"])).work()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
