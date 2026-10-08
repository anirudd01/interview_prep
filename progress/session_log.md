# Session Log

Append-only. One entry per prep session. Newest entry at the top.
Each entry: date, duration, questions asked (round + number), verdict per question (covered / partial / weak), and one-line takeaway.

Format:

```
## YYYY-MM-DD (N min)
- ROUND_x Q#: covered/partial/weak — short note
- ...
Takeaway: one sentence on how the session went and what to hit next time.
```

---

## 2026-09-21 (15 min)

- ROUND_5 Q22: partial — good production/citation instincts and honest about not knowing ranking, but missed the core isolation technique (replay with frozen context to bisect retrieval/ranking vs generation) and conflated retrieval with ranking.
Takeaway: solid instincts on RAG production concerns, but needs to tighten the actual debugging methodology and learn reranking cold before next AI round.

---
2026-10-06 | 55 min | ROUND 1: Intro & Career

- Q1 (Career arc): Covered — solid narrative from data eng → backend owner, honest on circumstances
- Q8 (Stability): Covered — clear on what makes him stay (interesting problems, learning, min 1yr floor)
- Q2 (Proudest system): Covered — News recommender, thoughtful on rebuilds (vector DB, Go, serverless)
- Q14-24 (Jio recommender deep-dive): Strong — real numbers (100M/day, 33k peak RPS, p50=100ms p95=200ms, <0.5% errors), named actual bottlenecks (GIL, Postgres pooling, network), explained Kafka + dual embedding/similarity services
- Q47-50 (DSA): Partial — mentioned design council value, acknowledged over-iteration on requirements, didn't go deep on crawler/anti-bot/alerting

Takeaway: Ownership and mentoring are genuine strengths; scale experience is real. Needs tighter precision on state/serverless tradeoffs and org-level architectural thinking for Staff bar.

---
2026-10-06 | 50 min | Round 2: Fundamentals Breadth

Questions covered:

- A1 (GIL): Partial — knows concept, missed concrete cases (I/O, C extensions)
- A2 (list/tuple/set/dict): Covered — time complexity solid, real-world tuple usage weak
- A3 (mutable defaults): Covered — nailed it
- A4 (shallow vs deep copy): Weak — confused behavior on nested objects
- B16 (FastAPI vs Flask): Partial — knows they work well together, lacks architectural depth
- D48 (Redis distributed locks): Weak — hasn't used, no knowledge of Redlock
- E51 (Kafka vs RabbitMQ): Covered — real production experience, understands tradeoffs
- F62 (Docker multi-stage): Partial — hasn't built from scratch in 2+ years, concept clear but details hazy
- K116 (OAuth2 vs OIDC): Weak — used once, mixing up layers, fuzzy on token types
- Round 4 System Design (URL shortener): Skipped (covered in prior session)

Takeaway: Solid on systems he's actively used (Kafka, RabbitMQ at scale). Weak on theory and edge cases (GIL specifics, deep copy behavior, distributed locks, auth details). Docker knowledge atrophied. FastAPI understanding is practical but not architectural.

---

## 2026-10-06 - ROUND 3: Python & Backend Advanced (Voice, ~45 min)

**Questions Covered:**

- Q1 (MRO/C3 linearization): Not covered — gap identified
- Q2 (Metaclasses): Not covered — gap identified
- Q3 (Attribute access / descriptors): Not covered — gap identified
- Q4 (Event loop / blocking): Partial — solid on event loop mechanics, weak on production detection (py-spy/yappi)
- Q5 (gather vs TaskGroup vs as_completed): Not covered — gap identified, hazy on all three
- Q6 (Structured concurrency): Not covered — admits light async experience, hasn't debugged under pressure
- Q7 (API error model): Partial — implemented custom error codes + Swagger docs, missing retryability signal and correlation ID concept (though he calls it trace ID)
- Q8 (Request-scoped DB sessions): Solid — read-only replicas, scoped write sessions with pool management, evolved from manual to `Depends` pattern
- Q9 (Rate limiting three ways): Partial — fixed window and sliding window correct, token bucket hazy, no discussion of edge vs in-app deployment
- Q10 (Circuit breaker): Covered (library/impl) — built from scratch at first company, details faded
- Q11 (K8s graceful shutdown): Partial — SIGTERM handling and grace periods known, **preStop hook completely unknown**, gap identified
- Q12 (Long-running HTTP jobs): Solid — job ID pattern, polling API, FastAPI background tasks for small work, Celery + broker for heavy tasks, experience with Flower monitoring and task distribution

**Takeaway:** Strong on practical async patterns and job queues in production. Significant gaps in Python runtime magic (MRO, metaclasses, descriptors) and async primitives (TaskGroup, structured concurrency). Kubernetes operational patterns (preStop) not in his toolkit yet. Retryability signaling and token bucket semantics need study.

**Flags for follow-up:**

- Async/concurrency is his weakest area despite FastAPI use — mostly working in sync codebases
- Python internals (A section) is almost entirely a gap — prioritize if targeting Staff roles
- Wants to build preStop hook + graceful shutdown pattern as a learning project

---
