"""JARVIS server: serves the app to your PC and phone, and runs reminders in the background.

Run:  python server.py          (add --open to open the browser)
"""
import asyncio
import collections
import contextlib
import hmac
import sys
import threading
import time
import webbrowser

import config

# When started hidden (pythonw), there is no console: log to a file instead.
if sys.stdout is None or sys.stderr is None:
    _log = open(config.DATA_DIR / "jarvis.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import db
import pc
import push

STATIC = config.BASE_DIR / "static"
brain = None  # created at startup (needs the API key)


# ------------------------------------------------------------------ reminders loop
def reminder_loop(stop):
    while not stop.is_set():
        try:
            for r in db.due_reminders():
                db.add_notification("reminder", r["text"])
                pc.alert(f"{config.ASSISTANT_NAME} reminder", r["text"])
                push.notify_all(f"{config.ASSISTANT_NAME} reminder", r["text"], tag=f"reminder-{r['id']}")
                db.advance_reminder(r)
        except Exception as e:
            print("Reminder loop error:", e)
        stop.wait(15)


@contextlib.asynccontextmanager
async def lifespan(app):
    global brain
    from agent import Jarvis
    if brain is None:
        brain = Jarvis()
    stop = threading.Event()
    threading.Thread(target=reminder_loop, args=(stop,), daemon=True).start()
    where = "in the cloud" if config.CLOUD else f"at http://localhost:{config.PORT}"
    print(f"\n  {config.ASSISTANT_NAME} is online {where}\n", flush=True)
    yield
    stop.set()


# ------------------------------------------------------------------ auth
_fails = {}                       # ip -> (count, first_fail_time)
_all_fails = collections.deque()  # times of every wrong PIN, from anyone


def _ip(request):
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd and config.CLOUD:      # behind the cloud host's proxy
        return fwd.split(",")[-1].strip()  # the address the host's proxy actually saw
    return request.client.host if request.client else "?"


def _token(request):
    h = request.headers.get("authorization", "")
    return h[7:] if h.lower().startswith("bearer ") else ""


def authed(fn):
    async def wrapper(request: Request):
        if not db.check_session(_token(request)):
            return JSONResponse({"error": "login required"}, status_code=401)
        return await fn(request)
    return wrapper


async def login(request: Request):
    now = time.time()
    while _all_fails and now - _all_fails[0] > 900:
        _all_fails.popleft()
    if len(_all_fails) >= 15:
        return JSONResponse({"error": "Too many wrong PINs. Logins are paused for 15 minutes."}, status_code=429)
    ip = _ip(request)
    count, first = _fails.get(ip, (0, now))
    if count >= 5 and now - first < 300:
        return JSONResponse({"error": "Too many wrong PINs. Wait 5 minutes."}, status_code=429)
    body = await request.json()
    pin = str(body.get("pin", ""))
    if config.PIN and hmac.compare_digest(pin.encode(), config.PIN.encode()):
        _fails.pop(ip, None)
        label = str(body.get("device", ""))[:80] or request.headers.get("user-agent", "")[:80]
        return JSONResponse({"token": db.new_session(label)})
    if now - first >= 300:
        count, first = 0, now
    _fails[ip] = (count + 1, first)
    _all_fails.append(now)
    await asyncio.sleep(1)
    return JSONResponse({"error": "Wrong PIN."}, status_code=401)


@authed
async def logout(request: Request):
    db.end_session(_token(request))
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------ API
@authed
async def status(request: Request):
    db.set_client_timezone(request.query_params.get("tz", ""))
    return JSONResponse({"name": config.ASSISTANT_NAME, "user": config.USER_NAME, "call_me": config.CALL_ME,
                         "model": config.MODEL, "auto_approve": config.AUTO_APPROVE, "cloud": config.CLOUD,
                         "last_notification": db.last_notification_id(),
                         "pending": [{"id": a["id"], "summary": a["summary"]} for a in db.pending_actions()]})


@authed
async def history(request: Request):
    rows = db.recent_turns(60)
    return JSONResponse([{"role": r["role"], "kind": r["kind"], "text": r["text"], "ts": r["ts"],
                          "sources": (r["meta"] or {}).get("sources", [])} for r in rows])


def _run_sync(fn, *args):
    from starlette.concurrency import run_in_threadpool
    return run_in_threadpool(fn, *args)


@authed
async def chat(request: Request):
    body = await request.json()
    text = str(body.get("message", ""))[:8000]
    device = str(body.get("device", "web"))[:60]
    tz = str(body.get("tz", ""))[:60]
    return JSONResponse(await _run_sync(brain.chat, text, device, tz))


@authed
async def action(request: Request):
    aid = int(request.path_params["aid"])
    approve = request.path_params["decision"] == "approve"
    body = await request.json() if request.headers.get("content-length") not in (None, "0") else {}
    device = str(body.get("device", "web"))[:60]
    return JSONResponse(await _run_sync(brain.resolve_action, aid, approve, device))


@authed
async def new_conversation(request: Request):
    db.archive_turns()
    return JSONResponse({"ok": True})


@authed
async def memories(request: Request):
    if request.method == "DELETE":
        return JSONResponse({"ok": db.delete_memory(int(request.path_params["mid"]))})
    return JSONResponse(db.list_memories())


@authed
async def reminders(request: Request):
    if request.method == "DELETE":
        return JSONResponse({"ok": db.cancel_reminder(int(request.path_params["rid"]))})
    return JSONResponse(db.list_reminders())


@authed
async def notifications(request: Request):
    after = int(request.query_params.get("after", "0") or 0)
    return JSONResponse({"items": db.notifications_after(after),
                         "pending": [{"id": a["id"], "summary": a["summary"]} for a in db.pending_actions()]})


# ------------------------------------------------------------------ phone notifications
@authed
async def push_key(request: Request):
    return JSONResponse({"key": push.public_key()})


@authed
async def push_subscribe(request: Request):
    body = await request.json()
    sub = body.get("subscription") or {}
    keys = sub.get("keys") or {}
    endpoint = str(sub.get("endpoint", ""))
    if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        return JSONResponse({"error": "bad subscription"}, status_code=400)
    db.add_push_sub(endpoint, keys["p256dh"], keys["auth"], str(body.get("device", ""))[:80])
    return JSONResponse({"ok": True})


@authed
async def push_test(request: Request):
    n = push.notify_all(config.ASSISTANT_NAME, f"Notifications are working, {config.CALL_ME or 'sir'}.", tag="test")
    return JSONResponse({"devices": n})


async def healthz(request: Request):
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------ app shell
async def index(request: Request):
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


async def service_worker(request: Request):
    return FileResponse(STATIC / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


async def manifest(request: Request):
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


routes = [
    Route("/", index),
    Route("/sw.js", service_worker),
    Route("/manifest.webmanifest", manifest),
    Route("/api/login", login, methods=["POST"]),
    Route("/api/logout", logout, methods=["POST"]),
    Route("/api/status", status),
    Route("/api/history", history),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/actions/{aid:int}/{decision:str}", action, methods=["POST"]),
    Route("/api/new", new_conversation, methods=["POST"]),
    Route("/api/memories", memories),
    Route("/api/memories/{mid:int}", memories, methods=["DELETE"]),
    Route("/api/reminders", reminders),
    Route("/api/reminders/{rid:int}", reminders, methods=["DELETE"]),
    Route("/api/notifications", notifications),
    Route("/api/push/key", push_key),
    Route("/api/push/subscribe", push_subscribe, methods=["POST"]),
    Route("/api/push/test", push_test, methods=["POST"]),
    Route("/healthz", healthz),
    Mount("/static", StaticFiles(directory=str(STATIC)), name="static"),
]
app = Starlette(routes=routes, lifespan=lifespan)


def main():
    problems = []
    if not config.API_KEY:
        problems.append("ANTHROPIC_API_KEY is missing")
    if len(config.PIN) < config.MIN_PIN:
        problems.append(f"JARVIS_PIN must be at least {config.MIN_PIN} characters")
    if problems:
        fix = "Add them in your Railway service's Variables tab." if config.CLOUD else \
            "Run install.bat (or configure.py) first."
        print("Can't start: " + "; ".join(problems) + ". " + fix, flush=True)
        sys.exit(1)
    if "--open" in sys.argv and not config.CLOUD:
        threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{config.PORT}")).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
