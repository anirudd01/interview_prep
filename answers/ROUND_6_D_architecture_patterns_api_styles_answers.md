# Round 6 — Gap Fill & Staff Readiness: Answers, Section D (Architecture Patterns & API Styles)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. Original question numbers are kept. Each answer leads with the mechanism, then the trade-offs and what an interviewer will push on. Where a question touches your own systems, a **Your story:** note tells you what real example to bring. Q29 gives a reference mapping of Aurora/Pulse: compare it with what was actually built and be ready to say where it differed and why.

---

## D. ARCHITECTURE PATTERNS & API STYLES

### 29. Domain-Driven Design: bounded context, aggregate, entity vs value object, ubiquitous language. Map Aurora/Pulse (quote, policy, rater, broker) into bounded contexts.
**Ubiquitous language**: one shared vocabulary, used the same way by underwriters, product people and the code. If underwriters say "bind" then the method is `bind()`, not `finalize_quote()`. The language is only ubiquitous *inside one context*. The same word can legitimately mean different things in different contexts.

**Bounded context**: the boundary inside which a model and its language stay consistent. "Policy" means one thing to the underwriting team (a bound contract with coverages and a premium) and another to billing (a thing that generates instalments). Rather than forcing one giant `Policy` class on everyone, each context owns its own model and they translate at the edges. A bounded context is usually the unit for a service, a team and a database schema, though one service can host several contexts in a modular monolith.

**Entity vs value object**: an **entity** has an identity that survives change (a `Quote` with `quote_id` stays the same quote when its premium changes). A **value object** is defined only by its attributes, is immutable, and is compared by value (`Money(1250.00, "GBP")`, `Address`, `DateRange`, `Limit(1_000_000, "per occurrence")`). Push as much logic as you can into value objects: they are trivially testable and remove whole classes of bugs (adding GBP to USD, an end date before a start date).

**Aggregate**: a cluster of entities and value objects treated as one unit for changes, with a single **aggregate root** that is the only entry point. Outside code holds a reference to the root's ID, never to inner objects. Covered further in Q30.

**Reference mapping for Aurora/Pulse:**

| Context | Owns | Key aggregates | Language notes |
|---|---|---|---|
| **Broker / Distribution** | broker firms, agents, appointments, commission agreements, authority limits | `Broker` (root), `Appointment` | "Producer", "appointment", "binding authority" |
| **Submission / Intake** (Orbit/Ayana) | inbound emails, documents, extracted risk data, triage | `Submission` | "Submission", "clearance", "extracted field" |
| **Rating** (Cellular) | rater versions, rating factors, the executable rating logic | `RaterVersion`, `RatingRequest/Result` (mostly stateless) | "Rate", "factor", "rater version"; pure function: risk in, premium breakdown out |
| **Quoting** | quote lifecycle, options, referrals, underwriter overrides | `Quote` (root) with `QuoteOption` children | "Quote", "option", "refer", "decline", "bind request" |
| **Policy Administration** | bound policies, endorsements (MTAs), renewals, cancellations | `Policy` (root) with `PolicyVersion`/`Endorsement` | "Bind", "endorse", "MTA", "renew", "lapse" |
| **Documents** | templates, generated schedules/certificates, storage in Blob | `DocumentRequest` | "Schedule", "wording", "certificate" |
| **Billing / Finance** (often external) | premium invoicing, commission payouts | `Account`, `Instalment` | Downstream consumer only |

Relationships worth naming (DDD **context map** terms): Quoting is a **customer** of Rating (customer/supplier); it calls Rating with a risk payload and gets back a `RatingResult` value object, it never reaches into rater internals. Quoting depends on Broker for authority checks via an **anti-corruption layer** if the broker data comes from a legacy system or CRM. Policy Admin is created from Quoting by a `QuoteBound` event, and it copies the data it needs (a snapshot of the premium and terms) rather than pointing at the live quote, because a policy must not change if someone re-rates the quote later. Documents is a **conformist** downstream that subscribes to `PolicyIssued` / `EndorsementApplied`.

Interviewer push points: "Why is Rating separate from Quoting?" Because the rater changes on a different cadence (actuarial releases a new workbook) and is owned by different people; versioning rater logic independently, with the quote recording `rater_version`, is what makes old quotes reproducible. "Is a quote an entity or value object?" Entity. The premium on it is a value object. "Where do you draw the line between Quote and Policy?" At bind: different lifecycle, different invariants, different regulatory treatment.

**Your story:** say which of these boundaries actually existed in code (separate services, separate schemas, or just packages), where the model leaked (e.g. one shared `quote` table read by four services) and what you would split first.

### 30. What is an aggregate's consistency boundary, and why should one transaction modify only one aggregate? What do you do when a business rule spans two?
The aggregate is the boundary inside which **invariants are enforced immediately and transactionally**. Example: "a Quote's selected option must belong to that quote, and a bound quote cannot be edited." The `Quote` root enforces that in-memory before save, and the whole aggregate is persisted atomically, usually with an **optimistic concurrency** version column:

```sql
UPDATE quote SET status = 'BOUND', version = version + 1, ...
WHERE quote_id = :id AND version = :expected_version;
-- 0 rows updated => someone else changed it, reload and retry or reject
```

Why only one aggregate per transaction: (1) **contention**: a transaction that locks a `Broker` row and a `Quote` row serialises every quote for that broker; at scale that is your bottleneck and deadlock source. (2) **Scalability and distribution**: aggregates may live in different services or databases, and you cannot have a local transaction across them without 2PC. (3) It forces you to keep aggregates small, which is the main design discipline in DDD. Vaughn Vernon's rules: design small aggregates, reference other aggregates by ID only, use eventual consistency outside the boundary.

When a rule spans two aggregates:
- **Question whether it really needs to be immediate.** Most cross-aggregate rules tolerate seconds of lag. Ask the business: "What happens if the broker's authority is revoked and a quote binds 2 seconds later?" Often the answer is "flag it for review", which is a compensating action, not a transaction.
- **Domain events + eventual consistency**: `Quote.bind()` emits `QuoteBound` (written via a **transactional outbox** in the same DB transaction), and a handler creates the `Policy`. If creation fails, retry; if it fails permanently, compensate.
- **Saga / process manager** for multi-step flows with compensation (bind quote, issue policy, generate documents, notify billing).
- **Check-then-act with a read model or a domain service** when you need a pre-condition from another aggregate (read the broker's authority limit, then bind). Accept the small race, or re-validate in the downstream handler.
- **Redraw the boundary** if two things truly must be atomically consistent every time. If you keep wanting to modify both together, they may be one aggregate.
- Last resort: one local transaction across two aggregates in the *same* database. It is allowed pragmatically in a monolith, but call it out as a deliberate exception.

Common mistake: a giant `Broker` aggregate that contains all its quotes and policies, so every write loads thousands of children and contends on one version number.

### 31. CQRS: when is it worth it and when is it overkill? How does it change what the UI has to deal with?
**CQRS** (Command Query Responsibility Segregation): the write side (commands, the domain model, invariants) and the read side (queries, denormalised views shaped for screens) use **different models**, and optionally different stores. It does not require event sourcing or separate databases; the lightest version is just separate command handlers and query functions over the same Postgres, with queries skipping the ORM domain model and using SQL or views directly.

Worth it when:
- Reads and writes have very different shapes or scale (a broker dashboard listing 10k quotes with filters, aggregates and search, versus a write model that is a small `Quote` aggregate).
- Many read views over the same data (underwriter workbench, broker portal, MI reporting, search index in Azure AI Search).
- Read load dwarfs write load (100:1 or more) and you want to scale read replicas, caches or a search index independently.
- You already have events flowing (outbox, Event Hubs) so projections are cheap to build.

Overkill when: simple CRUD with one screen per table, a small team, or strong read-your-writes needs everywhere. Full CQRS with separate stores doubles the moving parts (projections, rebuilds, lag monitoring, replay tooling).

What changes for the UI: the read model is **eventually consistent**, so after a command the UI may read stale data. Options: the command returns the new state or version (`202` with `quote_id` and `version`) and the UI renders optimistically; the UI polls or waits until the projection's version is >= the one it wrote; push updates via SSE/WebSockets when the projection catches up; or route the user's *own* immediate reads to the write store ("read your own writes") while lists come from the projection. Commands also become task-based ("Refer quote to underwriter") rather than "PUT the whole object", which tends to produce clearer UIs and APIs. Interviewer push: "How do you know your projection lag?" Track `last_processed_event_position` vs head, alert on lag in seconds.

### 32. Event sourcing: how does it work, what are snapshots, how do you evolve event schemas (upcasting), and when would you refuse to use it?
**Mechanism**: instead of storing current state, you store the append-only sequence of **events** that happened to an aggregate (`QuoteCreated`, `OptionAdded`, `PremiumOverridden`, `QuoteBound`). Current state = fold the events in order. Writes append to the aggregate's stream with an **expected version** for optimistic concurrency. Read models are **projections** built by subscribing to the event log.

```python
def load(stream: list[Event]) -> Quote:
    q = Quote.empty()
    for e in stream:
        q = q.apply(e)          # pure, no side effects
    return q

def handle_bind(cmd, store):
    events, version = store.read(cmd.quote_id)
    quote = load(events)
    new = quote.bind(cmd.by_user)          # validates invariants, returns [QuoteBound(...)]
    store.append(cmd.quote_id, new, expected_version=version)
```

**Snapshots**: once a stream gets long (hundreds or thousands of events), loading is slow. Periodically persist the folded state at version N; loading becomes "latest snapshot + events after N". Snapshots are a cache: you can delete and rebuild them. Version the snapshot format separately.

**Schema evolution**: events are immutable history, so you never rewrite old ones in place (in the normal case). Techniques:
- **Additive changes** with defaults (new optional field) and tolerant readers.
- **Upcasting**: a function that transforms an old event version into the current one *at read time*: `PremiumCalculated_v1 {amount}` -> `v2 {amount, currency="GBP"}`. Chain upcasters v1->v2->v3. The domain code only sees the latest shape.
- **New event type** when the meaning changes, not just the shape.
- **Copy-and-transform migration** of the whole store as a last resort.
- Store `event_type` and `schema_version` on every event, and keep a schema registry (Avro/JSON Schema) if events cross service boundaries.

When I would refuse: CRUD domains with no real interest in history; teams with no event-sourcing experience on a deadline; when you need ad-hoc queries over current state everywhere (you will need projections for all of them); when **GDPR right-to-erasure** applies to personal data in events (needs crypto-shredding: encrypt PII per subject and delete the key); and when an audit table or temporal tables would give 90% of the value. Insurance is actually one of the better fits (a policy's history of endorsements, "what did the policy look like on date X" is a regulatory question), but I would still often pick **versioned rows plus an audit log** over full event sourcing.

### 33. Commands vs domain events vs integration events: what is the difference, and how do you name and version each?
- **Command**: a request to do something, directed at one handler, which may **reject** it. Imperative name: `BindQuote`, `RequestEndorsement`, `RecalculatePremium`. Exactly one owner. Can be sync (HTTP POST) or async (a queue message on Service Bus). Carries an idempotency key.
- **Domain event**: a fact that already happened **inside** a bounded context, past tense: `QuoteBound`, `PremiumOverridden`. Used within the context (same process or same service) to trigger side effects and keep aggregates consistent. It can reference internal model types and change freely with the code because nobody outside depends on it.
- **Integration event**: a fact published **across** context or service boundaries, also past tense: `pulse.policy.PolicyIssued.v1`. It is a **public contract**: minimal, stable, no internal types, documented in a schema registry or AsyncAPI. Often produced by translating a domain event in an outbox relay.

The key distinction is audience and stability: domain events are private implementation, integration events are a published API and must be versioned like one.

Naming: commands as verb+noun imperative; events as noun+past-tense verb; integration events namespaced by producer context (`policy-admin.PolicyIssued`). Avoid CRUD-ish events like `PolicyUpdated` that carry no intent; prefer `PolicyEndorsed`, `PolicyCancelled`.

Versioning: commands are versioned like API endpoints (schema in the API contract). Domain events: refactor freely, upcast if event-sourced. Integration events: backward-compatible changes only within a version (add optional fields, never remove or rename, never change meaning); for breaking changes publish `v2` alongside `v1` for a deprecation window, and put `type`, `version`, `event_id`, `occurred_at`, `correlation_id` in an envelope (CloudEvents is a good standard for this and is supported natively by Azure Event Grid). Consumers must be idempotent on `event_id` because delivery is at-least-once.

### 34. GraphQL: when would you pick it over REST? How do you deal with the N+1 problem (DataLoader), caching, authorization per field, and query-cost limits?
Pick GraphQL when: many different clients (web, mobile, partner portal) need different shapes of the same graph of data; screens aggregate many entities (a broker dashboard needs broker, quotes, latest policy, documents); you want a typed, introspectable schema as the contract; and the front-end team iterates faster than the back-end can add endpoints. Stay with REST for public/partner APIs (simpler, HTTP-cacheable, better tooling for rate limits and versioning), file uploads, simple CRUD, and service-to-service (gRPC or REST).

**N+1**: resolving `quotes { broker { name } }` for 100 quotes naively issues 1 query for quotes and 100 for brokers. **DataLoader** collects every `load(key)` call made during one tick of the event loop, then calls one batch function with all keys (`WHERE id = ANY(:ids)`) and caches per request. In Python, Strawberry ships a DataLoader:

```python
from strawberry.dataloader import DataLoader

async def load_brokers(ids: list[str]) -> list[Broker]:
    rows = await repo.brokers_by_ids(ids)          # one query
    by_id = {r.id: r for r in rows}
    return [by_id.get(i) for i in ids]             # must match input order

# create per request in the context getter, never global (cache leaks across users)
context = {"broker_loader": DataLoader(load_fn=load_brokers)}
```

**Caching**: one POST endpoint defeats HTTP/CDN caching. Options: **persisted queries** (client sends a hash, server only runs allow-listed queries, can then use GET and CDN caching), response caching keyed by query hash + variables + user scope, field-level caching with `@cacheControl` hints, and normalised client caches (Apollo, Relay). Data-layer caching (Redis) still works as usual under resolvers.

**Per-field authorization**: do it in the resolver or business layer, not the gateway, because a single query touches many types. Use schema directives or permission classes (Strawberry `permission_classes`) on sensitive fields, e.g. `commission_rate` visible only to the owning broker and underwriters. Authorise on the object too (row-level: this broker can only see their own quotes) or you get IDOR through nested paths like `policy { broker { otherQuotes } }`.

**Query-cost limits**: GraphQL lets clients write expensive queries. Defences: max depth (e.g. 8), max aliases/complexity, a **cost analysis** that assigns weight per field and multiplies by list `first:` arguments and rejects over budget before execution, mandatory pagination limits, timeouts, rate limiting by cost not by request count, and disabling introspection in production for public endpoints. Persisted queries alone remove most of the risk for first-party clients.

### 35. API gateway vs backend-for-frontend (BFF) vs service mesh: what does each own?
- **API gateway** (Azure API Management, Kong, Envoy Gateway, AWS API Gateway): the **north-south edge**. Owns cross-cutting concerns for traffic entering the system: TLS termination, authentication (validate JWTs from Entra ID), coarse authorization, rate limiting and quotas per client/subscription key, request routing to services, API versioning and developer portal, WAF integration, request/response transformation. It should not contain business logic.
- **BFF**: a thin backend **owned by one front-end team for one client type** (broker web portal BFF, underwriter workbench BFF, mobile BFF). Owns aggregation and shaping for that UI: calls Quote, Policy and Broker services and returns exactly what the screen needs, handles client-specific auth flows (session cookies for the browser while services use tokens), and isolates the UI from backend churn. It is application code, deployed and versioned with the UI. Risk: duplicated logic across BFFs; keep domain rules in the services.
- **Service mesh** (Istio, Linkerd, Cilium; on AKS the Istio-based add-on): **east-west** traffic between services, implemented in sidecars or node-level proxies (Istio ambient mode). Owns mTLS and workload identity, retries/timeouts/circuit breaking, traffic splitting for canaries, and golden-signal telemetry and tracing headers, all without application code changes. It does not do client-facing concerns like API keys or developer portals.

One-line summary: gateway = how outsiders get in; BFF = what one UI needs; mesh = how services talk to each other safely. Interviewer push: "Don't they overlap?" Yes, retries and auth exist in all three; decide one owner per concern (e.g. retries in the mesh, not also in the gateway and the client, or you get retry amplification).

### 36. How do you deprecate and remove a public API endpoint that external partners depend on? Timeline, usage signals, communication, and the final switch-off.
1. **Have a replacement first** and a migration guide with field-by-field mapping and examples. Do not deprecate into a void.
2. **Measure usage**: per-client request counts on the old endpoint (by API key or OAuth client ID in APIM/gateway logs), which operations and fields they use, and who the human owner of each client is. Without per-client attribution you cannot do the rest.
3. **Announce with a date**: changelog, email to technical contacts, developer portal banner. Typical windows: 6-12 months for external partners, longer if contracts specify it. In insurance, brokers' integrations are often maintained by third-party software houses on slow release cycles, so be generous.
4. **Signal in-band**: `Deprecation` header (RFC 9745) and `Sunset` header (RFC 8594) with the removal date, plus a `Link` to the migration docs. Mark it deprecated in the OpenAPI spec.
5. **Track the burn-down** weekly: active clients and traffic share on the old endpoint. Contact the top consumers directly; offer help or office hours. Freeze the old endpoint (no new features, security fixes only).
6. **Brownouts** before the switch-off: scheduled short windows (e.g. 10 minutes, then 1 hour, then a day) where the endpoint returns `410 Gone` or `503` with an explanatory body. This finds the clients that ignore email.
7. **Switch-off**: return `410 Gone` with a link to docs rather than a raw 404, keep the route for a while so errors are understandable, keep the ability to temporarily re-enable for a specific client key if a critical partner is caught out (a business decision, time-boxed).
8. Remove the code later and record the decision in an ADR.

Common mistake: removing on the announced date with 3 big partners still calling it. The date is a target; the real gate is usage near zero or an explicit business sign-off on who breaks.

**Your story:** any partner/broker integration you versioned or retired at Aventum, or an internal API at Jio where consumers were other teams. Bring the signal you used to know it was safe.

### 37. Synchronous vs asynchronous communication between services: decision criteria. What is temporal coupling, and how do you spot it in an architecture diagram?
Decision criteria:
- **Does the caller need the answer to continue?** Rating a quote while the broker waits: sync (the user is waiting, and the result is the response). Generating policy documents after bind: async.
- **Latency budget and fan-out**: a sync chain multiplies latency and failure probability. Five services each at 99.9% availability in a chain gives about 99.5%.
- **Load shape**: bursty or slow work (100k resume parses, a batch of renewals) goes on a queue so consumers process at their own pace and you get back-pressure for free.
- **Consistency needs**: sync gives an immediate yes/no; async means eventual consistency and needs idempotency, retries, DLQs and status tracking.
- **Ownership and change**: events let new consumers subscribe without the producer changing.
- **Debuggability**: async is harder to trace; budget for correlation IDs and distributed tracing.

**Temporal coupling**: service A can only do its job if service B is **up and responsive at the same moment**. If B is down, A fails, even though A did not logically need B's answer right then. Example: Quote service bind calls Document service synchronously to generate the schedule; when Document (or Blob storage) is slow, binding fails, although binding never needed the PDF to exist yet.

How to spot it on a diagram: long chains of solid synchronous arrows (A -> B -> C -> D) on a user-facing path; a single service with many inbound sync arrows (a hub that takes everything down); sync calls whose result is not used in the response (notifications, audit, documents, analytics) - these should be events; and loops (A calls B which calls A). Also ask, per arrow, "what does the caller do when this is down?" If the answer is "return 500", that is temporal coupling. Fixes: publish an event via outbox, use a queue, cache reference data locally (broker data replicated via events instead of calling Broker on every quote), or degrade gracefully.

### 38. Workflow engines (Temporal, Azure Durable Functions, Step Functions) vs a hand-rolled state machine with a queue: when is the engine worth it? How does Temporal achieve durable execution, and why must workflow code be deterministic?
**Hand-rolled** (a `status` column + Celery/Service Bus + a beat scheduler) is fine for short, linear flows of 2-3 steps with simple retries. It gets painful when you need: long waits (days or weeks: "wait for broker to upload documents or expire the quote in 30 days"), timers and reminders, human approvals (referral to an underwriter), compensation logic for partial failures (sagas), fan-out/fan-in with partial results, versioning of in-flight flows, and visibility into "where is case X right now and why is it stuck". At that point you are building a workflow engine badly: your state is scattered across a table, queue messages, Celery retries and cron jobs, and every new step adds edge cases.

**Engine is worth it** when flows are long-running, multi-step, have timers/human steps or compensations, and correctness matters (money, policies). Choices: **Temporal** (cloud-agnostic, code-first, strong Python SDK, self-host or Temporal Cloud), **Azure Durable Functions** (natural if you are already on Azure Functions; same replay model; orchestrations in Python), **Step Functions** (AWS, JSON/ASL state machine, tight AWS integration). Costs: new infra to run or pay for, a new mental model, determinism constraints, and harder local testing until the team learns the tooling.

**How Temporal achieves durable execution**: the workflow function's progress is recorded as an **event history** on the Temporal server (`WorkflowExecutionStarted`, `ActivityTaskScheduled`, `ActivityTaskCompleted` with its result, `TimerStarted`, `TimerFired`, signals). Side-effecting work runs in **activities**, which are retried by policy and whose results are persisted. If a worker crashes, another worker picks up the workflow and **replays** the workflow code from the start against the history: each `execute_activity` call whose result is already in the history returns the recorded result immediately instead of re-running it, so the code fast-forwards to exactly where it was and continues. A `sleep(30 days)` is a durable timer on the server, not a process sleeping.

```python
from datetime import timedelta
from temporalio import workflow

@workflow.defn
class BindPolicyWorkflow:
    @workflow.run
    async def run(self, quote_id: str) -> str:
        rating = await workflow.execute_activity(
            rate_quote, quote_id, start_to_close_timeout=timedelta(seconds=30))
        if rating.needs_referral:
            # durable wait for an underwriter signal, or expire after 7 days
            await workflow.wait_condition(lambda: self.approved, timeout=timedelta(days=7))
        policy_id = await workflow.execute_activity(
            issue_policy, quote_id, start_to_close_timeout=timedelta(seconds=60))
        await workflow.execute_activity(
            generate_documents, policy_id, start_to_close_timeout=timedelta(minutes=5))
        return policy_id
```

**Why determinism**: replay only works if re-running the workflow code against the same history produces the **same sequence of commands** (schedule activity X, start timer Y). If the code calls `datetime.now()`, `random()`, `uuid4()`, reads env vars or makes an HTTP call directly, or iterates an unordered collection, replay can take a different branch, and the engine raises a non-determinism error because the new commands do not match the history. So: all I/O goes in activities; use `workflow.now()`, `workflow.random()`, `workflow.uuid4()`; no threads; and changing workflow code with executions in flight needs **versioning** (`workflow.patched("v2-change")` or worker versioning) so old executions replay the old path. The Python SDK runs workflows in a sandbox that catches many of these mistakes. Activities, by contrast, can do anything but must be **idempotent**, because they are retried at-least-once.

Interviewer push: "Couldn't you just use Celery chains?" Celery chains have no durable timers beyond countdown/ETA (which are held in broker memory and are a known footgun for long delays), no event history, no signals for human approval, and no replay. Fine for a pipeline of 3 quick tasks, wrong for a 30-day quote-to-bind lifecycle.

**Your story:** the Orbit/Ayana new-business onboarding flow (email in, extraction, triage, handoff) or the Aurora quote-to-bind lifecycle are natural candidates. Say how state was actually tracked (status columns, Azure Functions, queues), what broke or was hard to see, and whether you would move it to Durable Functions or Temporal.
