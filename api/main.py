import os
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from api import logs, storage
from api.db import SessionLocal, engine
from api.routes import router
from api.security import hash_password
from api.settings import get_settings
from api.tables import User


def ensure_admin() -> None:
    """Creates the first user from ADMIN_EMAIL / ADMIN_PASSWORD if it doesn't exist yet."""
    s = get_settings()
    if not (s.admin_email and s.admin_password):
        return
    email = s.admin_email.strip().lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)) is None:
            db.add(User(email=email, password_hash=hash_password(s.admin_password), role="admin"))
            db.commit()
            logs.log("admin_created")


def retention_loop(stop: threading.Event) -> None:
    while True:
        try:
            n = storage.purge(get_settings().retention_days)
            if n:
                logs.log("uploads_purged", count=n, retention_days=get_settings().retention_days)
        except Exception:  # never let a disk hiccup kill the thread
            logs.log("uploads_purge_failed", 30, exc_info=True)
        if stop.wait(3600):
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    logs.setup()
    get_settings().check_api()  # fail fast on bad config
    logs.log("app_started", version=os.environ.get("APP_VERSION", "dev"))
    engine()
    try:
        ensure_admin()
    except Exception:  # table missing before migrations ran; readyz will report it
        logs.log("admin_seed_skipped", exc_info=True)
    stop = threading.Event()
    threading.Thread(target=retention_loop, args=(stop,), daemon=True, name="retention").start()
    yield
    stop.set()


app = FastAPI(title="GSTR-2B Reconciler", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    token = logs.request_id.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logs.log("request_failed", 40, exc_info=True, method=request.method,
                 path=request.url.path)
        response = JSONResponse({"detail": "internal error", "request_id": rid}, 500)
    route = request.scope.get("route")
    if request.url.path not in ("/healthz", "/readyz"):  # probes would flood the logs
        logs.log("request", method=request.method, path=getattr(route, "path", "unmatched"),
                 status_code=response.status_code,
                 duration_ms=round((time.perf_counter() - started) * 1000, 1))
    response.headers["x-request-id"] = rid
    logs.request_id.reset(token)
    return response


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/readyz")
def readyz():
    checks = {}
    try:
        with engine().connect() as c:
            c.execute(text("SELECT 1 FROM users LIMIT 1"))  # also proves migrations ran
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = type(e).__name__
    url = get_settings().redis_url
    if url:
        try:
            from redis import Redis

            Redis.from_url(url, socket_timeout=2).ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = type(e).__name__
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"ok": ok, **checks}, status_code=200 if ok else 503)
