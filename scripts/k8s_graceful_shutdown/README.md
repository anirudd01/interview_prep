# Graceful shutdown on Kubernetes: FastAPI + preStop + request draining

This demo reproduces the most common zero-downtime-deploy bug: requests fail during a rolling update even though the app "handles SIGTERM". It then fixes the bug with a preStop hook and proves the fix with numbers.

It covers Round 3 Q29 (graceful shutdown), Round 2 Q62 (multi-stage Dockerfile) and the K8s probes and lifecycle material in Round 6 E.

## The race, in one picture

```text
kubectl rollout restart / scale down / node drain
        |
        v
Pod marked Terminating ----------------------+------------------------------+
        |                                    |                              |
        | (A) endpoints controller           | (B) kubelet                  |
        v     removes pod from Service       v                              |
  kube-proxy on EVERY node updates      preStop hook runs (sleep 10)        |
  iptables/IPVS  ~0.5-few s later;      ...then SIGTERM -> app drains       |
  ingress / cloud LB: often longer                                          |
                                                                            v
                                        terminationGracePeriodSeconds -> SIGKILL
```

(A) and (B) run **in parallel and nothing coordinates them**.

- **Without preStop:** SIGTERM arrives almost immediately. Uvicorn closes its listening socket while some nodes are still routing new connections to this pod's IP. Those connections get **connection refused** (or 502s at an ingress).
- **With preStop `sleep 10`:** SIGTERM is delayed. The app keeps serving normally while (A) catches up. By the time SIGTERM lands, no new traffic is arriving and the only job left is to drain in-flight requests.

## What the app does on SIGTERM ([app.py](app.py))

1. It flips `/readyz` to 503 and logs how many requests are in flight.
2. Uvicorn stops accepting new connections, closes idle keep-alives, and waits up to `DRAIN_TIMEOUT_SECONDS` for in-flight requests.
3. Any request still running after the deadline is **cancelled**. The client sees a 500, or a reset if the response had already started. That's why the drain timeout must exceed your p99 request time.
4. Lifespan shutdown runs: close pools, flush telemetry. Then the process exits 0.

**Budget rule:** `preStop + drain timeout + cleanup < terminationGracePeriodSeconds`. This demo uses 10 + 25 + ~1 < 45. If you get it wrong, kubelet SIGKILLs mid-drain.

## Run it

You need Docker running, [kind](https://kind.sigs.k8s.io/) and kubectl. Run this from Git Bash:

```bash
cd scripts/k8s_graceful_shutdown
./run_demo.sh            # round 1 WITHOUT preStop, round 2 WITH preStop
./run_demo.sh cleanup    # delete the cluster when done
```

To watch it live in a second terminal:

```bash
kubectl logs -l app=drain-demo -f --prefix      # SIGTERM, draining, exit logs per pod
kubectl get pods -w                               # Terminating -> gone
kubectl get endpointslices -l kubernetes.io/service-name=drain-demo -w
```

**What to expect:** the `without` round shows `conn_refused` (and possibly `conn_reset`) errors around each old pod's termination. The `with` round should show **0 failed**. kind is a best case: one machine, so endpoint updates are fast and the without-preStop error count may be small. On EKS/GKE/AKS behind an ingress or cloud LB, the window is seconds long and the errors are much larger. Run each round a couple of times, because the race is timing-dependent.

## Experiments worth trying

| Change | What you'll see | Lesson |
| --- | --- | --- |
| `--url ...?ms=30000` in `k8s/loadgen.yaml` | Long requests cut off at the 25s drain deadline as 500s | Drain timeout must exceed p99 latency. Long jobs belong in a queue, not HTTP |
| `terminationGracePeriodSeconds: 15` | Pods SIGKILLed mid-drain, `conn_reset` errors | Grace period includes preStop time |
| Dockerfile `CMD python app.py` (shell form) | No "got SIGTERM" log, every pod takes the full 45s, then SIGKILL | `sh` as PID 1 doesn't forward signals. Use exec form or `tini` |
| Make `/healthz` return 503 when shutting down | Container restarted mid-drain | Liveness must stay green while draining. Only readiness flips |
| `maxUnavailable: 1` in the rollout strategy | Extra errors and latency from lost capacity | Separate "capacity" failures from "shutdown race" failures |

## Running parts locally (no cluster)

```bash
pip install -r requirements.txt
python app.py                                   # serves on :8000
python loadgen.py --url "http://127.0.0.1:8000/work?ms=300" --duration 20 --concurrency 10
# Ctrl+C the app mid-run to watch in-flight requests drain and new ones get refused
```

On Windows, Ctrl+C sends SIGINT, which uvicorn handles the same way as SIGTERM. A refused connection takes about 2s to fail on Windows, but is instant on Linux.

## Interview answer (30 seconds)

> "SIGTERM and endpoint removal happen in parallel in Kubernetes, so a pod can get new traffic after it's started shutting down. I add a preStop sleep, around 5–15s depending on the ingress, so routing converges before SIGTERM. Then the app stops accepting, drains in-flight requests with a deadline above p99, and closes pools in the lifespan hook. Liveness stays green and readiness flips. I size terminationGracePeriodSeconds above preStop plus drain, use exec-form CMD so the app is PID 1 and actually gets the signal, and set maxUnavailable 0 on rollouts. For queue consumers it's the same idea: stop polling, finish or nack in-flight messages, and commit offsets only after processing."
