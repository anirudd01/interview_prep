"""
Load generator that runs INSIDE the cluster and counts failed requests.
=======================================================================

Why in-cluster and not `kubectl port-forward`? port-forward pins to ONE pod and
bypasses the Service/kube-proxy entirely, so it can't show the routing race we
care about. This runs as a pod and hits the Service DNS name like a real client.

Every request opens a NEW TCP connection (urllib sends `Connection: close`), so
each request is load-balanced afresh by kube-proxy. That's the worst case for
the endpoint-removal race and makes errors visible.

Stdlib only, so it runs from the same image as the app.

Usage:
  python loadgen.py --url http://drain-demo/work?ms=300 --duration 60 --concurrency 20
"""

import argparse
import collections
import socket
import threading
import time
import urllib.error
import urllib.request


def classify(exc: BaseException) -> str:
    """Bucket errors the way you'd talk about them in an incident review."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ConnectionRefusedError):
        return "conn_refused"   # pod's listener already closed, but traffic still routed to it
    if isinstance(reason, ConnectionResetError):
        return "conn_reset"     # connection killed mid-request (SIGKILL / drain timeout)
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timeout"
    return type(reason).__name__


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--duration", type=float, default=60)
    p.add_argument("--concurrency", type=int, default=20)
    p.add_argument("--timeout", type=float, default=5)
    args = p.parse_args()

    lock = threading.Lock()
    per_second: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    totals: collections.Counter = collections.Counter()
    pods: collections.Counter = collections.Counter()
    start = time.monotonic()
    deadline = start + args.duration

    def worker() -> None:
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(args.url, timeout=args.timeout) as resp:
                    resp.read()
                    outcome, pod = "ok", resp.headers.get("X-Pod", "?")
            except Exception as exc:  # noqa: BLE001 - we want to count everything
                outcome, pod = classify(exc), None
            # Bucket by COMPLETION time: a failed connect can take a while to
            # fail, and we want the error to show up in the second it happened.
            sec = int(time.monotonic() - start)
            if outcome != "ok":
                time.sleep(0.05)  # don't spin on instant failures
            with lock:
                per_second[sec][outcome] += 1
                totals[outcome] += 1
                if pod:
                    pods[pod] += 1

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.concurrency)]
    for t in threads:
        t.start()

    # Print a line per second while running so `kubectl logs -f loadgen` is live.
    printed = 0
    while True:
        alive = any(t.is_alive() for t in threads)
        if alive:
            time.sleep(1)
        now = int(time.monotonic() - start)
        with lock:
            # Once all workers are done, flush every remaining second.
            last = now if alive else max(per_second, default=-1) + 1
            while printed < last:
                c = per_second.get(printed, collections.Counter())
                errs = {k: v for k, v in c.items() if k != "ok"}
                flag = "   <-- ERRORS" if errs else ""
                print(f"t={printed:3d}s ok={c['ok']:4d} errors={errs or '{}'}{flag}", flush=True)
                printed += 1
        if not alive:
            break

    total = sum(totals.values())
    failed = total - totals["ok"]
    print("\n===== SUMMARY =====")
    print(f"requests: {total}  ok: {totals['ok']}  failed: {failed} "
          f"({100 * failed / max(total, 1):.2f}%)")
    print(f"errors by kind: {dict((k, v) for k, v in totals.items() if k != 'ok') or 'none'}")
    print(f"distinct pods that served traffic: {len(pods)}")


if __name__ == "__main__":
    main()
