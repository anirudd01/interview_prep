# Infographics: One-Page Visual Recaps

There's one image per finished week, for 5-minute weekly or monthly brush-ups. Each week has an **SVG** (the source: text-based, diffable in git, and rendered by GitHub and VS Code) and a **PNG** (for your phone's gallery or printing).

| Week | Image |
| --- | --- |
| W03 Async and concurrency | [W03_async.svg](W03_async.svg) · [PNG](W03_async.png) |

## Topic cards

These are smaller cards on one topic each, kept in [cards/](cards/). They don't wait for a finished week: use them to catch up, to review misses, or as a 3-minute refresher before an interview. Each card's header lists the question numbers it covers.

| Card | Covers | Image |
| --- | --- | --- |
| Python data model | Copies, `is` vs `==`, the `__eq__`/`__hash__` contract, dunders, the mutable default, late binding, decorators (W01) | [SVG](cards/python_data_model.svg) · [PNG](cards/python_data_model.png) |
| Python memory and the GIL | Refcount vs cyclic GC, shallow vs deep copy, when the GIL is released, `+=` races, free-threaded 3.13t/3.14t (W02) | [SVG](cards/python_memory_gil.svg) · [PNG](cards/python_memory_gil.png) |
| Redis caching | Cache patterns, invalidation races, stampede fixes, eviction policies, locks with fencing tokens, Redlock (W06) | [SVG](cards/redis_caching.svg) · [PNG](cards/redis_caching.png) |
| Resilience patterns | Timeouts and deadline budgets, retries with jitter and amplification, circuit breaker, idempotency keys, bulkheads (W08) | [SVG](cards/resilience_patterns.svg) · [PNG](cards/resilience_patterns.png) |
| Docker image and runtime | A multi-stage uv Dockerfile, layer caching, base images, PID 1 and signals, hardening and secrets (W09) | [SVG](cards/docker_image_runtime.svg) · [PNG](cards/docker_image_runtime.png) |
| Auth | Session vs JWT, OAuth2 vs OIDC, auth code + PKCE, refresh rotation, validating a JWT (W12) | [SVG](cards/auth_oauth_jwt.svg) · [PNG](cards/auth_oauth_jwt.png) |
| API design | Method semantics and status codes, offset vs cursor pagination, rate limiting, versioning, ETags, problem+json, REST vs gRPC vs GraphQL (W04) | [SVG](cards/api_design.svg) · [PNG](cards/api_design.png) |
| Postgres internals | Index types, reading `EXPLAIN ANALYZE`, MVCC and vacuum, isolation levels and their anomalies, PgBouncer pooling (W05) | [SVG](cards/postgres_internals.svg) · [PNG](cards/postgres_internals.png) |
| Distributed systems theory | CAP and PACELC, the consistency ladder, quorums, Raft, exactly-once = at-least-once + idempotence, fencing (W08) | [SVG](cards/distributed_systems_theory.svg) · [PNG](cards/distributed_systems_theory.png) |
| K8s request path and probes | Client → Ingress → Service → Pod, startup/readiness/liveness, requests vs limits, HPA and PDB, a debug ladder (W09) | [SVG](cards/k8s_request_path_probes.svg) · [PNG](cards/k8s_request_path_probes.png) |
| Observability and SLOs | Metrics, logs, traces and profiles, RED vs USE, histograms vs averaged p99, error budgets, burn-rate alerts, Jio SLOs (W11) | [SVG](cards/observability_slos.svg) · [PNG](cards/observability_slos.png) |
| Networking and TLS | What happens when you curl a URL: DNS, TCP, TLS 1.3, HTTP/1.1 vs 2 vs 3, L4 vs L7 load balancers, debug commands (W12) | [SVG](cards/networking_tls.svg) · [PNG](cards/networking_tls.png) |
| Estimation and latency | Latency numbers, unit shortcuts, Little's law, defending the Jio 100M/day and ATS 100k/day numbers (W13) | [SVG](cards/estimation_latency.svg) · [PNG](cards/estimation_latency.png) |
| RAG pipeline and debugging | The pipeline, chunking, bi-encoder vs cross-encoder, debugging by bisection with a frozen context, failure modes (AI track) | [SVG](cards/rag_pipeline_debugging.svg) · [PNG](cards/rag_pipeline_debugging.png) |
| LLM evaluation | Golden sets, choosing an eval method, LLM-as-judge biases, offline vs online, confidence intervals (AI track) | [SVG](cards/llm_evaluation.svg) · [PNG](cards/llm_evaluation.png) |

The cards use the same style as the weekly sheets. They're 1200 px wide, as tall as their content needs (about 1000–1900 px), and have 4–5 panels. To re-render one, run the command below with that card's path and its `height`. If headless Edge hangs after taking the screenshot, add `--user-data-dir` pointing at a temporary folder.

## How they get made

1. **You write your own cheat sheet first** (Thursday of that week). The infographic is a *check* on your recall, not a replacement for it.
2. Ask Claude Code: *"make the W0x infographic from teach/W0x_... and my cheat sheet"*. It uses the lesson plan's **Infographic brief**, plus whatever you got wrong that week.
3. Claude writes the SVG, renders it to PNG with headless Edge, looks at the render to check the layout, and fixes anything that overlaps.

To re-render a PNG yourself (Windows, from the repo root, in Git Bash):

```bash
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu \
  --hide-scrollbars --window-size=1200,1680 \
  --screenshot="$(pwd -W)\\teach\\infographics\\W03_async.png" \
  "file:///$(pwd -W)/teach/infographics/W03_async.svg"
```

Match `--window-size` to the SVG's `width`/`height`.

## Style rules (so they stay consistent)

- 1200 px wide, one page, light background, the same navy header and footer strip.
- 5–7 numbered panels, each answering one interview question.
- Tables over prose; **bold the trap**: the thing interviewers fish for.
- Always end with "N rules to say out loud".
