# System Design Kits

One kit per canonical design. Each kit is built in its own Claude Code session ("build the next system design kit"), one at a time, in the order below. The kits support the timed designs in plan weeks 13–16 ([PREP_TODO.md](../plan/PREP_TODO.md)); they don't replace them.

## How to use a kit (for Aniruddha)

1. **Attempt first.** Open the kit's `design.md` and read only the "Your attempt" box at the top. Design it yourself for 45 minutes, on paper or out loud in a voice session, using the framework below. Reading a design you haven't tried feels like learning, but it mostly isn't.
2. **Grade yourself with the page.** Open the interactive page. Click each component and step through the request flows. Note every decision you missed or got wrong, and add the real gaps to `progress/misses.md`.
3. **Listen.** Upload `narrative.md` to NotebookLM and generate an audio overview for commutes.
4. **Refresh.** Before an interview, the one-page card is the 3-minute recap.

### The framework (every design, every time)

Clarify scope → non-functional requirements (NFRs) with numbers → back-of-envelope estimation → API → data model → high-level diagram → deep dive on two components → bottlenecks and failure modes → trade-offs you chose *against* → v1 vs later. It mirrors the Round 4 rubric in [ROUND_4_system_design.txt](../questions/ROUND_4_system_design.txt).

## Catalog

Status: `todo` · `building` · `done`. Build in this order unless the plan week says otherwise.

| # | Design | Source questions | Why it's here / anchor | Plan wk | Status |
| --- | --- | --- | --- | --- | --- |
| 01 | News feed / recommendation serving at 100M req/day | R4 Q11–12 | **Pilot.** Your Jio recommender: defend 33k peak RPS, p95 200 ms | W14 | building |
| 02 | URL shortener | R4 Q1 | Warm-up classic: ID generation, read-heavy caching, 100k writes/s | W13 | todo |
| 03 | Rate limiter as a shared service | R4 Q3 | Token bucket at scale, Redis, fail-open vs fail-closed | W13 | todo |
| 04 | Notification system | R4 Q5 | Fan-out, preferences, dedupe, retries, provider failover | W13 | todo |
| 05 | Resume ingestion and matching pipeline | R4 Q13 | Your Jio ATS: queues, parsing, embeddings, backpressure | W14 | todo |
| 06 | Distributed job scheduler | R4 Q4 | At-least-once, leases, 1M jobs, per-second granularity | W14 | todo |
| 07 | Insurance submission intake (document AI) | R4 Q24–25, R5 Q65 | Your current domain: extraction, human review, evals, cost per doc | W15 | todo |
| 08 | Enterprise RAG with permissions | R6 Q101, R5 RAG section | ACL-aware retrieval, ingestion, evals, cost and latency | W15 | todo |
| 09 | LLM gateway and serving layer | R5 Q47 | Streaming, routing, fallbacks, caching, token budgets | W15 | todo |
| 10 | Multi-region active-active (Python API + Postgres) | R4 Q19, Q34 | Cloud half: replication, failover, RTO/RPO, DR | W15 | todo |
| 11 | Real-time chat | R6 Q102 | WebSockets, delivery receipts, ordering, presence | W16 | todo |
| 12 | Rating and quoting engine | R4 Q21–22 | Strongest-signal domain design: rules, versioning, A/B tests | W16 | todo |
| 13 | Payment / transaction ledger | R4 Q7 | Double-entry, idempotency, reconciliation | W16 | todo |
| 14 | Distributed cache (Redis Cluster from scratch) | R6 Q104 | Partitioning, consistent hashing, replication, eviction | after M3 | todo |
| 15 | Web crawler platform | R4 Q14 | Your DataWeave work: politeness, scheduling, anti-bot, dedupe | after M3 | todo |
| 16 | Search autocomplete | R6 Q103 | Tries vs search index, p99 latency, ranking, personalization | after M3 | todo |
| 17 | File upload and processing | R4 Q6 | Multipart and resumable uploads, scanning, webhooks | after M3 | todo |
| 18 | Metrics / time-series backend | R6 Q105, R4 Q33 | Ingestion, compression, downsampling, cardinality | after M3 | todo |
| 19 | Flash-sale booking (no double booking) | R6 Q106 | Holds with TTL, inventory contention, queueing users | after M3 | todo |
| 20 | Geospatial platform | R4 Q16 | Your GeoStorm: spatial indexes, tiles, PostGIS vs alternatives | after M3 | todo |

Kit links (pages, cards) go in the **Built kits** table at the bottom as each one is finished.

## Kit spec (for the Claude Code session building it)

Each kit lives in `system_design/NN_slug/` and has exactly these files:

| File | What it is | Made by |
| --- | --- | --- |
| `design.md` | **The source of truth.** All content lives here; everything else is derived from it. Fix content here first. | Main session (Opus), written carefully |
| `kit.json` | The data the interactive page renders: components, edges, flows, sections. | Main session, from `design.md` |
| `page.html` | Generated: `python scripts/tools/build_kit.py system_design/NN_slug`. Published as a private artifact; republish to the same URL after changes. | Script |
| `card.svg` + `card.png` | One-page refresh card in the `teach/infographics/cards/` style: the diagram plus the key decisions and six rules. | Sonnet subagent, from `design.md` |
| `narrative.md` | 1,500–2,200 words of spoken-style prose for NotebookLM: "walk me through it", no tables or bullets. | Sonnet subagent, from `design.md` |

### `design.md` sections (in this order)

1. **Your attempt**: the prompt as an interviewer would give it, plus 3–4 clarifying questions you should ask. Nothing that gives the design away.
2. **Requirements**: functional, then NFRs with numbers.
3. **Estimation**: the arithmetic, shown. Anchor on resume numbers where the kit is one of his systems.
4. **API**: 2–5 endpoints or event contracts.
5. **Data model**: stores, keys and access patterns, and why each store was chosen.
6. **Components**: for each box, *what it is · why it's needed · what breaks without it · the scaling knob*. These become the click-through panels.
7. **Request flows**: 2–3 numbered paths through the diagram (for example, read path, write path, async/offline path).
8. **Deep dives**: the two components an interviewer goes deep on, done properly.
9. **Failure modes**: where data can be lost, the single point of failure you accept, what breaks at 10× traffic.
10. **Trade-offs**: what was chosen *against*, and why.
11. **v1 vs later**: what a 2-person team ships in 6 weeks.
12. **Interviewer follow-ups**: 6–8 probes with one-line answers. These become drill cards.
13. **Your anchor** (resume-based kits): prompts for *his* real numbers and choices, never invented claims about what he built.

### Build session checklist

1. Read this README, pick the first `todo` in the catalog, and set it to `building`.
2. Write `design.md` and check it against the R4 rubric. Then write `kit.json` (positions are grid cells; see kit 01).
3. Build and publish `page.html`. Look at the page once, then fix anything wrong.
4. Start two Sonnet subagents in parallel: one for the card (render it with headless Edge and check the PNG), one for the narrative.
5. Add 5–8 follow-up probes to `drill/deck.json` (deck `sd-NN`). Rebuild and republish the drill page.
6. Mark the kit `done`, add its links to **Built kits**, and commit.

## Built kits

| # | Design | Page | Card | Audio script |
| --- | --- | --- | --- | --- |
| 01 | News feed at 100M req/day | [artifact](https://claude.ai/artifact/U8r5Dmuy624cpiuak2URbv) · [page.html](01_news_feed/page.html) | [card.png](01_news_feed/card.png) | [narrative.md](01_news_feed/narrative.md) |
