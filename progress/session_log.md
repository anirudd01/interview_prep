# Session Log

Append-only. One entry per prep session. **Newest entry at the top.**
Question numbers are the numbers printed in `questions/` (not the order asked).
Verdicts: **covered** / **partial** / **weak** / **gap** (didn't know it at all).

Format:

```text
## YYYY-MM-DD — ROUND_x: <name> (N min, voice|text)
- Q#: verdict — short note
- ...
Takeaway: one sentence on how the session went and what to hit next time.
```

---

## 2026-10-06 — ROUND_3: Python & Backend Advanced (45 min, voice)

- Q1 (MRO / C3 linearization): gap — no exposure
- Q2 (Metaclasses): gap — no exposure
- Q3 (`__getattr__` vs `__getattribute__` vs descriptors): gap — no exposure
- Q15 (Event loop / blocking the loop): partial — loop mechanics solid; weak on detecting blocking in prod (asyncio debug mode, py-spy)
- Q16 (gather vs TaskGroup vs as_completed): gap — hazy on all three
- Q17 (Structured concurrency): gap — light async experience, never debugged async under pressure
- Q24 (API error model): partial — custom error codes + Swagger docs; missing explicit retryability signal; calls correlation IDs "trace IDs"
- Q25 (Request-scoped DB sessions): covered — read replicas, scoped write sessions, pool management, evolved to `Depends`
- Q26 (Rate limiting three ways): partial — fixed window + sliding log correct, token bucket hazy, no edge vs in-app placement discussion
- Q28 (Circuit breaker): covered — built from scratch at first company, details faded
- Q29 (K8s graceful shutdown): partial — SIGTERM + grace period known; preStop hook unknown
- Q30 (Long-running jobs over HTTP): covered — job-ID polling, BackgroundTasks vs Celery, broker/backend, Flower

Takeaway: Strong on practical job queues and request plumbing; Python runtime internals and async primitives are the biggest gaps for a Staff-level Python bar. He wants to build a preStop/graceful-shutdown demo himself.

---

## 2026-10-06 — ROUND_2: Fundamentals Breadth (50 min, voice)

- Q1 (GIL): partial — knows concept, missed concrete release cases (blocking I/O, C extensions)
- Q2 (list/tuple/set/dict): covered — complexities solid, real-world tuple usage weak
- Q3 (Mutable defaults): covered — nailed it
- Q4 (Shallow vs deep copy): weak — reversed behavior on nested objects
- Q16 (FastAPI vs Flask): partial — practical, lacks ASGI vs WSGI architectural depth
- Q48 (Redis distributed lock / Redlock): weak — never used, didn't know Redlock
- Q51 (Kafka vs RabbitMQ): covered — real prod experience, clear tradeoffs
- Q62 (Docker image slimming / multi-stage): partial — concept clear, details hazy after 2+ yrs
- Q116 (OAuth2 vs OIDC): weak — mixes layers, fuzzy on access vs ID token

Takeaway: Solid wherever he has recent hands-on use (Kafka, RabbitMQ); weak on theory and edge cases (GIL specifics, deep copy, distributed locks, auth). Docker knowledge has atrophied.

---

## 2026-10-06 — ROUND_1: Intro & Career (55 min, voice)

- Q1 (Career arc): covered — clear data eng → backend owner narrative, honest on circumstances
- Q2 (Proudest system): covered — Jio news recommender; would rebuild with vector DB, Go, serverless
- Q8 (What makes you stay 4+ yrs): covered — interesting problems, learning, 1-yr floor
- Q41–46 (Jio recommender / ATS deep-dive): covered, strong — 100M req/day, 33k peak RPS, p50 100ms / p95 200ms, <0.5% errors; named GIL, Postgres pooling, network as real bottlenecks; Kafka + split embedding/similarity services
- Q47–50 (DataWeave DSA 2.0 / crawler): partial — design council value and over-iteration on requirements; no depth on crawler anti-bot or alerting

Takeaway: Ownership, mentoring and real scale are genuine strengths. For the Staff bar he needs tighter stateful vs serverless tradeoffs and more org-level architecture thinking.

_Note (2026-10-10 cleanup): this entry was originally logged as "Q14-24" and "Q47-50 (DSA)"; renumbered to match the question bank. Round 4 was listed as "skipped (covered in prior session)" in the Round 2 entry, but no Round 4 session exists — Round 4 is still untested._

---

## 2026-09-21 — ROUND_5: AI (15 min, voice)

- Q22 (RAG debugging tree): partial — good production/citation instincts, honest about not knowing ranking; missed the isolation technique (replay with frozen retrieved context to bisect retrieval vs ranking vs generation) and conflated retrieval with ranking

Takeaway: Good instincts on RAG production concerns; needs to tighten the debugging method and learn reranking cold before the next AI round.

---
