# Roadmap: Backend Engineer → AI Consultant

Owner: Aniruddha K · Created: 2026-10-14 · Status: living document, edit freely
Companion file: [PREP_TODO.md](PREP_TODO.md), the week-by-week running to-do with dates and checkboxes. This file is the *why and what*; that file is the *when*.

---

## 0. How to read this

- Sections 1–4 are strategy: what the job really is, where you stand, what to aim for. Read once, re-read every quarter.
- Sections 5–7 are the skill map and the phased plan. These are what the voice agent teaches from.
- Sections 8–13 are execution: portfolio, public proof, credentials, reading list, job targets, getting into consulting.
- Sections 14–16 are guard rails: anti-patterns, progress signals, and how this repo should evolve.

Depth labels used throughout:

| Label | Meaning | Test |
| --- | --- | --- |
| **Explain** | You can explain it clearly to a peer without notes | Voice agent asks, you answer in under 2 minutes with no hand-waving |
| **Build** | You have built it yourself, end to end | There's code in a repo you can show |
| **Operate** | You have run it with real traffic, metrics and failures | You can name a failure mode you debugged and the number that moved |
| **Advise** | You can tell a client whether and how to do it, with trade-offs and costs | You can write a one-page recommendation a CTO would sign off on |

---

## 1. The honest picture

**Your fear is partly right, but the conclusion needs adjusting.** Routine backend work is getting cheaper fast. CRUD services, glue code, boilerplate infra and "translate this ticket into an endpoint" are exactly what coding agents are good at. An engineer whose value is *typing code* has a shrinking market.

But "AI consultant" as a pure advisory role, with slides and strategy and no building, is *also* fragile. That market fills with generalists, MBA-track consultants and people who read the same newsletters. When the hype cycle cools, the people who survive are the ones who **can take an AI idea and make it work reliably inside a real business**: with real data, real security, real cost limits and real users. That is mostly a backend, infra and data problem with an LLM in the middle. **That's your moat, and you already have most of it.**

So the target isn't "stop being a backend engineer and become a consultant." It's this:

> **A backend/infra engineer who can design, ship, evaluate and operate AI systems, and who can sit with a business owner, find where AI actually pays off, and say no when it doesn't.**

The titles for that are *AI Engineer → Senior/Lead AI Engineer → AI Solutions Architect / Forward-Deployed Engineer → AI Consultant / Principal*. Consulting is the *last* step, earned by having shipped things, not the first.

**One more honest point.** You said you went a year without touching fundamentals and struggled to recall. That's normal, and it's fixable in about 4 months of steady work, which is what [PREP_TODO.md](PREP_TODO.md) is for. But it tells you something important: **knowledge you don't use decays fast.** Whatever you learn in this roadmap, build something with it, or it will be gone again in a year. That's why every phase below has a build output, not just reading.

---

## 2. What "AI consultant" actually means: pick your flavour

The title is used for very different jobs. Know which one you're aiming at, because they're hired on different things.

| Flavour | What they actually do day to day | What gets them hired | Interview shape | Fit for you |
| --- | --- | --- | --- | --- |
| **Applied AI / AI Engineer** (product or GCC) | Build LLM features: RAG, extraction, agents, evals, LLM gateways. Own them in production. | Shipped AI systems, eval discipline, backend strength | Coding + LLM app take-home + AI system design + backend fundamentals | **Very high, and it's your next job.** Closest to what you do at Aventum already. |
| **AI Solutions Architect / Forward-Deployed Engineer (FDE)** (AI vendors, cloud providers, AI startups, SIs) | Sit with customers, scope use cases, build PoCs fast, architect production rollouts, unblock integration | Breadth across cloud/infra/AI, customer communication, speed to working demo | System design with a customer twist, live build, presentation/role-play | **High, 12–24 months out.** Your multi-cloud + multi-domain history is exactly this profile. |
| **AI Consultant at a firm** (Big 4, Accenture-type, boutiques) | Discovery workshops, use-case portfolios, business cases, PoCs, governance frameworks, delivery management | Client presence, structured thinking, domain knowledge, some technical credibility | Case interviews, client role-play, a technical round | **Medium.** Good pay and exposure, but you'd risk drifting away from building. Viable if you want to go that way. |
| **Independent AI consultant / small practice** | Find clients, sell, scope, deliver small builds or advisory retainers | Reputation, network, case studies, a narrow niche | No interview, just sales conversations | **Long-term option (2–3+ years).** Needs public proof and a niche first. Insurance is a strong one. |

**Recommendation:** aim at **Applied AI Engineer now**, use it to get **Operate**-level evidence, then move to **AI Solutions Architect / FDE**. Keep independent consulting as a side option that grows out of your niche and public work. That sequence keeps you employable the whole way and doesn't bet your income on a pivot.

---

## 3. Where you're starting from

### Assets (things many "AI consultants" don't have)

From your resume and Round 1/5 sessions:

- **You're already doing applied AI work at Aventum:**
  - Orbit/Ayana extracts information from insurance agents' inboxes. That's document AI plus workflow.
  - You built an internal RAG pipeline.
  - You built an MCP server for Pulse.
  - You built an agent as a Cellular replacement.

  Most people pivoting to AI have none of this. You have four AI systems in a regulated domain.
- **Insurance domain: specialty, delegated authority, raters, quotes, policy documents.** It's a niche that's document-heavy, rule-heavy, regulated and slow to modernise. Ideal for AI consulting.
- **RLHF evaluation dashboard (Turing).** You've seen how model outputs get judged. Evaluation is the most under-supplied skill in applied AI.
- **Scale and infra credibility:** Jio's 100M req/day and 100k resumes/day, K8s across GKE and AKS, all three clouds, queues, Terraform. AI systems in production fail on exactly these things.
- **Consulting experience already on paper:** StatusNeo Consultant (McKinsey OHI, Jio), and you led a team of 10 data scientists' infra needs. You've already worked *for clients* and *with ML people*.
- **Builder-from-zero track record:** GeoStorm from scratch with SOC2 in mind, and the Jio recommender built single-handedly. Consultants who can actually build are rare.

### Liabilities (be honest about these)

From [knowledge_map.json](../progress/knowledge_map.json) as of 2026-10-10:

- **Fundamentals are rusty:**
  - weak: python_internals, security_auth
  - developing: async, resilience, containers (and declining), kubernetes
  - Interviewers *will* test these before they let you talk about AI.
- **Large untested areas:** system_design, databases, distributed systems theory, estimation, AI infra and staff leadership are all unrated. System design is the single biggest gate for senior roles.
- **AI is "developing / flat".** You've built AI things, but you can't yet *defend* them at depth: evals, retrieval metrics, failure modes, cost math.
- **Job stability narrative:** several short stints recently (4 months, 6 months, 12 months). Interviewers will probe it. Consultants get a pass on short engagements *if* the framing is "engagements with outcomes". That's a framing to work on in Round 1 prep.
- **No public proof.** Nothing on GitHub or in writing that a stranger can verify. For consulting, this matters more than certifications.

---

## 4. The target shape: a T with three layers

```text
                ┌──────────────────────────────────────────────────────────┐
  CONSULTING    │ discovery · use-case ROI · build-vs-buy · governance ·   │  ← makes you trusted
  LAYER         │ writing · workshops · scoping · pricing · change mgmt    │
                ├──────────────────────────────────────────────────────────┤
  AI            │ LLM mechanics · RAG · agents/MCP · document AI · EVALS · │  ← makes you relevant
  ENGINEERING   │ LLMOps · AI security · fine-tuning (when) · serving      │
                ├──────────────────────────────────────────────────────────┤
  ENGINEERING   │ Python · async · APIs · DBs · queues · K8s · cloud ·     │  ← makes you credible
  BASE (stem)   │ security · distributed systems · SYSTEM DESIGN           │     (and interviewable)
                └──────────────────────────────────────────────────────────┘
                     domain spike: INSURANCE / SPECIALTY / DOCUMENT-HEAVY
```

You build bottom-up but **in parallel, not in sequence**. The engineering base gets most of the hours for the first ~4 months because it gates every interview. The AI layer runs alongside it on weekends. The consulting layer starts small (writing, scoping) and grows from month 4.

---

## 5. Skill map in detail

Each item has a target depth for **12 months from now** (Oct 2027). Items marked ★ are the highest return for you specifically.

### Layer 1: Engineering base

This layer is covered week by week in [PREP_TODO.md](PREP_TODO.md) Phases 1–4 and maps onto Rounds 1–6 in `questions/`. Target by Feb 2027: every area at **solid** in the knowledge map, with system design at least **solid**. The AI-specific additions to the base are:

| Topic | Why it matters for AI work | Target |
| --- | --- | --- |
| ★ Async Python + rate-limited concurrency | Every LLM pipeline is I/O-bound fan-out against rate limits | Build/Operate |
| ★ Queues, retries, idempotency, DLQs | Batch extraction and ingestion jobs are long, flaky and expensive. Re-running costs real money | Operate |
| Postgres + pgvector, indexing (HNSW/IVFFlat) | Most companies should start with vectors in Postgres, not a new database | Build |
| ★ Observability + tracing (OpenTelemetry) | LLM calls are slow and non-deterministic. Without traces you can't debug them | Build |
| Security: authn/z, secrets, tenancy, PII | AI apps leak data across tenants through retrieval if authz is wrong | Advise |
| Cost modelling + capacity estimation | Token cost and GPU cost decide whether a use case is viable at all | Advise |

### Layer 2: AI engineering

#### 2.1 LLM fundamentals: enough to reason, not to research (target: Explain)

- Tokens and tokenization; why token counts differ between models; context windows and what "lost in the middle" means.
- How generation works: next-token prediction, sampling (temperature, top-p), why outputs vary, and why temperature 0 still isn't fully deterministic.
- Transformer at the whiteboard level: embeddings → attention → feed-forward → logits. What the KV cache is and why it makes long contexts expensive.
- Pre-training vs instruction tuning vs RLHF/RLAIF vs reasoning models. Connect RLHF to your Turing work: you built the tool that feeds this.
- Embeddings: what similarity means, cosine vs dot product, dimensionality, why domain matters.
- Model landscape: frontier closed models (Claude, GPT, Gemini) vs open-weight (Llama, Qwen, Mistral, DeepSeek families). Small vs large; when a small model is enough.
- Prompt caching, batch APIs, and the latency/cost/quality triangle.

#### 2.2 Prompting and structured outputs (target: Build)

- System prompts, few-shot examples, giving the model room to reason, decomposing tasks.
- ★ Structured output: JSON schema, Pydantic models, tool-call-as-schema, validation + repair loops, and when to fall back.
- Prompt versioning, and treating prompts as code: tests, review, rollback.
- Long-document strategies: map-reduce, refine, and when to just use a long context.

#### 2.3 Retrieval and RAG (target: Operate) ★

- Ingestion: parsing PDFs, DOCX, emails and spreadsheets; OCR; tables; layout. In insurance, this is 60% of the work.
- Chunking strategies: fixed, recursive, semantic, structure-aware (headings, clauses). Parent-child chunks.
- Retrieval: dense, sparse (BM25), hybrid with reciprocal-rank fusion; metadata filters; rerankers (cross-encoders).
- Query side: rewriting, multi-query, HyDE, routing.
- Generation: grounding, citations, refusing when context is missing.
- ★ Permission-aware retrieval: document-level ACLs enforced *at retrieval time*. This is the classic enterprise RAG data leak.
- Freshness and re-indexing; deletes ("right to be forgotten" in a vector index).
- When *not* to use RAG: use SQL or an API for structured data, and plain long context for small corpora.

#### 2.4 Agents, tool use and MCP (target: Build → Operate) ★

- Workflows vs agents. Most production "agents" should be workflows with one or two LLM decision points. Read Anthropic's *Building Effective Agents* and be able to argue it.
- Tool calling mechanics, tool design (names, descriptions, error messages written for the model), and parallel tool calls.
- The agent loop from scratch, without a framework: plan → act → observe → stop conditions, budgets, max steps.
- Memory: conversation, scratchpad, long-term; context management and compaction.
- ★ MCP: servers, clients, tools, resources, prompts, transports, auth. You built one, so be able to defend its design.
- Human-in-the-loop: approval gates, confidence thresholds, escalation. This is critical for insurance decisions.
- Multi-agent: when it helps (parallel research, separation of concerns) and when it's just cost and confusion.
- Frameworks: know one well (LangGraph, Pydantic AI, OpenAI Agents SDK or Claude Agent SDK). Understand the primitives underneath so you can switch.

#### 2.5 Document AI and extraction (target: Operate) ★ your niche

- Pipelines: classify → extract → validate → human review → write back.
- OCR and layout models vs vision-capable LLMs reading pages directly. Cost and accuracy trade-offs.
- Schema design for extraction; field-level confidence; cross-field validation rules (dates, sums, policy limits).
- Email intake: threading, attachments, deduplication, broker-specific formats.
- Measuring it: field-level precision/recall, straight-through-processing rate, and human-correction rate as your north-star metric.

#### 2.6 Evaluation (target: Operate → Advise) ★★ highest return

This is where you stand out. Most teams ship AI on vibes.

- Error analysis first: read 100 outputs, cluster the failures, then decide what to measure.
- Golden datasets: building, versioning and growing them from production failures.
- Metric types:
  - deterministic checks: schema, regex, exact match
  - retrieval metrics: recall@k, MRR, nDCG
  - LLM-as-judge, with calibration against human labels
  - pairwise comparison
- Offline evals in CI (prompt or model change → eval run → gate), and online evals (sampling production traffic, user feedback signals).
- Regression testing when the model provider updates the model.
- Connect to RLHF: preference data, rubric design, inter-annotator agreement. You've done this; frame it.

#### 2.7 LLMOps / production (target: Operate) ★

- LLM gateway pattern: one internal API in front of providers that handles auth, rate limits, retries with fallback, caching (exact and semantic), budgets per team, and logging.
- Tracing every call: prompt version, model, tokens, latency, cost, trace ID linking to the user request.
- Latency: streaming, parallelism, smaller models for easy steps, prompt caching, speculative patterns.
- Cost: per-request cost math, per-tenant budgets, batch APIs for offline work.
- Reliability: timeouts, provider outages, multi-provider fallback, degraded modes.
- Deployment: prompt/model rollout with feature flags, shadow mode, A/B tests.

#### 2.8 AI security and safety (target: Advise)

- OWASP Top 10 for LLM Applications. Know each item with one mitigation.
- Prompt injection, direct and indirect (through retrieved docs and emails). This is critical for inbox automation like Orbit.
- Data exfiltration through tools; least-privilege tool design; output filtering.
- PII detection and redaction; data residency; vendor data-retention terms.
- Guardrails: input/output classifiers, allow-lists, policy checks.

#### 2.9 Model adaptation (target: Explain → Build once)

- Decision ladder: prompt → few-shot → RAG → fine-tune → train. Know why most problems stop at step 2 or 3.
- Fine-tuning types: full, LoRA/QLoRA, preference tuning (DPO). When it's worth it: style or format consistency, latency or cost from distilling into a small model, or a narrow classification task.
- Do one small LoRA fine-tune yourself so you can speak from experience.

#### 2.10 AI infrastructure and serving (target: Explain, Build lightly)

- Self-hosting vs API: when it makes sense (data residency, cost at volume, latency). Usually later than people think.
- Serving engines (vLLM, TGI, Ollama for local); continuous batching; KV cache; quantization (int8/int4, GGUF/AWQ).
- GPU basics: memory math for model size, throughput vs latency, and autoscaling on K8s. Your K8s base pays off here.
- Covered in Round 6 K. Your knowledge-map entry is unrated.

#### 2.11 Classic ML literacy (target: Explain)

You'll be in rooms with data scientists, as you were at Jio. Know:

- train/val/test splits, overfitting, precision/recall/F1, ROC-AUC
- class imbalance
- when a gradient-boosted tree beats an LLM: tabular risk scoring, which is very common in insurance
- feature stores, and the basic MLOps life cycle

Not deep, just enough not to propose an LLM for a problem logistic regression solves.

#### 2.12 Platforms (target: Build on one, Explain the others)

- **Azure first:** Azure OpenAI / AI Foundry, AI Search, Document Intelligence. You're already Azure-heavy, and your current domain runs on it.
- Then AWS Bedrock (plus Textract) and GCP Vertex AI at the "explain the equivalent" level.
- Direct provider APIs (Anthropic, OpenAI) for portfolio projects.

### Layer 3: Consulting

This is the layer engineers skip, and it's what makes someone a *consultant* rather than a contractor.

#### 3.1 Discovery and problem framing ★

- Running a discovery session: stakeholders, current process, volumes, error costs, who does the work today and how long it takes.
- Turning "we want to use AI" into "underwriters spend 40 min per submission re-keying broker emails into the rating tool; 30% of submissions are declined after that effort."
- Process mapping before solution design. Measure the baseline *before* you build, or you can never prove value.

#### 3.2 Use-case portfolio and prioritization

- Scoring use cases on **value × feasibility × risk** (data availability, error tolerance, regulatory exposure, integration effort).
- Quick wins vs strategic bets; the "AI where errors are cheap and volume is high" heuristic.
- Recognising non-AI problems: often the fix is a form, an API or a rules engine.

#### 3.3 Business case and ROI ★

- Hours saved × loaded cost, error reduction, faster turnaround leading to more quotes bound, revenue uplift.
- Full cost: tokens + infra + build + run + human review + change management.
- Token cost math at volume: e.g. 10k docs/day × 8k tokens × price. Know how to do this in your head (Round 6 I helps here).
- Payback period and sensitivity: "if accuracy is 85% instead of 95%, here's what happens to the case."

#### 3.4 Build vs buy vs partner

- Vendor landscape awareness: insurance-specific AI vendors, horizontal platforms, and hyperscaler services.
- Evaluation criteria: data control, integration, accuracy on *their* data, lock-in, pricing model, roadmap risk.
- When a client should buy a SaaS and you should just integrate it, instead of building.

#### 3.5 PoC → pilot → production

- Why most AI PoCs die: no baseline, no eval set, no owner, no integration path, demo data ≠ real data.
- Defining success criteria *before* the PoC. Pilot design: a limited user group, shadow mode, human review.
- The production checklist: security review, evals in CI, monitoring, cost controls, runbooks, rollback.

#### 3.6 Data readiness assessment

- Where's the data, who owns it, its quality, labelling, access permissions and retention rules.
- Building a labelled eval set with the client's SMEs: the most valuable artefact in any AI engagement.

#### 3.7 Governance, risk and compliance (target: Advise) ★ for insurance

- **EU AI Act:** a risk-based tiering. Life and health insurance risk assessment and pricing are listed as high-risk. Obligations phase in over 2025–2027; check current dates, because parts have been under revision.
- **UK context** (Aventum is in the London market): FCA expectations, Consumer Duty (fair outcomes), and model risk management principles.
- **Frameworks:** NIST AI RMF, ISO/IEC 42001 (AI management systems). Know what they are and when a client needs them.
- **Practical governance:** model inventory, use-case risk registers, human oversight design, audit logs, explainability for declined cases, bias testing.
- **Data protection:** GDPR and the India DPDP Act basics, lawful basis, vendor DPAs, data residency.

#### 3.8 Change management and adoption

- AI projects fail on adoption more often than on accuracy. Bring in users early, design for trust (show sources and confidence), and train champions.
- Measuring adoption: usage, overrides, time saved per user.

#### 3.9 Communication ★

- **Writing:** one-page exec summaries, design docs, recommendation memos. Structure: answer first, then reasons, then risks and next steps.
- **Demos:** demo real client data, show failures honestly, end with the decision you need.
- **Workshops:** running a 2-hour use-case discovery workshop.
- **Saying no:** with data, and with an alternative.

#### 3.10 Commercials (later, for independent work)

- Scoping and statements of work: deliverables, assumptions, exclusions, acceptance criteria.
- Pricing models: time & materials, fixed-price discovery, fixed-price PoC, retainer, value-based. Start with **fixed-price discovery sprints**; they're the easiest to sell.
- Managing scope creep, change requests, and the conversation where you tell a client their idea won't work.
- Legal and admin basics: contracts, IP ownership, liability caps, invoicing and tax. Only relevant if you ever go independent; until then, learn it by watching how your employer's SOWs are written.

---

## 6. Your wedge: insurance and document-heavy operations

Generic "AI consultant" is a crowded market. **"The engineer who has shipped AI into specialty insurance workflows"** is not. Lean into it.

### Use cases you can speak to credibly

Some come from work you've already done:

| Use case | Your evidence | AI pattern |
| --- | --- | --- |
| Submission intake from broker emails | Orbit/Ayana | Email classification + document extraction + human review |
| Rater / quote generation | Aurora/Pulse, Cellular | Deterministic engine + LLM for edge cases + agent alternative |
| Rater workbook → code conversion | Cellular transpiler + agent replacement | Code generation with verification against workbook outputs |
| Internal knowledge Q&A | Your org RAG pipeline | Permission-aware RAG with citations |
| Testing-team tooling | Pulse MCP | MCP server exposing domain operations to agents |
| Policy wording comparison | (new) | Clause-level diff + LLM explanation |
| Bordereaux processing (delegated authority) | (new; learn the domain) | Spreadsheet normalization + validation + anomaly flags |
| Claims FNOL triage | (new) | Classification + extraction + routing |
| Underwriting assistant | (new) | RAG over guidelines + risk summary + referral rules |
| Regulatory change monitoring | (new) | Document diffing + summarization + impact tagging |

### Domain knowledge to build (target: Explain)

- Insurance value chain: broker → MGA/coverholder → carrier/syndicate → reinsurer.
- Lloyd's market basics, delegated authority, bordereaux.
- Underwriting, rating, binding, endorsements and claims.
- What "loss ratio", "combined ratio", "GWP" and "premium leakage" mean, and why an underwriter cares.

**Confidentiality rule:** never use Aventum or client data, code or documents in public projects. Build public versions on synthetic or public data (public policy wordings, regulator PDFs, generated broker emails). Talk about work projects in terms of the problem, the architecture and the outcomes, never proprietary details.

---

## 7. Phased plan

Dates assume you start the PREP_TODO on Mon 2026-10-19 at ~10–12 focused hours per week, plus audio while walking.

### Phase 0: Re-foundation + AI basics (Oct 2026 → Feb 2027, ~18 weeks)

- **Goal:** interview-ready as a senior (7–8 years) backend engineer, with AI fundamentals rebuilt on weekends.
- **Main track:** [PREP_TODO.md](PREP_TODO.md) Weeks 1–18. Python → async → APIs → DBs → messaging → distributed → K8s/cloud → security → system design → mocks.
- **AI track (weekends):** LLM basics, structured extraction, async LLM pipelines, RAG v1 → v2 with an eval harness, MCP server, agent from scratch.
- **Outputs:**
  - knowledge map at solid in most areas
  - 2 portfolio projects started (P1 and P2 below)
  - a polished Round 1 story bank
- **Exit criteria:**
  - you can pass a mixed voice mock (R2 + R3 + R4) with no area below "partial"
  - you can whiteboard an AI system design (RAG or extraction) with evals and cost
- **Decision point (Feb 2027):** start applying for Senior Backend / AI Engineer roles, or keep building in your current role. Either way, continue to Phase 1.

### Phase 1: Applied AI engineer (Feb → Jun 2027)

- **Goal:** Build-level everywhere in Layer 2, and Operate-level on RAG, extraction and evals.
- **Work:**
  - Finish P1–P3; start P4.
  - Write 3 public case studies.
  - Do one LoRA fine-tune experiment.
  - Take one Azure AI certification if you want the badge (optional; see section 10).
- **At your job:** volunteer to own evals and observability for the AI products at work (Orbit, the RAG pipeline, the Cellular agent). Turn "I built it" into "I measured it, and here's the number that moved." That's Operate-level evidence, and it's better than any side project.
- **Consulting layer starts:** write one internal recommendation memo (e.g. "Should we fine-tune or prompt for extraction X?") and run one discovery-style session with a business team.
- **Exit criteria:**
  - you can answer every Round 5 question at solid or better
  - you have 3 public projects with READMEs and eval results
  - you have 1 internal "Operate" story with numbers

### Phase 2: AI solutions architect (Jun → Dec 2027)

- **Goal:** move from "I build what I'm told" to "I decide what should be built, and prove it."
- **Work:**
  - Advise-level on governance, security, cost and build-vs-buy.
  - Insurance domain at Explain level.
  - Run 2–3 discovery workshops at work, with business teams that want AI help.
  - Give a talk at a Bengaluru meetup.
  - Build P5 (LLM gateway) and P6 (domain demo).
- **Job move window:** AI Solutions Architect, FDE, Lead AI Engineer, or a GenAI practice at a consulting firm or GCC.
- **Exit criteria:**
  - a portfolio of 5+ projects and 5+ write-ups
  - at least 1 engagement-style story: discovery → recommendation → PoC → outcome
  - you can do a 45-minute AI consulting case interview (Round 7 idea, section 16)

### Phase 3: Consultant (2028 →)

- **Goal:** paid advisory work, inside a firm or independently.
- **Work:**
  - Package offers: *AI Readiness & Use-Case Discovery (2 weeks, fixed price)*, *Extraction PoC with eval harness (4–6 weeks)*, *Production hardening review for an existing AI app (1–2 weeks)*.
  - Move into a consulting-shaped role: a firm's AI practice, a vendor's solutions team, or an internal AI advisory role. No side work needed.
  - Build referral sources: past colleagues, insurance-market contacts, and AI vendors who need implementation partners.
- **Exit criteria:** repeatable offers, 3+ client references, and an inbound lead now and then from your writing.

### Phase 4: Principal / practice lead (2029 →)

- Staff/Principal AI Architect in a company, or a small practice with 1–3 associates.
- At this level you're paid for judgment, risk management and trust. The engineering base keeps you honest.

---

## 8. Portfolio projects

Public GitHub, synthetic or public data only. Each needs a README with: problem, architecture diagram, how to run it, **eval results table**, cost per request, known limitations, and what you'd do next. The eval table is what separates you from tutorial projects.

### P1. Insurance submission intake pipeline ★ (start in Phase 0)

- **Problem:** broker emails with attachments → structured submission record → human review queue.
- **Build:**
  - email/attachment ingestion → classification (new business / renewal / endorsement / other)
  - Pydantic-schema extraction with field-level confidence
  - validation rules → FastAPI review UI or API → Postgres
  - async workers with rate-limited LLM calls, retries and DLQ
- **Eval:**
  - a synthetic set of ~100 emails with ground truth
  - field-level precision/recall
  - straight-through rate at different confidence thresholds
- **Proves:** document AI, structured outputs, async pipelines, evals, your domain.
- **Stretch:** prompt-injection test cases hidden inside emails, plus defences.

### P2. Permission-aware RAG with an eval harness ★ (start in Phase 0)

- **Problem:** Q&A over a corpus of public policy wordings or regulatory documents, with per-user document access.
- **Build:**
  - structure-aware chunking; hybrid search in Postgres (pgvector + full-text) with RRF; a reranker
  - citations; refusal when the answer isn't in the context
  - ACL filtering at retrieval time
- **Eval:**
  - a golden set of 50+ questions
  - recall@k, MRR, faithfulness (LLM-judge calibrated on 30 human labels), answer correctness
  - a table comparing v1 naive → v2 hybrid → v3 reranked
- **Proves:** RAG depth, eval discipline, and security thinking.

### P3. MCP server + agent for a rater (Phase 1)

- **Problem:** a public, made-up rating spreadsheet (e.g. a simple property rater) exposed as tools; an agent quotes from a natural-language request.
- **Build:**
  - convert the rater to Python (Cellular-style) with tests against workbook outputs
  - an MCP server exposing `rate`, `explain_rating` and `list_factors`
  - an agent that gathers missing info, calls tools and shows its working
  - human approval before "bind"
- **Eval:** task success on 30 scenarios; tool-call correctness; average steps and cost.
- **Proves:** agents, MCP, deterministic + LLM hybrid design (the right answer for pricing).

### P4. Agent from scratch vs framework (Phase 1)

- The same task built three ways: a raw loop with no framework, then one framework, then a workflow (not an agent).
- Compare reliability, cost, latency and code complexity.
- Short write-up: "When you don't need an agent."
- **Proves:** you understand the primitives and can argue trade-offs, which is consulting judgment.

### P5. LLM gateway (Phase 2) ★ plays to your backend strength

- **Build:**
  - a FastAPI service in front of 2+ providers
  - per-key rate limits (token bucket), budgets, retries with fallback, exact + semantic cache
  - streaming pass-through, OpenTelemetry traces, a Prometheus cost/latency dashboard
- **Deploy:** on K8s (kind), reusing your graceful-shutdown demo.
- **Proves:** LLMOps, infra and resilience: the "backend engineer who does AI" story in one repo.

### P6. Fine-tune vs prompt experiment (Phase 1–2)

- **Task:** a narrow classification or extraction task (e.g. email intent).
- **Compare:** zero-shot frontier model vs few-shot vs a LoRA-tuned small open model. Measure accuracy, latency and cost per 1k.
- **Proves:** you can give an evidence-based answer to "should we fine-tune?"

### Optional P7. Bordereaux normaliser (Phase 2, domain-deep)

- Messy coverholder spreadsheets in different formats → a canonical schema, with validation and anomaly flags.
- Very niche, very valuable in the London market, and a great consulting conversation starter.

---

## 9. Public proof and brand

You don't need to be an influencer. You need **a stranger to be able to verify you're good in 10 minutes.**

- **GitHub:**
  - a pinned profile README (one paragraph: backend/infra engineer building production AI for insurance and document-heavy operations)
  - 3–6 pinned projects with eval tables
- **Write-ups:** 1 per month from Phase 1 on. Formats that work:
  - "How I evaluated X"
  - "What broke when we put Y in production" (sanitized)
  - "Fine-tune vs prompt: the numbers"
  - "A checklist for prompt injection in email-processing agents"

  Post on LinkedIn, plus a simple blog or GitHub Pages.
- **LinkedIn:** rewrite your headline from "Python Backend Developer" to something like *"Backend & AI Engineer · Production LLM systems (RAG, document AI, agents) · Insurance · Azure/K8s"*. Do this once P1 and P2 exist, so it's true.
- **Talks:** Bengaluru has active Python, cloud-native and GenAI meetups. One 20-minute talk on "evals for document extraction" is worth more than 10 certificates.
- **Network:** keep in touch with ex-colleagues from Jio, StatusNeo, Turing and DataWeave. Most first consulting clients come from people who already trust you.

---

## 10. Credentials: optional, and lower value than projects

Certifications help with recruiters and consulting firms' screening, not with senior engineering interviews. If you take any, keep it to one or two that match the platforms you use. **Verify current names, exam codes and status before booking; these change often.**

- **Azure AI Engineer Associate (AI-102):** the best fit, given your Azure background and current domain.
- AWS: Certified AI Practitioner (foundational), plus the newer generative-AI developer certification if it's generally available by the time you're ready.
- Google Cloud Generative AI Leader (business-oriented). Only if you're targeting GCP-heavy consulting.
- CKA/CKAD (Kubernetes). Useful if you go the AI-infra route, and it forces real K8s fluency.
- Governance: ISO/IEC 42001 lead implementer or similar. Only in Phase 3, if governance consulting becomes a real line of work.

---

## 11. Learning resources

Prefer one good source per topic, finished, over five half-read ones. ✅ = start here.

### Engineering base

- ✅ *Designing Data-Intensive Applications*, Martin Kleppmann. The backbone for databases, replication, partitioning and streaming.
- ✅ *Fluent Python* (2nd ed.), Luciano Ramalho. Python data model and internals.
- *Architecture Patterns with Python*, Percival & Gregory. DDD, repository pattern and events in Python.
- *System Design Interview* vols 1–2, Alex Xu. Interview structure and classic designs.
- *Kubernetes in Action*, Marko Lukša, or the official docs concepts section.
- *The Staff Engineer's Path*, Tanya Reilly. Leadership and influence (Round 6 A).
- Your own `answers/` files plus NotebookLM audio for review, and `scripts/` for hands-on practice.

### AI engineering

- ✅ Andrej Karpathy's YouTube: *Intro to Large Language Models* (1 hour) and *Deep Dive into LLMs like ChatGPT*. Then *Let's build GPT* if you want the internals.
- ✅ *AI Engineering*, Chip Huyen (O'Reilly, 2025). The closest thing to a textbook for this role.
- ✅ Anthropic, *Building Effective Agents* (engineering blog). Read it twice.
- ✅ Hamel Husain's writing on evals (start with *Your AI Product Needs Evals*). Also Eugene Yan's *Patterns for Building LLM-based Systems & Products*.
- Jay Alammar, *The Illustrated Transformer*. Visual intuition.
- OWASP Top 10 for LLM Applications (current edition).
- Provider docs: the Anthropic and OpenAI cookbooks; Azure AI Foundry docs; the MCP specification and docs.
- DeepLearning.AI short courses, which are free and about an hour each. Good for a specific tool, not for depth.

### Consulting

- ✅ *The Trusted Advisor*, Maister, Green & Galford. How advisors earn trust.
- *The Secrets of Consulting*, Gerald Weinberg. Short, sharp and engineer-friendly.
- *The Pyramid Principle*, Barbara Minto. How to write recommendations: answer first.
- *Million Dollar Consulting*, Alan Weiss. Only when you go independent; it's about pricing and selling.

### Insurance domain

- The Lloyd's website (market basics, delegated authority), Insurance Institute / CII introductory material, and your own colleagues. Ask underwriters to walk you through their day. That's discovery practice too.

---

## 12. Job targets and how AI interviews differ

### Titles to search for (Phase 0 → 2)

Senior Backend Engineer (AI products) · AI Engineer / Applied AI Engineer · Senior/Lead GenAI Engineer · LLM Platform Engineer · AI Solutions Architect · Forward-Deployed Engineer · GenAI Consultant (technical track) · AI Platform/Infra Engineer.

### Where (Bengaluru and remote)

- Global capability centres (GCCs) building AI platforms, including insurance and financial-services GCCs where your domain is a plus.
- AI-native startups.
- AI model and tooling vendors' solutions/FDE teams.
- Hyperscaler partner teams.
- Consulting firms' GenAI practices.
- InsurTech companies, especially London-market ones with India teams.

### What AI-engineer interviews add on top of the backend loop

- **LLM app take-home or live build:** e.g. "build an extraction endpoint with evals in 3 hours." Judged on structure, error handling, evals and README, not just whether it works.
- **AI system design:** "design a RAG system for X" or "design document processing for Y." They want ingestion, retrieval, evals, cost, latency, security and the human in the loop.
- **Eval discussion:** "how do you know it's working?" This is the most common failure point. Practise with Round 5 F.
- **Debugging scenarios:** "accuracy dropped after a model update," "answers cite the wrong document," "costs tripled."
- **Opinion and judgment:** "when would you not use an LLM?", "agents vs workflows?", "fine-tune or RAG?"
- **Consulting/FDE roles add:** customer role-play, a live discovery conversation, and presenting a recommendation.

---

## 13. Getting into consulting through role moves, not side work

1. **Be the AI person at your current job.** You mostly already are. Make it visible: internal demos, write-ups, eval dashboards and guidance docs for other teams.
2. **Internal consulting:** offer other teams or business units a 1-hour "is AI right for this?" session. This is discovery practice with zero sales risk.
3. **Collect engagement-shaped stories at work:** discovery → recommendation → PoC → measured outcome. Write each one up (sanitised) in the Round 7 case format. These stories are what consulting interviews ask for.
4. **Move internally** into an AI lead or architect role if one opens up. It's the cheapest way to get the title and the scope.
5. **Move externally** to an AI Solutions Architect, FDE or GenAI-practice role at a consulting firm or vendor. It's consulting with a salary, and the main path in this plan.
6. **Independent practice** stays an optional, far-future idea: only with a niche, 3+ client references, and 6–12 months of runway.

---

## 14. Anti-patterns to avoid

- **Tutorial hell.** Watching courses without building. Rule: every learning week ends with code or a written explanation.
- **Chasing every model release.** Fundamentals (retrieval, evals, cost, reliability) change slowly; model names change monthly. Spend 30 minutes a week on news, max.
- **Framework-first learning.** Learning LangChain before you can write the agent loop yourself. Primitives first.
- **Certificate collecting.** One, maybe two. Projects and write-ups count for more.
- **Skipping fundamentals because "AI will replace backend."** Every AI interview still tests system design and backend depth, and every production AI failure is ultimately an engineering failure.
- **Over-claiming.** Your resume claims (100M req/day, 100k resumes/day) must be defensible with real numbers. The same goes for AI claims: don't say "agentic" if it's a workflow, and don't claim accuracy you never measured.
- **Using employer data publicly.** It ends careers.
- **Going independent too early.** Consulting without a niche, references and runway means taking any work at any rate.

---

## 15. Signals you're on track: quarterly check

At the end of each quarter, answer these honestly. The voice agent can run this as a review session.

- **Q4 2026 (end Dec):**
  - Phase 1–2 base areas mostly solid
  - P1 v1 running with an eval set
  - you can explain tokens, embeddings, RAG and evals without notes
- **Q1 2027 (end Mar):**
  - interview-ready on backend (mock pass)
  - P1 + P2 public with eval tables
  - first write-up published
  - applying or deliberately not applying
- **Q2 2027 (end Jun):**
  - 3 projects
  - 1 Operate-level work story with numbers
  - you've run 1 discovery session
  - Round 5 all solid
- **Q3 2027 (end Sep):**
  - LLM gateway built
  - insurance domain at Explain level
  - 1 meetup talk or long-form post
  - interviews for AI SA/FDE roles going well
- **Q4 2027 (end Dec):**
  - in an AI-titled role, or a clear path to one
  - 5+ write-ups
  - first full engagement-style story from work (discovery → outcome)

If two quarters in a row miss most of their signals, the plan is too big for your available hours. Cut scope (drop P6/P7, slow the timeline). Don't just feel guilty.

---

## 16. How this repo should evolve (suggestions)

Your idea is early, so here's a structure that scales from "Q&A bank" to "personal teaching system":

```text
interview/
├── CLAUDE.md                  # rules for any agent (interviewer + teacher modes)
├── plan/
│   ├── AI_CONSULTANT_ROADMAP.md   # this file: strategy (quarterly review)
│   └── PREP_TODO.md               # running to-do: what this week is (daily/weekly)
├── teach/                     # NEW (suggested): lesson plans for teacher mode
│   └── W03_async.md           #   per-week: concepts in order, analogies, checks for understanding,
│                              #   "explain it back" prompts, links to scripts/ and answers/
├── questions/                 # interview banks (add ROUND_7_ai_consulting_case.txt later)
├── answers/                   # reference answers → NotebookLM audio
├── scripts/                   # runnable refreshers (async, k8s, ... add llm/, rag/ later)
├── labs/ or portfolio links   # NEW (suggested): pointers to P1–P7 repos, eval results
└── progress/
    ├── knowledge_map.json     # add AI-engineering + consulting skill areas when Phase 1 starts
    └── session_log.md
```

Concrete suggestions, in priority order:

Status 2026-10-14: items 1, 2 (via PREP_TODO + teach/), 3, 4 and 6 are done; 5 has a builder script (`scripts/tools/build_week_pack.py`). Weekly infographics live in `teach/infographics/`.

1. **Teacher mode needs lesson plans, not just question banks.** A voice teacher working from a Q&A bank will quiz you, not teach you. For each week in PREP_TODO, a short `teach/Wxx_topic.md` should list:
   - concepts in teaching order
   - the one analogy that makes each one click
   - 3 "explain it back to me" checks
   - common misconceptions
   - what to run in `scripts/`

   I can generate these a week or two ahead of where you are.
2. **Split the loop explicitly: learn → explain back → quiz.** PREP_TODO is built around this. The voice agent should never quiz on a topic you haven't been taught in the current cycle; it should teach first.
3. **Add a Round 7 bank: AI consulting case interviews.** "A Lloyd's syndicate wants to use AI in underwriting; you have 45 minutes." This tests discovery, prioritization, ROI, risk and architecture together. Start it in Phase 1.
4. **Extend knowledge_map.json with AI and consulting areas** (evals, document AI, LLMOps, AI security, discovery, business case, governance, insurance domain) when Phase 1 starts. Until then, the existing 24 areas are enough.
5. **NotebookLM audio per week**, not per round. Upload just that week's answer sections and the teach file, so the walking audio matches what you're learning that week.
6. **A misses file** (`progress/misses.md`): every question you fumble goes there with the fix in one line. Re-quiz from it weekly. It's the highest-yield review list you'll ever have.
