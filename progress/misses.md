# Misses: Spaced-Review List

Every question you fumble lands here, with the fix in one line. This is the highest-yield review list in the repo.

**How it works:**

- **Add:** after every voice session, each `partial` / `weak` / `gap` verdict from `session_log.md` becomes one row in **Open**. The **Fix** is the one sentence you *should* have said: the mechanism, not just the buzzword.
- **Review:** every Friday quiz includes 2–3 questions from Open (oldest first, plus anything in that week's topic). The voice agent asks them cold.
- **Clear:** a miss moves to **Cleared** only after it's answered correctly **twice, on two different days**, at least a week apart. Track this in the `Hits` column (`0/2` → `1/2` → move to Cleared). If you get one wrong again, reset it to `0/2`.
- Keep rows short. If a fix needs more than a sentence or two, link the answer file or the lesson plan.

Columns: **Added** (date) · **Ref** (round + question number) · **What I missed** · **Fix (the answer in one line)** · **Hits** · **Teach week** (where it's taught in [PREP_TODO](../plan/PREP_TODO.md)).

---

## Open

| Added | Ref | What I missed | Fix (the answer in one line) | Hits | Teach week |
| --- | --- | --- | --- | --- | --- |
| 2026-10-06 | R3 Q1 | MRO / C3 linearization: no exposure | MRO is the order Python searches classes for an attribute; C3 builds it so children come before parents and the order in `class X(A, B)` is preserved, which makes `super()` cooperative in diamonds. Check with `X.__mro__`. | 0/2 | W2 |
| 2026-10-06 | R3 Q2 | Metaclasses: no exposure | A metaclass is the class of a class: `type` creates classes, and a custom metaclass hooks class *creation* (registries, ORMs like SQLAlchemy declarative). Today `__init_subclass__` or a decorator covers 90% of uses. | 0/2 | W2 |
| 2026-10-06 | R3 Q3 | `__getattr__` vs `__getattribute__` vs descriptors | `__getattribute__` runs on *every* lookup. `__getattr__` runs only when normal lookup fails. Descriptors (`__get__`/`__set__` on a class attribute) power `property`, methods and `classmethod`. Data descriptors beat the instance `__dict__`; non-data ones don't. | 0/2 | W2 |
| 2026-10-06 | R3 Q15 | Detecting a blocked event loop in prod | `asyncio` debug mode (`PYTHONASYNCIODEBUG=1`, slow-callback warnings > 100 ms), a loop-lag metric (schedule a sleep, measure the drift), and `py-spy dump` to see the blocking stack. | 0/2 | W3 |
| 2026-10-06 | R3 Q16 | gather vs TaskGroup vs as_completed | `gather`: results in order; on error the others keep running unless you cancel them. `TaskGroup`: the first failure cancels its siblings and raises an ExceptionGroup (structured). `as_completed`: handle results as they finish. Reach for TaskGroup by default. | 0/2 | W3 |
| 2026-10-06 | R3 Q17 | Structured concurrency | A task's lifetime is bounded by the block that created it: no orphan tasks, errors propagate to the parent, and cancellation flows down. TaskGroup/anyio give you that; bare `create_task` doesn't (and needs a stored reference, or it can get GC'd). | 0/2 | W3 |
| 2026-10-06 | R3 Q24 | API error model: retryability signal; "trace ID" vs correlation ID | The error body has a stable code, message, details and a correlation ID, plus an explicit retryable signal: the status class (429/503 retryable, 4xx not) + `Retry-After` + a `retryable` flag. Use problem-details (RFC 9457). | 0/2 | W4 |
| 2026-10-06 | R3 Q26 | Token bucket hazy; edge vs in-app placement | Token bucket: refill at rate r up to capacity b, and each request takes a token, so it allows bursts up to b. Do coarse per-IP limits at the edge/gateway, and per-tenant/business limits in-app (Redis + Lua for atomicity). | 0/2 | W4 |
| 2026-10-06 | R3 Q29 | K8s graceful shutdown: preStop unknown | Endpoint removal and SIGTERM race in parallel. A `preStop` sleep lets routing converge, then the app drains in-flight requests. Grace period > preStop + drain. See `scripts/k8s_graceful_shutdown/`. | 0/2 | W9 |
| 2026-10-06 | R2 Q1 | GIL: concrete release cases | The GIL is released during blocking I/O (socket/file reads, `time.sleep`) and by C extensions that drop it (NumPy, hashlib on big buffers, compression). So threads help I/O-bound work, not pure-Python CPU work. | 0/2 | W2 |
| 2026-10-06 | R2 Q4 | Shallow vs deep copy: reversed the nested behaviour | A shallow copy makes a new outer container but *shares* the nested objects, so mutating `copy[0].append()` changes the original too. `deepcopy` recursively copies the nested objects. | 0/2 | W1 |
| 2026-10-06 | R2 Q16 | FastAPI vs Flask: no ASGI vs WSGI depth | WSGI is synchronous, with one request per worker thread. ASGI is an async interface that supports long-lived connections (WebSockets, SSE) and concurrency on one event loop. FastAPI = Starlette (ASGI) + Pydantic validation + DI. | 0/2 | W4 |
| 2026-10-06 | R2 Q48 | Redis distributed lock / Redlock | `SET key token NX PX ttl`, then release only if the token matches (Lua). Redlock = a majority across N independent Redis nodes. It's still unsafe under GC pauses or clock jumps, so use fencing tokens checked by the resource. | 0/2 | W6 |
| 2026-10-06 | R2 Q62 | Docker multi-stage / slimming details | Build stage has the compilers and builds the wheels; runtime stage copies only the wheels/venv onto a slim or distroless base. Order layers so dependencies come before code (cache), add `.dockerignore`, run as non-root, use exec-form CMD. | 0/2 | W9 |
| 2026-10-06 | R2 Q116 | OAuth2 vs OIDC: mixes layers; access vs ID token | OAuth2 = *authorization* (delegated access): the access token is for the API. OIDC = an *authentication* layer on top: the ID token (a JWT) tells the client who the user is. Never send ID tokens to APIs. | 0/2 | W12 |
| 2026-10-06 | R1 Q47–50 | DataWeave crawler: no depth on anti-bot / alerting | Prepare: crawl architecture (scheduler → fetchers → parsers → storage), politeness/rate limits, proxy rotation, block detection, retries, and alerting on success rate and freshness per source. | 0/2 | W17 |
| 2026-09-21 | R5 Q22 | RAG debugging: no isolation technique; conflated retrieval with ranking | Bisect it: (1) is the right chunk in the corpus? (2) is it in top-k retrieval? (3) did the reranker keep it? (4) replay generation with the *frozen* context: does the model still fail? Fix whichever stage broke. | 0/2 | W8 (A-08) |

## Cleared

| Added | Cleared | Ref | Topic |
| --- | --- | --- | --- |
| | | | |
