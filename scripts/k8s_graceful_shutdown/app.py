"""
FastAPI app that shuts down gracefully under Kubernetes.
=========================================================

Run locally:  pip install -r requirements.txt && python app.py
In-cluster:   see README.md / run_demo.sh

WHAT THIS APP DOES ON SHUTDOWN
------------------------------
  0. (K8s, before we see anything) preStop `sleep 10` runs. During those 10s
     we are still fully serving, while the endpoint removal propagates to
     kube-proxy / ingress so NEW traffic stops being routed here.
  1. SIGTERM arrives -> GracefulServer.handle_exit():
       - flip /readyz to 503 (belt-and-braces; the endpoint is normally gone by now)
       - tell uvicorn to exit
  2. uvicorn then:
       - closes the listening socket       -> no new connections
       - closes idle keep-alive connections, and marks busy ones "close after
         this response"
       - waits up to timeout_graceful_shutdown for in-flight requests to finish
       - cancels whatever is still running after that
  3. lifespan shutdown runs (close DB pools, flush telemetry)
  4. process exits 0, well before terminationGracePeriodSeconds -> no SIGKILL.

Budget rule:  preStop sleep + drain timeout + lifespan cleanup < terminationGracePeriodSeconds
              10            + 25            + ~1               < 45   (see k8s/app.yaml)

WHY SUBCLASS uvicorn.Server?
----------------------------
uvicorn installs its own SIGTERM/SIGINT handlers and already drains correctly.
We just want to *observe* the signal (log it, flip readiness) without replacing
its logic, so we override handle_exit and call super().
"""

import asyncio
import logging
import os
import signal
import socket
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response

POD = os.getenv("POD_NAME", socket.gethostname())
PORT = int(os.getenv("PORT", "8000"))
DRAIN_TIMEOUT = int(os.getenv("DRAIN_TIMEOUT_SECONDS", "25"))

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s.%(msecs)03d [{POD}] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app")


class State:
    shutting_down = False
    sigterm_at: float | None = None
    in_flight = 0


state = State()


def since_sigterm() -> str:
    return "" if state.sigterm_at is None else f" (+{time.monotonic() - state.sigterm_at:.1f}s after SIGTERM)"


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("startup: (pretend) DB pool opened")
    yield
    # Runs AFTER uvicorn has finished draining requests.
    log.info("lifespan shutdown: closing DB pool, in_flight=%d%s", state.in_flight, since_sigterm())


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def track_in_flight(request: Request, call_next):
    if request.url.path != "/work":  # don't count probes
        return await call_next(request)
    state.in_flight += 1
    try:
        response = await call_next(request)
    finally:
        state.in_flight -= 1
    response.headers["X-Pod"] = POD
    return response


@app.get("/work")
async def work(ms: int = 300):
    """Simulates a request that takes `ms` milliseconds (DB call, downstream API...)."""
    started_before_sigterm = not state.shutting_down
    await asyncio.sleep(ms / 1000)
    if state.shutting_down and started_before_sigterm:
        log.info("finished an in-flight request during drain%s", since_sigterm())
    return {"pod": POD, "ms": ms}


@app.get("/healthz")
async def healthz():
    """Liveness: 'is the process wedged?'. Keep it 200 during shutdown - failing
    liveness while draining makes kubelet restart the container mid-drain."""
    return {"ok": True}


@app.get("/readyz")
async def readyz(response: Response):
    """Readiness: 'should I get traffic?'. 503 once we've been told to stop."""
    if state.shutting_down:
        response.status_code = 503
        return {"ready": False}
    return {"ready": True}


class GracefulServer(uvicorn.Server):
    def handle_exit(self, sig: int, frame) -> None:
        if not state.shutting_down:
            state.shutting_down = True
            state.sigterm_at = time.monotonic()
            log.warning(
                "got %s -> readiness=503, stop accepting, draining %d in-flight request(s), "
                "deadline %ds",
                signal.Signals(sig).name, state.in_flight, DRAIN_TIMEOUT,
            )
        else:
            log.warning("second signal -> uvicorn will force exit")
        super().handle_exit(sig, frame)


def build_server() -> GracefulServer:
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=PORT,
        timeout_graceful_shutdown=DRAIN_TIMEOUT,  # max wait for in-flight requests
        access_log=False,                          # loadgen is noisy; we log what matters
        log_level="info",
    )
    return GracefulServer(config)


if __name__ == "__main__":
    build_server().run()
    log.info("process exiting cleanly%s", since_sigterm())
