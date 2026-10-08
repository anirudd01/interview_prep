# Round 5 — AI / LLM Engineering: Answers, Part B (longer questions)

Companion to `questions/ROUND_5_ai.txt`. **Original question numbers are kept.** Part A (`ROUND_5_ai_answers_PART_A.md`) has the short/direct questions.

This file has the 41 questions that need a designed or multi-step answer: 14–16, 18, 22–24, 27–29, 35, 36, 38, 42, 43, 45–48, 50, 52, 53, 57, 58, 61–65, 67–72, 74–76, 78, 85, 90.

The three things this round grades hardest are **evaluation methodology**, **production concerns** (cost, latency, failure handling), and **knowing where determinism and humans must stay in control**. If you run out of time in an answer, make sure you've said something about each.

**Your story:** marks where only your real experience works.

---

## B. RAG - DESIGN AND QUALITY

### 14. Draw your org-knowledge RAG pipeline from Espire end to end: ingestion, chunking, embedding, storage, retrieval, reranking, prompt assembly, generation, citation.
Below is a strong reference pipeline (Azure-flavoured, since that's your stack). **Your story:** walk through it and be explicit about which boxes you actually had and which you'd add. Interviewers respect "we didn't have a reranker in v1; here's what I'd add and why".
**Offline / ingestion path**
1. **Sources & connectors**: SharePoint/OneDrive, Confluence/wiki, PDFs/Word in Blob storage, product/offering pages. Pull via connectors (Graph API, Azure AI Search **indexers** with blob/SharePoint data sources) on a schedule or change events. Capture **metadata**: source URL, title, owner, last modified, **ACLs** (who can see it), document type, department.
2. **Parsing**: extract text **with structure** (headings, lists, tables, page numbers) using Azure Document Intelligence (layout model) or library parsers (PyMuPDF, python-docx, unstructured). OCR for scans. Clean boilerplate (headers/footers, navigation).
3. **Chunking**: structure-aware: split by headings/sections, then recursively to a token budget (e.g. ~300–800 tokens with ~10–15% overlap), keep tables intact, prepend the **section path/title** to each chunk (Q15).
4. **Enrichment** (optional): contextual header per chunk, keywords, summaries; dedupe near-identical chunks.
5. **Embedding**: batch-embed chunks (Azure OpenAI embedding model), with retries/rate limits; store the **embedding model version** with each vector.
6. **Storage / index**: Azure AI Search index (vector field + full-text fields + filterable metadata + ACL fields), or Postgres + pgvector (+ `tsvector` for BM25-like full text). Idempotent upserts keyed by `doc_id + chunk_index + content_hash`.
**Online / query path**
7. **Query understanding**: conversational rewrite to a standalone question (if chat), extract filters (department, date), optional multi-query.
8. **Retrieval**: **hybrid** (BM25 + vector) with **security filters** applied inside the search (user's groups) → top ~50 (Q20, Q28).
9. **Reranking**: cross-encoder / Azure semantic ranker → top ~5–8 (Q21).
10. **Relevance gate**: if nothing passes the threshold → "I couldn't find this" (Q25).
11. **Prompt assembly**: system prompt (rules: answer only from context, cite sources, say NOT_FOUND, style), then the chunks with IDs and titles (best first), then the question. Token budget per section; stable prefix first for caching.
12. **Generation**: streaming (SSE) answer with inline citations, structured as `{answer, citations[], answerable}` where possible.
13. **Citation post-processing**: validate cited IDs exist, map to document links (page/section anchors), optional groundedness check.
14. **Logging & feedback**: trace per request (query, rewritten query, retrieved IDs + scores, prompt version, model, tokens, latency, answer), thumbs up/down with reasons → eval set (Part A Q80, Q78).
**Cross-cutting**: evaluation harness (golden set, recall@k, faithfulness: Q23/Q24), incremental re-indexing and deletions (Q27), permissions (Q28), cost and latency dashboards.

### 15. How did you chunk? Fixed size, recursive, semantic, or structure-aware? What chunk size and overlap, and how did you arrive at those numbers rather than copying a blog?
**Strategies**:
- **Fixed size** (e.g. 500 tokens, 50 overlap): simple, predictable; cuts sentences/tables/clauses in the middle and ignores document structure.
- **Recursive** (split on paragraphs → sentences → words until under the size limit, e.g. LangChain's RecursiveCharacterTextSplitter): respects natural boundaries; a good default for prose.
- **Semantic** (split where the embedding similarity between consecutive sentences drops: topic boundaries): sometimes better coherence, more compute, inconsistent chunk sizes, and gains are often small in practice.
- **Structure-aware** (use the document's own structure: headings, sections, clauses, list items, table boundaries, Markdown/HTML tags), then recursive within sections that are too long. **Best for structured business documents** like policies, procedures and contracts.
Important extras: **prepend the heading path / document title** to every chunk (so "4.2 Exclusions" chunks know which policy and section they belong to); keep **tables as whole units** (or rows with their header row); store chunk → page/section metadata for citations; consider **small-to-big / parent-document retrieval** (retrieve small precise chunks, then send their parent section to the LLM).
**Choosing size and overlap empirically** (the part the interviewer wants):
1. Build a golden set of questions with the passages that answer them (Q23).
2. Try a small grid: e.g. 256 / 512 / 1024 tokens × overlap 0 / 10% / 20%, and structure-aware vs recursive.
3. For each, measure **retrieval recall@k** (does the right passage appear in the top k?) and **end-to-end answer faithfulness/correctness** at a fixed prompt token budget. Smaller chunks → precise matching but fragmented context; bigger chunks → more context per hit but diluted embeddings and fewer chunks fit in the prompt.
4. Look at the **failure cases** (answers split across chunk boundaries → more overlap or structure-aware splitting; irrelevant text dominating chunks → smaller chunks).
5. Pick the best and **record the eval results** so the choice is defensible.
Typical outcome for policy-style documents: structure-aware sections, capped around 400–800 tokens, ~10–15% overlap, plus section titles prepended. But say these numbers came from **your** measurements.
**Your story:** if you used a default (e.g. 1000 characters / 200 overlap) without measuring, say that honestly, then explain this methodology as what you'd do now.

### 16. How do you chunk a 200-page insurance policy PDF with tables and nested clauses? What does naive chunking destroy?
**What naive (fixed-size) chunking destroys**:
- **Clause hierarchy and scope**: "4.2(b) This exclusion does not apply to..." lands in a chunk without its parent "Section 4: Exclusions" or the clause it modifies, so the meaning flips (an exception to an exclusion read as a cover grant).
- **Cross-references**: "subject to the conditions in Section 7" points to text that isn't retrieved.
- **Definitions**: insurance documents define terms ("Flood", "Insured Location") in a definitions section, and the meaning of a clause depends on them.
- **Tables** (schedules, limits, deductibles, sub-limits): split mid-table, rows lose their header row → numbers without meaning ("250,000" of what?).
- **Endorsements** that modify base wording later in the document; the base clause is retrieved without the endorsement that changes it.
- Page headers/footers repeated in every chunk (noise).
**Better approach**:
1. **Layout-aware parsing** (Azure Document Intelligence layout / similar): detect headings, numbering, paragraphs, tables, page numbers; remove headers/footers.
2. **Reconstruct the hierarchy**: build a tree from the clause numbering (1 → 1.1 → 1.1(a)) and headings.
3. **Chunk by clause/section** with the **full heading path prepended** ("Policy: Acme Commercial Property 2024 > Section 4 Exclusions > 4.2 Water damage > (b)"); split very long sections recursively, keeping subclauses with their parent's lead-in sentence.
4. **Tables**: keep each table as one chunk (if small) or chunk by rows **repeating the header row** in each; also store a Markdown/HTML rendering, and possibly a **structured representation** (JSON) for exact lookups of limits/deductibles. Numbers like limits are often better extracted into structured fields and queried with code than retrieved as text.
5. **Definitions**: index the definitions section separately; at answer time, automatically **attach the definitions of defined terms** that appear in the retrieved clauses (detect capitalised defined terms).
6. **Cross-references and endorsements**: link chunks with metadata (`references: [7.1]`, `modified_by: endorsement 3`) and fetch the linked chunks during retrieval (a simple graph expansion).
7. **Metadata** per chunk: policy ID, version/effective date, section number, page range, chunk type (clause/table/definition/endorsement), for filtering and citations.
8. **Evaluate** with questions that need definitions, tables and exceptions (these are exactly the questions naive chunking gets wrong).

### 18. pgVector vs ChromaDB vs Azure AI Search vs a dedicated vector DB - you've used several. Give me the real decision criteria, and where each falls over.
**Decision criteria**: scale (number of vectors, QPS), need for **hybrid search** and rich filtering, **permission filtering**, transactional consistency with your other data, operational burden and team skills, managed vs self-hosted, data residency, cost, ecosystem (indexers, connectors), latency requirements, and update patterns (frequent upserts/deletes).
- **pgvector (Postgres)**: vectors live **next to your relational data**, in the same transactions; joins and SQL filters (tenant, ACLs) for free; backups/HA/monitoring you already have; HNSW/IVFFlat indexes. Great up to roughly **millions to tens of millions** of vectors on a well-sized instance. **Falls over**: very large scale (index memory, build times), high QPS vector search competing with OLTP load on the same DB, filtered ANN recall issues (Part A Q19), and full-text search is weaker than a real search engine (no BM25 natively; `tsvector` ranking is simpler, though extensions help).
- **ChromaDB**: very easy embedded/local vector store; great for **prototypes, notebooks, small apps**. **Falls over**: production concerns: multi-tenancy, HA/replication, access control, scaling, operational tooling are limited compared to the others (its hosted/distributed offerings are improving, but it's rarely the enterprise choice).
- **Azure AI Search**: a full managed **search engine**: BM25 + vectors + **hybrid with RRF** + **semantic ranker** (reranker) built in, **indexers** that pull from Blob/SharePoint/SQL automatically with enrichment (OCR, chunking, embedding skills), security filtering patterns, Azure-native networking and residency. Excellent for enterprise document RAG on Azure. **Falls over**: cost at higher tiers/replicas, index schema changes often require re-indexing, less flexibility than code you control, service limits per tier (index size, vector quotas), and lock-in to Azure.
- **Dedicated vector DBs** (Pinecone, Qdrant, Weaviate, Milvus): built for **large-scale, high-QPS ANN** with good filtered search, sharding, and serverless options. **Falls over**: another system to run and keep in sync with your source of truth (dual-write issues), weaker relational/transactional features, extra cost; often unnecessary below ~tens of millions of vectors.
**Default recommendation**: use what you already run. Postgres app → pgvector; Azure document-heavy enterprise RAG → Azure AI Search (hybrid + semantic ranker + indexers save a lot of work); Chroma for prototypes; a dedicated vector DB only when scale/QPS justifies it.
**Your story:** explain why you used each one where you did (e.g. Chroma for an Ollama prototype, pgvector in an app with Postgres, Azure AI Search with indexers at Espire).

### 22. Your RAG answers a question wrong. Walk me through the debugging tree: is it a retrieval failure, a chunking failure, a ranking failure, or a generation failure? How do you tell them apart?
You need the **full trace** of that request (rewritten query, retrieved chunk IDs with scores and ranks before/after reranking, the final prompt, the answer). Then walk down the tree:
1. **Is the answer in the corpus at all?** Search the source documents manually. If not → **content/coverage gap** (or the document wasn't ingested: ingestion/parsing failure, e.g. scanned PDF without OCR, a failed indexer run, permissions excluding it). Fix ingestion or the answer should have been "I don't know" (a generation/gating failure).
2. **Is the right information in a chunk, intact?** Look at the chunks of the source document. If the answer is split across chunk boundaries, the table is broken, or the chunk lacks its context (heading, definition) → **chunking/parsing failure**.
3. **Was the right chunk retrieved in the candidate set (e.g. top 50)?** If not → **retrieval failure**. Sub-causes: the query wording doesn't match (vocabulary mismatch → hybrid/BM25, query rewriting), the embedding model doesn't understand domain terms, a metadata/permission filter wrongly excluded it, a conversational query wasn't rewritten ("what about the second one?"), filtered ANN returning too few results. Test by running the query against the index directly and finding the rank of the right chunk.
4. **Was it retrieved but not in the final top-k sent to the LLM?** → **ranking failure** (reranker or fusion ordered it too low, or k is too small). Check the reranker score of the right chunk vs the chunks that made it in.
5. **Was the right chunk in the prompt, but the answer was still wrong?** → **generation failure**. Sub-causes: the model ignored it (lost in the middle, too many distracting chunks), it mixed information from several chunks, the prompt instructions were unclear, the model answered from its own knowledge, or the question needed reasoning/calculation the model got wrong. Test by re-running with only the correct chunk: if the answer becomes right → noise/ordering; if still wrong → prompt or model capability.
6. **Was the answer actually wrong?** Sometimes the "ground truth" is outdated or the question is ambiguous → fix the eval data or add a clarification step.
Then **add the case to the golden set** with its failure category, and track counts per category: that tells you which component to invest in.

### 23. How do you measure retrieval quality? (Looking for: recall@k, MRR, NDCG, and a labelled golden set.) Do you have a golden set? Who built it?
**Golden set**: a list of realistic queries, each with the **IDs of the relevant chunks/documents** (and ideally graded relevance: 2 = answers it, 1 = partially relevant). Sources: real user queries from logs (best), SME-written questions, and LLM-generated questions from documents, reviewed by SMEs. Include hard cases: identifiers, multi-hop, unanswerable questions, paraphrases. Typically start with **50–200 queries**; grow it from production failures (Q78). Label at the **document/section level** if chunking changes often (so the labels survive re-chunking), or map relevant passages to chunks automatically by text overlap.
**Metrics**:
- **Recall@k**: fraction of queries (or of relevant items) where the relevant chunk appears in the top k. The most important one for RAG: if it's not retrieved, the LLM can't use it. Measure at the k you retrieve (e.g. @50 before reranking) and the k you send (e.g. @5 after reranking).
- **Precision@k**: fraction of the top k that are relevant (noise in the prompt).
- **MRR** (Mean Reciprocal Rank): average of 1/rank of the first relevant result: rewards having it at the very top.
- **NDCG@k**: accounts for graded relevance and position; best for comparing ranking quality overall.
- **Hit rate** for unanswerable questions: are low scores/no results correctly detected?
Use it: run the golden set on every change (chunking, embedding model, hybrid weights, reranker, query rewriting) and keep a results table. Track latency and cost alongside.
**Your story:** "Do you have a golden set? Who built it?" is a pass/fail question. If yes: size, who labelled (you + SMEs?), how it's maintained. If not: say so plainly and describe exactly how you'd build one in a week with SMEs (Q75 in Part B).

### 24. How do you measure answer quality? Faithfulness/groundedness, answer relevance, context precision/recall. Have you used RAGAS or an LLM-as-judge? What are the failure modes of LLM-as-judge?
**The RAG triad + correctness**:
- **Faithfulness / groundedness**: is every claim in the answer **supported by the retrieved context**? (Catches hallucination.) Typically: break the answer into claims, check each against the context with an LLM judge or an NLI model; score = supported claims / total claims.
- **Answer relevance**: does the answer actually address the question (not evasive, not off-topic)?
- **Context precision**: are the retrieved chunks relevant (and are the relevant ones ranked high)?
- **Context recall**: does the retrieved context contain everything needed for the reference answer? (Needs a reference answer.)
- **Answer correctness**: compared with a **reference answer** written by SMEs: factual overlap/semantic similarity or a judge comparing against the reference. The closest thing to "is it right?".
- Plus: **citation accuracy**, **correct refusal rate** on unanswerable questions, format compliance, latency, cost.
**Tools**: **RAGAS** implements these metrics (faithfulness, answer relevancy, context precision/recall) using LLM judges; also DeepEval, TruLens, promptfoo, Azure AI Foundry evaluators, Langfuse/LangSmith eval runs. They're conveniences, not ground truth: the judge model's quality decides the metric's quality.
**LLM-as-judge failure modes** (details in Part A Q77): position bias, verbosity bias, self-preference, leniency/score compression, inability to verify domain facts (fooled by fluent wrong answers), inconsistency across runs, prompt sensitivity, being influenced by text inside the evaluated answer. **Mitigations**: narrow binary rubrics, reference-based judging, position swapping, a different model family as judge, and above all **calibrating the judge against SME labels** on a sample (report agreement), and re-validating when the judge model changes.
**Your story:** say whether you used RAGAS/an LLM judge or only manual spot checks. If manual: be honest and propose this setup.

### 27. Documents change. How do you handle incremental re-indexing, deletions, and stale embeddings? What happens when you switch embedding models - full re-embed?
**Incremental re-indexing**:
- Keep a **document registry**: `doc_id, source_uri, version/etag/last_modified, content_hash, indexed_at, embedding_model, status`.
- Detect changes via **change feeds** (Graph delta queries for SharePoint, Blob change feed / Event Grid events, DB CDC) or periodic scans comparing last-modified/hash. Azure AI Search indexers track changes for supported sources with high-water marks.
- On change: re-parse and re-chunk the document, compute chunk content hashes, **upsert only changed chunks** (reuse embeddings for unchanged chunk hashes to save cost), delete chunks that no longer exist. Do it per document **atomically enough**: write new chunks with a new version, then switch/delete old ones, so queries never see a half-updated document (or accept a brief window).
**Deletions**: the hard part, because sources often don't tell you something was deleted. Use **soft-delete detection** (indexer deletion detection policies, tombstones in change feeds) or periodic **reconciliation** (list source IDs vs index IDs, delete orphans). Deletions matter for **compliance and permissions**: a deleted or access-revoked document must stop being retrievable quickly (also purge from caches/semantic caches).
**Permission changes** are updates too: ACL metadata on chunks must be re-synced when access changes, even if content didn't (Q28).
**Stale embeddings**: track `embedding_model` + version per vector; monitor index freshness (lag between source modification and indexing) as a metric with alerts.
**Switching embedding models**: vectors from different models are **not comparable** (different spaces, often different dimensions), so yes: **full re-embed** of the corpus. Do it like a blue/green deployment: build a **new index** (or a new vector column) with the new model in the background (throttled to respect rate limits; cost = total corpus tokens × price; usually affordable), keep incremental updates flowing to **both** indexes during the migration, run the **golden-set evaluation** to confirm the new model is better, switch reads (with a flag, possibly canary), then drop the old index. Queries must be embedded with the same model as the index they search.

### 28. Permissions in RAG: user A must not retrieve chunks from documents they can't see. How do you enforce that at the vector-search layer, not after?
Why not after: **post-filtering** (retrieve top-k, then drop forbidden chunks) leaks nothing to the user if done right, but it **destroys recall** (top 10 may all be forbidden → empty answer), still sends forbidden content into intermediate stages (rerankers, logs, caches), and is easy to get wrong. Enforce in the search itself:
1. **Store ACL metadata on every chunk** at ingestion: allowed group IDs / user IDs (`allowed_principals: ["grp-underwriting", "user-123"]`), tenant ID, classification level. Prefer **groups** to users (fewer updates).
2. **At query time, resolve the user's identity and group memberships** (from their token / Entra ID group claims / a cached directory lookup; handle large group counts via Graph lookup).
3. **Pre-filter in the vector search**: the filter is part of the ANN query: Azure AI Search **security filters** (`filter: allowed_groups/any(g: search.in(g, 'grp1,grp2'))`), pgvector `WHERE allowed_groups && $user_groups` (with iterative index scans or partitioning so filtered ANN keeps recall), Qdrant/Pinecone metadata filters. The search returns only permitted chunks. (Some services, e.g. Azure AI Search, now offer native document-level permission support for certain sources; know it exists.)
4. **Keep ACLs in sync**: permission changes in the source must update chunk metadata quickly (incremental sync of ACLs; Q27), and revoked access must take effect fast; track ACL sync lag as a metric.
5. **Defence in depth**: verify access again on the documents behind cited chunks before displaying (cheap check against the source or registry); never cache answers across users with different permissions (semantic cache keyed by permission scope); logs and traces containing chunk text need access control too.
6. **Test it**: automated tests with users of different permissions asserting forbidden documents never appear; include in the eval harness.
Hard parts: nested groups, very large group memberships, sources with complex inherited permissions (SharePoint), and sync latency.

### 29. Multi-tenant RAG: one index with a filter, or an index per tenant? Cost and isolation tradeoffs.
- **Shared index + tenant filter** (`tenant_id` on every chunk, mandatory filter on every query): cheapest and simplest to operate at many tenants (one schema, one pipeline, efficient resource use), easy cross-tenant improvements. Risks: **a missing filter = data leak** (enforce the filter in one data-access layer that can't be bypassed, plus tests); **noisy neighbours** (a large tenant affects latency); **filtered ANN recall** issues for small tenants inside a huge shared HNSW index (Part A Q19); per-tenant deletion/export is a filtered operation; per-tenant customisation (different embedding models, chunking) is harder.
- **Index per tenant** (or partition/namespace per tenant): **strong isolation** (physically separate, easy to prove to security-conscious clients/regulators), simple tenant deletion (drop the index: clean GDPR/offboarding), per-tenant tuning, per-tenant residency (place the index in the tenant's region), no cross-tenant recall effects. Costs: more indexes to manage (migrations, monitoring, re-indexing × N), service limits (e.g. max indexes per Azure AI Search service tier), wasted capacity for many small tenants, higher fixed cost.
- **Hybrid** (common answer): shared index for many small tenants, **dedicated indexes for large or regulated tenants** (and per-region services for residency). Middle options: Postgres **partitioning by tenant** (each partition with its own HNSW index: isolation-ish, and filtered queries hit a small index), Qdrant/Pinecone namespaces/collections per tenant.
For insurance clients with contractual isolation requirements, lean toward **index per tenant** (or per tenant group/region) and accept the operational cost, automated through IaC and one ingestion pipeline parameterised by tenant.

---

## C. AGENTS, TOOL CALLING & MCP

### 35. Walk me through the MCP server you built for the Pulse QA team - what tools did it expose, and how did you handle auth and blast radius?
**Your story** (essential: this is on your resume). Prepare: who used it (QA engineers, in which client: Claude Desktop/Code, VS Code, Copilot?), what problem it solved (e.g. "QA needed to create test quotes with specific inputs, look up rater versions, compare expected vs actual premiums, inspect policy documents without writing scripts or using the UI"), the list of tools, how it was deployed (local stdio vs remote HTTP), and how auth worked.
A strong structure for the answer:
- **Tools** (example shape; replace with real ones): `list_products`, `get_rater_version(product, jurisdiction)`, `create_test_quote(product, inputs)` (**test environment only**), `get_quote(quote_id)`, `compare_quote_outputs(quote_id, expected)`, `search_quotes(filters)`, `get_document(quote_id)`. Maybe **resources** for rater input schemas and **prompts** like "generate test cases for product X".
- **Auth**: if remote: OAuth (Entra ID) per user, so each call runs with the **user's identity and permissions**, not a shared super-user; if local stdio: the server uses the user's own credentials/token from the environment. Scopes per tool. Secrets never in the tool definitions or logs.
- **Blast radius**: pointed at **non-production environments only** (QA/staging) by configuration that can't be overridden by the model; read-only tools by default; mutating tools limited to test data (e.g. quotes created with a `test` flag/tenant), rate limits, input validation in the server, no generic "run SQL" tool, audit log of every call with user identity.
- **Results**: what it saved (time per test cycle, number of users), and what you'd improve.
If parts weren't there (e.g. auth was a shared API key), say so and explain how you'd harden it (Q36).

### 36. If an MCP tool can mutate production data, what guardrails do you build? (Expect: read-only defaults, scoping, confirmation, audit logging, sandboxing.)
Layers, from design to runtime:
1. **Don't expose it unless needed**: read-only tools by default; separate read and write tools (never a combined "execute anything" tool, never raw SQL/shell against prod); make write tools **narrow and task-specific** (`cancel_test_quote(quote_id)` rather than `update_record(table, fields)`).
2. **Identity and least privilege**: every call executes **as the end user** (OAuth with the user's token, delegated permissions), never with a privileged service account; scope tokens to the minimum (specific tenants/resources); the server enforces authorisation itself, never trusting the model's arguments.
3. **Human confirmation for mutations**: the client asks the user to approve the exact action with the exact parameters before executing ("Cancel quote Q-123 for Acme Ltd? [Approve/Reject]"). MCP clients support tool-approval flows, and elicitation lets the server ask for confirmation or missing input. High-risk actions may require a second approver or be blocked entirely from the agent channel.
4. **Validation and limits in the server**: strict input schemas, business-rule checks, **dry-run/preview mode** (show what would change), **bulk limits** (max records per call), rate limits, and preconditions (e.g. can only modify records in state X).
5. **Reversibility**: prefer soft deletes and versioned updates; make actions undoable; idempotency keys for retries.
6. **Sandboxing/environment separation**: default to staging/test data; production writes only via a separately configured, separately authorised server; network isolation.
7. **Audit logging**: every tool call with user, client, arguments, result, timestamp, and the conversation/trace ID: immutable logs, alerting on unusual patterns (many writes, off-hours).
8. **Prompt-injection awareness**: if the agent also reads untrusted content (emails, documents, web), it should not have write tools in the same session, or writes require human approval regardless.
9. **Kill switch**: disable a tool or the whole server instantly via config.

### 38. ReAct vs plan-and-execute vs a state-machine/graph workflow. Which did you use for the Cellular replacement agent and why?
- **ReAct** (Reason + Act loop): the model thinks, calls a tool, observes the result, thinks again, and so on until done. Flexible and adaptive, good for open-ended tasks with unpredictable paths (exploration, debugging). Downsides: can wander or loop, many LLM calls (cost/latency), hard to predict and test, harder to audit.
- **Plan-and-execute**: a planner LLM produces an explicit multi-step plan up front, executors carry out steps (possibly with cheaper models or plain code), and the planner re-plans when needed. More structured, the plan is inspectable/approvable, fewer expensive reasoning calls. Downsides: plans can be wrong when the environment surprises it; re-planning logic adds complexity.
- **State-machine / graph workflow** (e.g. LangGraph, or your own state machine): the developer defines the **steps and transitions explicitly**; LLM calls happen at specific nodes (classify, extract, generate code), with deterministic code in between and conditional edges (retry, human review). Most **predictable, testable, auditable**, and supports checkpoints and human approval nodes. Downside: less flexible; you must know the process.
For a **Cellular replacement** (workbook → executable rating logic), the right answer is a **graph/state-machine workflow** with LLM steps inside: e.g. parse workbook (code) → identify inputs/outputs (LLM + code validation) → for each formula block, translate to Python (LLM) → run the generated code against the workbook's cached values / Excel oracle (code) → if mismatches, feed the failing cells back to the LLM to fix (a bounded loop) → human review → publish. That's because the process is known, the outputs must be verifiable, and auditors need a reproducible path. Pure ReAct would be hard to make reliable and auditable.
**Your story:** say honestly which pattern your agent used. If it was a ReAct-style loop, explain why it was chosen (speed of building, flexibility with messy workbooks) and how you'd restructure it now.

### 42. How do you make an agent's behaviour reproducible for debugging? What do you log per step? (Expect: full trace of prompts, tool calls, args, outputs, token counts.)
Exact reproducibility of the LLM's choices isn't guaranteed (Part A Q5), so the goal is: **record everything needed to replay any step** and to understand why it did what it did.
**Per run (trace)**: run/trace ID, user/tenant, entry point and input, agent version (code commit), **prompt template versions**, model names and **exact versions**, parameters (temperature, max tokens, seed), tool definitions version, start/end time, total cost/tokens, final outcome (success/failure/escalated), and any human approvals.
**Per step (span)**:
- The **exact messages sent** (rendered system prompt, conversation history, retrieved context) or a reference to stored content, and the **raw model response** (text, tool calls, finish reason, refusal).
- **Tool calls**: tool name, arguments (as generated and after validation), execution result (or a reference if large), errors, duration, retries.
- Tokens in/out (cached tokens too), cost, latency (time to first token, total).
- Retrieval details where relevant (query, doc IDs, scores).
- State changes made by the step (workflow state before/after).
**Tooling**: OpenTelemetry spans with GenAI semantic conventions → Langfuse/LangSmith/Phoenix or your tracing backend; nested spans give a tree view of the run.
**Replay**: a debug tool that reloads a trace and **re-runs a single step** with the same inputs (same messages, same model version, temperature 0, seed) to see if the behaviour is stable, or with a modified prompt to test a fix; **tool results can be mocked from the recorded outputs** so replays don't hit real systems. Failed traces become eval cases.
**Governance**: traces contain user data → PII redaction policy, access control and retention limits (Q62).

### 43. Your Cellular replacement agent: how do you prove to an auditor that the premium it computed is correct and repeatable? If you can't, why did you ship it?
(See also Round 3 Q65 and Round 4 Q27.)
The honest, strong answer separates two architectures:
**If the agent computed premiums directly at runtime**, you **can't** fully prove repeatability: LLM outputs aren't deterministic across runs and model versions, and the arithmetic isn't verifiable step by step. The defensible position is then: "it wasn't the system of record for premiums" (e.g. used for internal testing/prototyping/QA comparison, with the authoritative premium from the deterministic rater), or "we mitigated it by...". If it *was* used for real premiums without those controls, admit it was a risk and explain how you'd fix it. Don't pretend.
**The provable architecture**: the agent **generates deterministic code** (or configuration/IR) from the workbook; that artifact is what computes premiums. Then proof is the same as for the transpiler:
1. **Correctness**: differential testing of the generated module vs Excel on a large test corpus (boundary values, all dropdown options, random inputs) with 100% match required on outputs (Round 3 Q62); actuarial sign-off on the test results; human code review of the generated code.
2. **Repeatability**: the approved artifact is **immutable and hashed**; each quote stores inputs, outputs, artifact version/hash, runtime version; re-running the artifact on the stored inputs reproduces the premium exactly, any time.
3. **Explainability**: a calculation trace (intermediate values mapped to workbook cells/business names) per quote.
4. **Change control**: every regenerated version goes through the same tests + approval; audit log of who approved.
5. **The LLM's role is recorded but not relied on**: prompts/model versions used during generation are logged for transparency, but the evidence for the auditor is the tested artifact, not the LLM.
"Why did you ship it?": answer with the real business reason (speed of onboarding new workbooks, coverage of workbooks the transpiler couldn't handle) **plus the controls** that made it acceptable, or with what you'd change.
**Your story:** this is a pass/fail-level question for you. Prepare it carefully and honestly.

### 45. How would you evaluate an agent, as opposed to a single LLM call? (Trajectory eval, tool-selection accuracy, end-task success rate.)
A single call has one input and one output; an agent has a **trajectory** (sequence of decisions and tool calls) and an **end state**. Evaluate at three levels:
1. **End-task success rate** (most important): did it achieve the goal? Define success checks per task, **verifiable by code where possible**: the generated rater matches Excel on the test set; the correct record was updated in a sandbox DB; the answer matches the reference. Run each task several times (non-determinism) and report the success rate (pass@1, and pass^k = succeeds in all k runs for reliability).
2. **Trajectory evaluation**: was the path reasonable? Metrics: **tool-selection accuracy** (right tool at each step vs a reference trajectory or an allowed set), **argument correctness**, number of steps vs optimal (efficiency), redundant/looping calls, **policy violations** (called a forbidden tool, skipped a required confirmation, accessed data out of scope), recovery from tool errors. Compare against reference trajectories where the path matters, or use an LLM judge with a rubric where multiple paths are valid.
3. **Step-level / component evals**: unit-test individual decisions: given this state, does it choose the right tool with the right arguments? (Fast, cheap, good for CI.)
Also measure **cost, latency, number of LLM calls** per task, and **safety** (red-team tasks: prompt injection in tool outputs, requests to do forbidden things).
**Environment**: a **sandbox** with mocked or test versions of the tools and a reset between runs, so tasks are repeatable; a benchmark set of 30–200 representative tasks (including hard and adversarial ones), growing from production failures. Run in CI on prompt/model/tool changes; compare against the baseline.

### 46. What is human-in-the-loop approval design, and where did you need it?
HITL = designing **explicit points where a human reviews, corrects, or approves** before the system proceeds, chosen based on **risk and confidence**.
Design elements:
- **Where**: before **irreversible or high-impact actions** (sending external emails, writing to production systems, binding a policy, payments, deleting data), when **confidence is low** (extraction fields below threshold), for **regulated decisions** (pricing, underwriting, hiring: human makes the decision, AI assists), and for **new/unfamiliar inputs** (drift).
- **What the human sees**: the proposed action with its exact parameters, the evidence/sources (highlighted document regions, citations), the model's confidence and reasons, and a diff of what will change. Easy approve/edit/reject; keyboard-friendly for volume.
- **Mechanics**: the workflow **pauses durably** (state saved, e.g. a workflow engine or LangGraph checkpoint) and resumes on approval; timeouts and escalation if nobody responds; SLAs on review queues; who can approve what (permissions, maker-checker for high value).
- **Learning**: every approval/correction is logged as labelled data (eval set, threshold tuning, fine-tuning; Q67, Q78), and approval rates per action type inform where automation can safely increase.
- **Avoid rubber-stamping**: if humans approve 99.9% without reading, the control is fake. Use sampling, show only what matters, measure review time, and occasionally insert known-bad cases (like gold tasks) to check attention.
**Your story:** natural places in your work: Orbit/Ayana extraction (low-confidence fields reviewed by operations/underwriters before creating new business), the Cellular agent (generated code reviewed and approved before publishing), the MCP server (approval before mutating tools), RLHF (humans *are* the loop).

---

## D. AI IN PRODUCTION - THE BACKEND/DEVOPS SIDE

### 47. Design the serving architecture for an LLM feature: streaming, timeouts, retries, rate limits from the provider, fallback models, and cost caps. What's the p95?
**Architecture**: client → API (FastAPI, async) → **LLM gateway layer** (an internal module or service, or LiteLLM / Azure API Management AI gateway / Portkey) → providers/deployments. The gateway centralises everything below so features don't each reimplement it.
- **Streaming**: SSE from the API to the client (Part A Q49); the gateway streams from the provider and forwards chunks; on client disconnect, cancel the upstream call.
- **Timeouts**: separate **time-to-first-token timeout** (e.g. 10–15s: if no first token, the request is stuck) and **total/idle timeouts** (e.g. no new token for 20s); an overall request deadline that propagates from the caller.
- **Retries**: only on retryable errors (429, 5xx, connection errors, first-token timeout), **exponential backoff + jitter**, honour `Retry-After`, max 1–2 retries, and **never retry after tokens have already streamed to the user** (switch to fallback or fail cleanly instead). Retry budget to avoid storms.
- **Provider rate limits**: client-side **token-aware rate limiting** (track TPM/RPM per deployment and queue/shape requests before sending); spread load across **multiple deployments/regions/keys** (load balancing with health checks); priority queues (interactive > batch); details in Q48.
- **Fallback models**: an ordered fallback chain per feature (primary model → same model in another region/deployment → a different provider/model that passed the feature's eval suite → a degraded response like "try again" or a non-LLM fallback). Circuit breaker per provider so a failing one is skipped quickly. Only fall back to models **validated by evals** for that feature.
- **Cost caps**: estimate tokens before sending (prompt tokens counted, `max_tokens` capped per feature), **budgets per tenant/user/feature per day** enforced in the gateway (soft alert at 80%, hard stop or downgrade to a cheaper model at 100%), per-request max cost, anomaly alerts. Log tokens and cost on every call (Q52).
- **Plus**: prompt caching (stable prefixes), response caching where safe, guardrails before/after (Q63), tracing (Q58).
**What's the p95?** Depends on input/output size and model, so compute it rather than guess: latency ≈ queueing + **TTFT** (time to first token: ~0.3–1s for fast models with small prompts, several seconds for long prompts or reasoning models) + **output tokens ÷ generation speed** (e.g. 50–100 tokens/s for typical hosted models). Example: a RAG answer with ~4k input tokens and ~300 output tokens on a mid-size model: TTFT ~0.6–1.5s, generation 3–6s, plus retrieval/rerank ~0.3s → **p50 ≈ 3–5s, p95 ≈ 7–12s** total, but **perceived latency is TTFT** thanks to streaming, so the SLO should be on **p95 TTFT (e.g. < 2s)** plus a cap on total time. Measure with real traffic; p95 is dominated by long outputs, provider queueing at peak, and retries.

### 48. Provider rate-limits you at peak (429s with a TPM limit). Every mitigation you know, in order.
Ordered roughly from immediate/cheap to structural:
1. **Respect the 429 correctly**: honour `Retry-After`, exponential backoff with jitter, limited retries, so you don't make it worse (retry storms).
2. **Reduce tokens per request**: trim prompts (redundant instructions, too many few-shot examples, too many retrieved chunks → rerank and send fewer), cap `max_tokens` to what the feature needs, shorter outputs. TPM limits often count `max_tokens` as reserved, so lowering an oversized `max_tokens` frees capacity immediately.
3. **Prompt caching** (doesn't always reduce TPM accounting but cuts cost/latency) and **response caching** for repeated requests (exact or carefully scoped semantic caching).
4. **Client-side rate limiting and queuing**: a token-aware limiter in the gateway that keeps you just under the limit and **queues** excess requests instead of firing them and getting 429s; **prioritise** interactive traffic over background jobs; shed or defer low-priority work.
5. **Move non-interactive work off-peak / to batch APIs** (separate, larger quotas and ~50% cheaper): ingestion, re-processing, evals, summaries that aren't needed immediately.
6. **Spread load across more capacity**: multiple deployments, regions or subscriptions/keys (e.g. several Azure OpenAI deployments behind a load balancer: within policy and data-residency limits); request **quota increases** from the provider.
7. **Model routing**: send easy requests to a smaller/faster model (different, often higher limits); use the big model only where needed.
8. **Provisioned/reserved throughput** (Azure OpenAI PTUs, provisioned throughput on other platforms) for predictable baseline load, with pay-as-you-go spillover for peaks.
9. **Fallback provider/model** validated by evals for when limits are exhausted.
10. **Product-level**: graceful degradation (shorter answers, disabling non-essential AI features at peak), and self-hosting for steady high-volume workloads where it pays off (Q53).
Monitor: 429 rate, queue wait time, TPM usage vs limit per deployment, and alert before hitting the ceiling.

### 50. How do you handle a 40-second LLM call in an HTTP API? Compare streaming, async job + polling, and webhooks.
- **Streaming (SSE/WebSockets)**: keep the connection open and send tokens/progress as they're produced. **Best UX for interactive features** (chat, answers a user is waiting for): perceived latency is the time to first token. Costs: long-lived connections through proxies/load balancers (timeouts, buffering: Part A Q49), connection capacity on servers, work lost if the connection drops (unless you persist the result server-side), and retries are awkward mid-stream.
- **Async job + polling**: `POST` returns `202` + job ID; a worker runs the LLM call; the client polls `GET /jobs/{id}` (or the UI shows "processing"). **Most robust**: survives disconnects, deploys and retries, easy to scale workers on queue depth, natural for batch and long agent runs (minutes). Costs: polling latency/overhead, more infrastructure (queue, job store), no token-by-token UX (unless combined with streaming of progress).
- **Webhooks**: client registers a callback URL; you POST the result when done. **Best for server-to-server integrations** (a partner system submits documents for extraction). Costs: the client needs a public endpoint; you need signing, retries, idempotent delivery, a DLQ (Round 3 Q30).
**Recommendation**: interactive user-facing → **streaming**, backed by persisting the result (so a reconnect can fetch it); long or background work (document extraction, multi-step agents, anything > ~60s or that must survive restarts) → **async job**, with polling for UIs (optionally SSE for progress events) and webhooks for integrations. A 40-second call specifically: stream it if a user is watching and the output is text; otherwise make it a job.

### 52. How do you control and attribute LLM cost per tenant/feature? What do you track?
**Attribution**: every LLM call goes through the gateway with **metadata tags**: tenant ID, user ID, feature/use-case, prompt version, model, environment, request/trace ID. Log per call: **input tokens, cached input tokens, output tokens, reasoning tokens** (if any), model, unit prices at that time → **computed cost**; plus embedding calls (ingestion and queries), reranker calls, vector DB/search costs, and OCR/Document Intelligence pages (often a big part of document-AI cost). Aggregate into a cost table / dashboard (by tenant, feature, model, day). Reconcile monthly against the provider invoice (they won't match exactly; investigate big gaps). Cloud-level tags help for provisioned resources (separate deployments per feature where useful).
**What to track**: cost per **unit of value**, not just totals: cost per document processed, per answered question, per conversation, per active user, per tenant vs revenue from that tenant; tokens per request (input/output) trends; cache hit rates; model mix (% of calls by model); retry/failure overhead (tokens spent on failed or discarded calls); cost of agent runs by number of steps.
**Control**:
- **Budgets and quotas** per tenant/feature/user (daily/monthly), enforced in the gateway: alerts at thresholds, then throttling, model downgrade, or hard stop by plan tier.
- **Per-request caps**: `max_tokens`, max agent steps, max retrieved context.
- **Anomaly detection**: a tenant's spend jumping 5× day-over-day pages someone (a runaway loop or abuse).
- **Optimisation levers** (Part A Q96): model routing, caching, prompt trimming, batch APIs for offline work, not calling the LLM where code works.
- **Pricing feedback**: per-tenant cost visibility feeds product pricing (AI usage tiers).

### 53. Self-hosted (Ollama/vLLM) vs API providers (Azure OpenAI, Groq): give me the real decision framework - cost curve, latency, data residency, ops burden.
- **Cost curve**: APIs are **pay-per-token**: zero fixed cost, linear growth, cheap at low/spiky volume. Self-hosting is a **fixed cost** (GPUs running 24/7 whether used or not; e.g. one or several GPUs at cloud prices of several thousand dollars per month each, plus engineers' time) with near-zero marginal cost per token. **Break-even** comes only with **high, steady utilisation** (GPUs kept busy most of the day) and a model size you can serve efficiently. Below that, APIs are cheaper, and providers' prices keep dropping. Do the math with your real token volume.
- **Quality**: the best frontier models are API-only; open models (Llama, Mistral, Qwen, etc.) are very good for many tasks (extraction, classification, RAG answers) especially after fine-tuning, but evaluate on your task.
- **Latency**: APIs: variable, shared infrastructure, queueing at peak, network hop; specialised providers (Groq, Cerebras) are extremely fast. Self-hosted: predictable, no rate limits beyond your hardware, can be co-located with your app; but achieving high throughput needs vLLM-class serving and tuning, and capacity planning for peaks.
- **Data residency & privacy**: self-hosting keeps data **entirely in your network/region**, with no third-party processing, which matters for strict clients or regulators. But enterprise APIs often satisfy requirements: **Azure OpenAI** in specific regions with data-processing terms (no training on your data, regional/data-zone deployments) is usually acceptable for insurance in the EU/UK/US. Groq and other external providers need a DPA review and may not meet residency.
- **Ops burden**: self-hosting means GPU provisioning and quotas (GPUs are scarce), drivers, serving stack upgrades, model updates, autoscaling (slow: large model loads), monitoring, security patching, on-call. APIs: none of that, but provider dependency (deprecations, outages, silent updates).
- **Control & customisation**: self-hosting allows fine-tuned/custom models, pinned versions forever, custom decoding (grammars). APIs offer fine-tuning on some models but less control.
**Decision**: start with **APIs** (fast to market, best quality); self-host when you have (a) a steady high-volume workload where an open model meets the quality bar, (b) a strict residency/privacy requirement APIs can't satisfy, or (c) a need for a custom/fine-tuned model or full version control. **Ollama** is for local development/prototyping and small internal use; **vLLM** (or TGI/SGLang, or managed endpoints) for production self-hosting.
**Your story:** you used Ollama (local), Azure OpenAI and Groq. Say what drove each choice.

### 57. How do you A/B test a prompt or model change in production safely?
1. **Offline first**: the change must pass the eval suite (golden set: quality, format validity, safety, cost, latency) before it gets any traffic (Q61).
2. **Shadow mode** (no user impact): run the new variant in parallel on a sample of real traffic, **don't show its output**; compare with the current variant using automatic metrics (validation failures, length, refusals, LLM-judge pairwise preference calibrated to humans, agreement with current outputs for extraction tasks). Costs 2× on sampled traffic.
3. **Canary / A/B**: assign by a stable unit (user/tenant/conversation, via hashing) so a user doesn't flip between variants; start at 1–5%; tag every call with the variant and prompt/model version.
4. **Metrics**: primary success metric chosen upfront (task success, thumbs-up rate, acceptance rate of extracted fields without edits, resolution rate, conversion) plus **guardrails** (error/validation rate, latency p95, cost per request, safety triggers, escalation/complaint rate). Note that LLM features often have weak signals, so you need enough volume and time; use implicit signals (edits, retries) to increase sensitivity.
5. **Automatic rollback** if guardrails breach; ramp up gradually (5 → 25 → 50 → 100%).
6. **Analysis**: statistical significance with pre-defined sample sizes (don't peek and stop early), segment analysis (tenants, document types: a change can help on average and hurt one segment badly), and review a sample of outputs qualitatively.
7. **Rollback path**: the old prompt/model version stays deployable instantly via config (Part A Q56).
For high-stakes outputs (insurance decisions, extraction feeding pricing), stay longer in shadow mode and add human review of samples before exposure.

### 58. What does observability look like for an LLM system? (Traces, token counts, cost, latency per step, retrieval hits, user feedback signals. LangSmith/Langfuse/OTel GenAI semconv?)
**Traces**: one trace per user request with nested spans for each step: API → query rewrite (LLM) → retrieval (search) → rerank → generation (LLM) → tool calls → post-validation. For agents, the full tree of steps (Q42). Capture prompts/responses (with redaction), model and version, parameters, prompt version.
**Metrics** (dashboards and alerts):
- **Latency**: TTFT and total per LLM call and per pipeline step; end-to-end p50/p95.
- **Tokens and cost**: input/cached/output tokens per call, cost by feature/tenant/model (Q52).
- **Reliability**: provider errors, 429s, timeouts, retries, fallback activations, schema validation failures, tool-call errors, agent step counts and loop detections.
- **Retrieval**: number of results, top scores, % of queries with no result above threshold, reranker score distribution, citation counts.
- **Quality proxies**: refusal / "I don't know" rate, groundedness scores from sampled online evaluation (LLM judge on a % of traffic), guardrail triggers, output length distribution.
- **User signals**: thumbs up/down with reasons, edits/acceptance, re-asks, escalations (Part A Q80).
**Tooling**: **OpenTelemetry** instrumentation with the **GenAI semantic conventions** (standard span attributes like `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, operation names) so traces flow into your existing backend (Tempo/Jaeger/App Insights/Datadog); LLM-specific platforms such as **Langfuse** (open source, self-hostable: good for data residency), **LangSmith**, **Arize Phoenix**, or Datadog LLM Observability add prompt management, eval runs on traces, and annotation queues for human review.
**Governance**: prompts and outputs contain customer data → redact PII before logging or restrict access, set retention limits, and log sampling for high-volume features (Q62).

### 61. How do you build a regression test suite for LLM behaviour in CI? What's the pass/fail criterion when outputs are non-deterministic?
**Suite structure** (per feature):
1. **Deterministic checks** (fast, cheap, run on every PR): output parses and matches the schema; required fields present; values in allowed enums/ranges; citations reference provided chunks; refusal on known unanswerable inputs; prompt-injection test cases don't trigger forbidden behaviour; token count of the rendered prompt within budget; and plain unit tests of all the non-LLM code (prompt rendering, parsing, validation) with **mocked LLM responses**.
2. **Golden-set evals** (on PRs touching prompts/models/retrieval, or nightly): the labelled dataset (50–500 cases), scored with **task-appropriate metrics**: exact match / field-level accuracy for extraction and classification; recall@k for retrieval; faithfulness/correctness via calibrated LLM judges for free text; tool-selection accuracy for agents.
3. **Regression cases** from production failures (each fixed bug becomes a test: Q78).
**Pass/fail with non-determinism**:
- Use **temperature 0 / seeds** where possible to reduce variance, but don't rely on exact string equality for free text.
- **Aggregate thresholds instead of per-case exactness**: e.g. "field accuracy ≥ 95% overall and ≥ 90% on every field", "faithfulness ≥ 0.9", "no regression > 2 percentage points vs main's baseline on any metric".
- **Critical cases are hard gates**: a small set that must pass 100% (e.g. never invent a sum insured; never answer from a forbidden document; refusal on injection).
- **Repeat runs** for flaky cases (run 3–5 times, require a pass rate) and track variance; report confidence intervals for small sets so you don't chase noise.
- **Compare against the baseline** (current main's scores stored as an artifact) and show the delta in the PR, including cost and latency changes.
**Practicalities**: cache LLM responses keyed on (prompt, model, params) to make reruns cheap where appropriate; run expensive suites nightly and a smoke subset per PR; tools like promptfoo, DeepEval, pytest-based harnesses, or Langfuse/LangSmith datasets; pin the **judge model** version too.

### 62. PII and data governance: what leaves your network, what gets logged, what gets redacted, and how does that interact with SOC2 and insurance regulation?
**What leaves your network**:
- Decide per data class: e.g. submission documents with personal data may go to **Azure OpenAI in the same region/data zone under the enterprise agreement** (no training on data, no human review/abuse monitoring retention where exemptions are approved, data processed in-region), but **not** to consumer-grade or non-contracted providers. Maintain an approved-provider list with DPAs, regions, retention terms; route by data classification in the gateway.
- **Minimise**: send only what the task needs (the relevant pages/fields, not whole case files); pseudonymise identifiers where the task doesn't need them (replace names/policy numbers with tokens and re-insert after).
**What gets logged**: traces are invaluable for debugging but are a **copy of customer data**: log metadata always (tokens, latency, model, IDs, scores); log full prompts/outputs **only** with redaction, in-region storage, restricted access (role-based, audited), and **short retention** (e.g. 30 days, longer only for sampled, approved eval data). Never log secrets, full card/bank details, health data unnecessarily.
**What gets redacted**: PII detection (Microsoft Presidio, Azure AI Language PII detection, regex for structured IDs) before logging and, where possible, before sending to providers: names, addresses, emails, phone numbers, national IDs, bank details, dates of birth, health information. Note the trade-off: redaction before the LLM can hurt extraction tasks that *need* the PII (e.g. extracting the insured's name), so for those, rely on the contractual/regional controls instead and redact in logs only.
**SOC2**: requires documented and evidenced controls: access control to logs/prompt stores, vendor risk management (LLM providers as subprocessors, with their SOC2 reports), data retention and deletion policies actually enforced, change management for prompts/models, monitoring and incident response for AI features (Round 4 Q41).
**Insurance regulation & privacy law**: **GDPR / UK GDPR** (lawful basis, data minimisation, purpose limitation, DPIAs for new AI processing, data subject rights incl. deletion: traces and eval sets must be deletable/traceable, cross-border transfer rules), sector rules on **automated decision-making** (decisions with legal/significant effects need human involvement and explainability: underwriting/pricing/claims), regulators' expectations on model risk management and fairness (e.g. FCA Consumer Duty in the UK, state insurance regulations/NAIC model bulletin on AI in the US, and the **EU AI Act**, which classifies some insurance uses, like life/health risk assessment and pricing, as high-risk), record-keeping obligations, and client contracts (many insurers forbid sending their data to certain providers or regions).

### 63. Guardrails: input filtering, output validation, jailbreak detection, toxicity. What did you actually implement vs what do you know exists?
**Input side**:
- **Validation and limits**: max length/tokens, allowed file types, rate limits per user.
- **Prompt-injection / jailbreak detection**: classifiers like Azure AI Content Safety **Prompt Shields** (user prompt attacks and document/indirect attacks), Llama Guard / Prompt Guard models, Lakera-style services, heuristics; plus **structural defences** (delimit untrusted content, least-privilege tools, no tools when processing untrusted content: Part A Q9). Detection is probabilistic, so the structural defences matter more.
- **Content moderation** on user input (hate, violence, sexual, self-harm categories) where the product is user-facing: Azure AI Content Safety, OpenAI moderation, Llama Guard.
- **PII detection** where policy requires (Q62).
- **Topic/scope filtering**: refuse out-of-scope requests (a policy assistant shouldn't write marketing poems), via a classifier or system prompt rules.
**Output side**:
- **Schema validation** (Pydantic) and **business-rule validation** (values in range, consistency) for structured outputs: the most valuable guardrail in extraction systems.
- **Groundedness checks** for RAG (claims supported by context; Azure AI Content Safety has groundedness detection; or an NLI/LLM judge).
- **Content safety** on outputs (toxicity), **PII leakage** checks (the model shouldn't output other customers' data), **secret/system prompt leakage** checks, citation validation.
- **Action guardrails** for agents: allow-lists of tools, argument validation, approval for risky actions, budgets (Q64).
Frameworks: NVIDIA NeMo Guardrails, Guardrails AI, Llama Guard, Azure AI Content Safety (built into Azure OpenAI content filters).
**Measure guardrails**: false positive rate (blocking legitimate requests annoys users) and false negative rate on a red-team test set; log triggers.
**Your story:** be precise about what you implemented (e.g. "Azure OpenAI's default content filters were on; I added Pydantic schema validation and business-rule checks on extracted fields and a strict 'answer only from context' prompt; I did not deploy a dedicated jailbreak classifier"). The interviewer explicitly asks "what did you actually implement vs what do you know exists", so honesty is being tested.

### 64. How do you handle the "agent did something expensive/destructive" scenario - budget limits, kill switches, and blast radius?
**Prevention (before it happens)**:
- **Blast radius by design**: least-privilege credentials per agent (scoped to specific resources/tenants), read-only by default, **no destructive tools** unless essential, separate environments (agents default to sandbox/staging), bulk operation limits, soft deletes/versioning so mutations are reversible, idempotency keys.
- **Human approval** for irreversible or high-cost actions (Q36, Q46).
- **Budget limits** enforced by the orchestrator: max steps, max tokens/cost per run, per user/tenant per day, max wall-clock time; **spend rate alerts** (cost per minute) and hard stops.
- **Rate limits on tools** (e.g. max 10 emails per run, max N writes per minute) and anomaly detection on tool usage.
**Kill switches**: a global flag to disable an agent/feature instantly; per-tool disable flags; ability to **cancel in-flight runs** (the orchestrator checks a cancellation flag between steps and cancels running tool calls); revoke the agent's credentials as a last resort. Test that the kill switch works (game day).
**Response (when it happens)**: treat it as an incident (Round 4 Part A Q39): stop the agent (kill switch), contain (revoke credentials, stop downstream effects like queued emails), assess impact from the **audit trail of tool calls** (Q42: exactly what it did, with which arguments), remediate (roll back changes using versioning/soft deletes, reverse transactions, notify affected parties), and do a blameless postmortem focusing on **which guardrail was missing** (approval, limit, scope) rather than "the model misbehaved". Add the scenario to the agent's red-team eval set.

---

## E. DOCUMENT AI / EXTRACTION

### 65. Design an information-extraction pipeline for insurance submission emails: attachments, scanned faxes, tables, handwriting. Where do OCR, layout models, and LLMs each fit?
(System-level intake design is in Round 4 Q24 and Round 3 Q66; this answer focuses on the AI layers.)
**Pipeline**:
1. **Pre-processing (code)**: parse the email (body, headers, thread), **strip quoted replies and signatures**, extract attachments recursively (nested .msg/.eml, zips), detect file types, convert Office files to text/PDF, de-duplicate attachments by hash, split multi-document PDFs if needed.
2. **Classification**: document type per attachment (ACORD application, schedule of values, loss run, broker cover letter, prior policy, photo) with a cheap classifier or a small/fast LLM on the first page(s). Determines which extraction path to use.
3. **OCR (text from pixels)**: only where there's no reliable text layer: scanned PDFs, faxes, images, photos of documents. Azure Document Intelligence **Read** model (or Tesseract/PaddleOCR locally). Image pre-processing (deskew, denoise, contrast) helps faxes a lot. **Handwriting**: modern OCR handles neat handwriting reasonably, but confidence is lower; route low-confidence handwritten fields to human review.
4. **Layout models (structure)**: Azure Document Intelligence **Layout** / prebuilt or **custom models**: detect paragraphs, headings, **tables** (rows/columns/merged cells), key-value pairs, checkboxes/selection marks, with **bounding boxes and confidence**. For fixed forms (ACORD), a **custom template/neural extraction model** trained on a few dozen labelled examples extracts fields precisely and cheaply. Spreadsheets (SOVs) are parsed directly with code (pandas/openpyxl) and normalised column-by-column (LLM can map messy headers to the canonical schema).
5. **LLMs (understanding and normalisation)**: for **unstructured and variable content**: cover letters and email bodies ("client wants cover from 1st of next month, TIV about £12m across 3 sites"), mapping varied table headers to the schema, resolving which entity is the insured vs the broker, reconciling information across documents, summarising loss history. Input = layout output as **Markdown with tables preserved** (not flat text), plus page references. Output = **structured output** with per-field value, source page/snippet, and null when absent.
6. **Post-processing (code)**: normalise (dates, currencies, amounts, addresses → geocoding, NAICS codes), **validation rules** (totals, ranges, consistency across documents), confidence calculation per field (Q66 in Part A), dedupe/matching against existing submissions.
7. **Human review** for low-confidence or high-risk fields (Q67), corrections feeding evaluation and improvement (Round 4 Q25).
**Division of labour in one line**: **OCR turns pixels into text; layout models turn text into structure (tables, key-values, positions); LLMs turn structure into meaning (which value is which field, across messy, variable documents); code validates and normalises everything.** Using an LLM for what a layout model or code does reliably is wasted cost and accuracy.

### 67. How do you decide the threshold at which a document goes to a human reviewer? How do you tune it against business cost?
1. **Get calibrated confidence per field** (Part A Q66), so the score means a probability of being correct.
2. **Collect labelled data**: reviewed outputs (including a **random sample of auto-accepted** ones so you see errors in high-confidence items too).
3. **Plot, per field, accuracy vs confidence threshold and the automation rate** (% of items above threshold): for each candidate threshold you get "X% straight-through, with error rate Y% among auto-accepted".
4. **Put money on both sides**:
   - Cost of a **human review** (e.g. reviewer time ~1–3 minutes per document × loaded cost, plus SLA delay).
   - Cost of an **undetected error** for that field (wrong sum insured → mispriced risk or a rejected quote later; wrong effective date → coverage gap / E&O claim; wrong broker email → minor). This differs **per field**: critical fields get much stricter thresholds.
   - Choose the threshold that **minimises expected total cost**: `review_rate × review_cost + auto_rate × error_rate_auto × error_cost`, subject to constraints (SLA capacity of the review team, regulatory requirements that some fields always get human confirmation).
5. **Route at the field level** where possible (review only the uncertain fields), and use **document-level rules** too (any critical field below threshold → review; new broker/template → review; validation rule failures → review regardless of confidence).
6. **Revisit continuously**: thresholds drift as models, document mix and reviewer capacity change; monitor the error rate of auto-accepted items via ongoing random sampling, and adjust. Start conservative (more review) and loosen as evidence accumulates.

### 68. How do you measure extraction accuracy per field, and how do you catch degradation on a new document format you've never seen?
**Measuring per field**:
- **Ground truth**: human-labelled or human-corrected values (review UI corrections + a dedicated labelled evaluation set covering document types, brokers and quality levels).
- **Per-field metrics** with field-appropriate comparison: exact match after normalisation for IDs/dates/enums; numeric tolerance for amounts (or exact to the unit for money); fuzzy/semantic match for names/addresses (normalised, or token-level F1); list fields (e.g. locations in an SOV) with precision/recall/F1 over items.
- Distinguish error types: **wrong value**, **missed value** (null when present), **hallucinated value** (value when absent: often the most dangerous), and wrong field mapping.
- Report per field × document type × source (broker/template) × model/prompt version; track **straight-through rate** and **human correction rate** in production as continuous proxies.
**Catching degradation on new/unseen formats**:
- **Detect novelty**: a template/layout fingerprint (layout model's structure, first-page embedding, sender/broker + document type combination); flag documents whose fingerprint or embedding is far from anything in the eval set or recent history; alert on spikes of "unknown template".
- **Watch proxy signals per segment** (no labels needed): confidence distributions, schema/validation failure rates, null rates per field, value distributions, and **correction rates** in review, segmented by broker and template, because a degradation on one new template is invisible in global averages.
- **Route new formats to human review by default** until enough samples are verified; then add labelled examples of the new format to the eval set (and to few-shot examples/custom model training).
- **Periodic random sampling** of auto-processed documents for audit (catches silent errors that confidence didn't flag).

### 69. Tables in PDFs are notoriously hard. What did you actually use, and what still fails?
**Tools landscape** (so you can talk about trade-offs):
- **Text-layer PDFs**: `pdfplumber` / PyMuPDF (positions of words, lines), **Camelot** (lattice mode for ruled tables, stream mode for whitespace-separated) and **Tabula**: good on clean, digital, consistently formatted tables.
- **Layout models**: **Azure Document Intelligence Layout** (tables with rows/columns/spans, works on scans, outputs Markdown), AWS Textract tables, Google Document AI; open-source table-transformer models, **Docling**, Unstructured, Marker. Much more robust across formats and scans.
- **Vision LLMs**: send the page image to a multimodal model and ask for the table as Markdown/JSON; handles messy layouts well, but can **silently hallucinate or shift cells** and is expensive at volume, so validate.
- **Spreadsheets** (SOVs) as native Excel: parse directly, don't OCR.
**What still fails** (be ready to name these):
- Tables **spanning pages** (header only on the first page, rows split across pages, repeated headers mistaken for data).
- **Merged cells / multi-level headers** (e.g. "Building | Contents | BI" under "Sum Insured"), nested tables.
- **Borderless tables** with irregular alignment; wrapped text in cells merging with the next row.
- Low-quality **scans/faxes** (skew, noise), handwriting in tables, rotated pages.
- **Numbers**: thousands separators vs decimals (1.234,56 vs 1,234.56), units in headers ("£000s"), totals rows mistaken for data rows, footnote markers attached to numbers.
- Tables rendered as images inside PDFs, or charts.
**Mitigations**: layout model → table as Markdown/JSON → **LLM maps columns to the schema** → **code validates** (column totals match the stated total, row counts, data types per column, plausible ranges) → mismatches go to human review; stitch multi-page tables by comparing column structures; keep page/cell coordinates to show reviewers the source.
**Your story:** say what you used in Orbit/Ayana (likely Azure Document Intelligence / indexers) and one table case that still failed.

### 70. How do you handle a 200-page document where the answer needs 3 pages from different sections?
Options, often combined:
1. **Good retrieval within the document**: structure-aware chunking with section paths (Q15/Q16), hybrid search + reranking restricted to that document, **top-k large enough** (e.g. 8–15 chunks) so all 3 pieces can make it in; **query decomposition**: split the question into sub-questions ("what's the limit?", "what's the deductible?", "is flood excluded?"), retrieve for each, then combine.
2. **Structure-guided retrieval**: use the document's table of contents/section map: first ask the model (or rules) which sections are relevant ("Definitions", "Section 4 Exclusions", "Endorsement 3"), then load those sections fully. Plus automatic expansion: include **definitions** of terms used in retrieved clauses and **cross-referenced sections** (Q16).
3. **Long context**: 200 pages ≈ 100–150k tokens, which fits in many modern context windows. For high-value, low-volume questions, sending the whole document (with **prompt caching** if multiple questions are asked about the same document) can be simplest and most accurate. Trade-offs: cost per question, latency, lost-in-the-middle effects (mitigate by asking the model to first quote the relevant passages, then answer).
4. **Iterative/agentic retrieval**: the model searches, reads, notices it needs the definition of "Flood", searches again: a bounded loop with a small step budget.
5. **Map-reduce** for extraction across the whole document (e.g. "list all exclusions"): process sections in parallel, extract relevant facts per section, then reduce/merge.
6. **Pre-extraction**: for questions asked repeatedly (limits, deductibles, key dates), **extract structured fields once at ingestion** and answer from the structured data; no retrieval needed at query time.
Whichever you choose: require **citations to each page used**, and evaluate on multi-section questions specifically (they're the ones that fail).

### 71. Resume-to-JD matching (Jio ATS): embeddings alone will rank badly. What actually works, and how do you make ranking explainable to a recruiter?
**Why embeddings alone rank badly**: they capture topic similarity, not **fit**. A junior and a senior Python resume embed close together; they ignore **hard requirements** (years of experience, location, work authorisation, mandatory certifications); keyword-stuffed resumes look similar; negation and recency are lost ("used Java 10 years ago"); a long resume's embedding averages everything; and domain-specific skill relationships are fuzzy.
**What works: a multi-stage pipeline**:
1. **Structured extraction** from resumes and JDs (Round 4 Q13): skills (normalised to a taxonomy with synonyms and hierarchy: "PySpark" → Spark, Python), titles normalised to standard roles and seniority, experience per skill with **recency and duration**, education, certifications, location, notice period.
2. **Hard filters** from the JD's must-haves (location/relocation, authorisation, minimum years, mandatory certifications) applied as filters, not similarity.
3. **Candidate retrieval**: hybrid: skill/keyword matching (BM25 on normalised skills) + embeddings (of the experience summary/sections) to get top ~200.
4. **Ranking with features**: a scoring model combining interpretable features: required-skill coverage (% of must-have skills present, weighted by recency/years), nice-to-have coverage, years of relevant experience vs required, title/seniority match, domain/industry match, education match, semantic similarity score as **one feature among many**. Start with a **weighted scoring formula** agreed with recruiters; move to a learning-to-rank model (e.g. LightGBM LambdaMART) trained on **recruiter decisions** (shortlisted/interviewed/hired) once enough data exists. Optionally an LLM/cross-encoder re-scores the top 20–50 against the JD with a rubric.
5. **Feedback loop**: recruiter actions (shortlist/reject with reasons) become training and evaluation data; measure NDCG/precision@k against recruiter shortlists.
**Explainability for recruiters**: show **why** in their language: "Matches 7 of 9 required skills (missing: Kubernetes, Terraform)", "6 years of backend experience (required: 5+)", "Last used Python: current role", "Seniority: Senior (JD: Senior)", with **evidence snippets** highlighted from the resume. Feature contributions from the ranker (SHAP) map directly to these reasons. Let recruiters **adjust weights or toggle requirements** and see the ranking change: that builds trust and catches bad JD parsing. Never present a bare similarity score as "fit".
**Your story:** explain what the real Jio ATS did (embeddings? rules? DS models?) and where your backend fit; defend the 100k resumes/day scale.

### 72. How do you deal with bias and fairness in an automated candidate-shortlisting system? What would you refuse to build?
**Sources of bias**: historical hiring decisions used as training labels (they encode past bias), **proxy features** for protected attributes (names → gender/ethnicity, graduation year → age, address/postcode → ethnicity/socio-economic status, gaps in employment → parental leave/disability, specific universities/clubs), embedding models that carry societal associations, and unequal parsing quality (non-standard resume formats, non-native English, non-Western name and education formats).
**Measures**:
- **Exclude protected attributes and obvious proxies** from features and from what the model/LLM sees (strip names, photos, age/DOB, gender, marital status, addresses beyond the required location check); but recognise that removing them isn't enough because of correlated proxies.
- **Bias audits**: measure selection rates by group (where demographic data is available under proper governance) and check for **adverse impact** (e.g. the four-fifths rule: a group's selection rate below 80% of the highest group's is a red flag); test with counterfactual resumes (same resume, changed name/gender signals → should get the same score).
- **Human decision-making**: the system **ranks and explains, humans decide**; no automatic rejection based solely on the model; clear appeal/review processes. (This is also a legal requirement in many places: GDPR Article 22 on solely automated decisions, the **EU AI Act** classifies recruitment/candidate evaluation AI as **high-risk** with obligations on risk management, data governance, transparency, human oversight; NYC Local Law 144 requires bias audits for automated employment decision tools.)
- **Transparency** to candidates and recruiters about AI use; documentation of training data, features and evaluation; monitoring over time (bias can drift).
- Diverse evaluation data, and parsing quality checks across resume formats and languages.
**What I'd refuse to build**: inference of protected characteristics (gender, ethnicity, age, health, pregnancy, religion) from resumes or photos; **emotion or personality analysis from video interviews or voice** (scientifically weak and banned/restricted in employment contexts under the EU AI Act); fully automated rejection without human review; scoring based on social media profiling unrelated to the job; models trained to mimic past hiring decisions without bias auditing; any feature designed to screen out people with employment gaps, disabilities or parental status. Raising these concerns with stakeholders and offering a compliant alternative is the professional response.

---

## F. EVALUATION & DATA

### 74. From the Turing project: what makes annotation data high quality? How do you detect a lazy or adversarial annotator?
**High-quality annotation data**:
- **Clear, versioned guidelines** with definitions, worked examples and edge cases; updated as ambiguities are discovered (and each annotation records the guideline version).
- **Qualified annotators**: entry tests on gold tasks, domain expertise where needed (coding tasks need programmers), ongoing calibration sessions.
- **Well-designed tasks**: specific rubric dimensions (correctness, helpfulness, safety, instruction-following) rather than one vague score; pairwise comparisons often more reliable than absolute ratings; requiring a **written justification** for preferences.
- **Redundancy and agreement**: multiple annotators on a subset, agreement measured (Krippendorff's alpha / Cohen's kappa), disagreements adjudicated by experts; **low agreement means the guideline is ambiguous**, not only that annotators are bad.
- **Diversity and coverage** of prompts (topics, difficulty, languages), and balanced positions (randomise which response is shown as A/B).
- **Review pipeline**: reviewers audit a sample of each annotator's work; feedback loops.
**Detecting lazy or adversarial annotators**:
- **Gold/honeypot tasks** with known answers mixed in invisibly: accuracy below threshold flags them (the strongest signal).
- **Agreement with consensus/peers** over time (persistently low, after accounting for task difficulty).
- **Time per task**: implausibly fast completion relative to task length; uniform timing patterns.
- **Response patterns**: always choosing A (position bias), always the longer response, identical ratings across dimensions, low-variance scores, copy-pasted or templated justifications, justifications that don't match the choice.
- **Text quality checks** for written content: plagiarism/duplicate detection, **AI-generated text detection** for written responses (a real problem: annotators pasting LLM output), grammar/length heuristics.
- **Adversarial** signals: systematically inverted preferences on gold tasks (deliberately wrong), coordinated patterns across accounts.
Act on it: retrain/coach first, then reduce task access or remove; **re-check or discard** their past annotations (that's why annotator IDs are stored with every label).
**Your story:** describe what your RLHF dashboard actually supported (task workflows, response comparison, scoring) and any quality mechanism you built or saw (gold tasks? reviewer layer? stats in Redis?).

### 75. How do you build a golden eval set for a domain like insurance with 3 SMEs and no budget? How many examples is enough?
**Plan**:
1. **Define what you're evaluating** (e.g. RAG answers about policy wordings, or field extraction from submissions) and the **task taxonomy**: question types / document types / difficulty levels, including edge cases and unanswerable questions. Agree on the scoring rubric with SMEs upfront.
2. **Source candidates cheaply**:
   - **Real queries/documents** from logs, support tickets, emails to the team (most representative). For extraction: real documents spanning brokers/templates/quality.
   - **LLM-generated drafts**: have an LLM generate questions and draft answers from documents, or pre-extract fields; this turns SME time from *writing* into *reviewing/correcting*, which is 3–5× faster.
3. **SME time, used efficiently**: short sessions (e.g. 2 hours/week each), a simple labelling UI (even a spreadsheet or Label Studio, which is free), clear instructions. Each SME reviews/corrects; **overlap ~10–20% of items** between SMEs to measure agreement and catch ambiguity; disagreements resolved together (that discussion often improves the rubric).
4. **You do the pre-work**: dedupe, cover the taxonomy, prepare the context (documents, relevant passages) so SMEs only judge.
5. **Version and store** the dataset in the repo/eval tool with metadata (who labelled, when, category).
**How many is enough**: depends on the decisions you need to make. Rough guide: **50–100 examples** is enough to start and to catch big regressions; **200–500** to compare variants with differences of a few percentage points with reasonable confidence; more for many categories (you want ~20–30+ per important category to see per-category performance). Statistics: with 100 examples, a measured 85% accuracy has a 95% confidence interval of roughly ±7 points, so small differences between prompts are noise at that size. Start small, then **grow continuously from production failures and reviewed corrections** (Q78), which is effectively free labelled data in an extraction system with human review.

### 76. Offline eval says the new prompt is better; online metrics say it's worse. What do you do?
Don't ship based on either blindly. **Investigate the disagreement**: it means the offline eval doesn't represent what matters online, or the online metric is misleading.
1. **Check the online result is real**: sample size and significance, experiment setup (assignment bugs, both arms receiving the same traffic mix, novelty effects, a concurrent change elsewhere, a segment with very different behaviour), metric instrumentation correct for both arms.
2. **Check the offline eval's representativeness**: is the golden set distribution like production traffic (topics, document types, lengths, languages)? Is it stale? Has it been **overfitted** (prompts tuned repeatedly against the same set)? Is the judge metric aligned with what users value (e.g. the judge rewards longer, more detailed answers while users want short answers: verbosity bias)?
3. **Segment the online results**: where exactly is it worse (which topics/tenants/document types)? Pull **examples of online failures** for the new prompt and compare side by side with the old prompt's outputs for the same kinds of inputs.
4. **Check non-quality factors**: latency (a longer prompt or longer outputs make the UX worse even if answers are "better"), cost, format changes that break UI parsing or downstream code, more refusals.
5. **Fix the eval**: add the online failure cases to the golden set, rebalance it to match production, recalibrate the judge against human labels, add the missing metric (e.g. conciseness, latency).
6. **Decide**: usually keep the old prompt (online reality wins for users), iterate on the new prompt using the improved eval, and re-test. The lasting value is the improved eval set; the goal is offline and online agreeing in future.

### 78. How do you close the loop from production failures back into your eval set?
1. **Capture failures with full context**: every failure signal (thumbs-down with reason, human-review corrections, validation failures, escalations, support tickets, incident reports, LLM-judge flags on sampled traffic, drift alerts) linked to the **trace** (input, retrieved context, prompt version, model, output).
2. **Triage queue**: someone (rotation) reviews flagged traces weekly, confirms whether it's a real failure, **labels the root cause category** (retrieval miss, chunking, ranking, generation, extraction field X, tool selection, guardrail false positive...) and writes the **expected output**/correct label.
3. **Add to the eval set**: convert the confirmed case into an eval item (input + context + expected output + category + source "production failure, date"), **anonymised/redacted** per data governance (Q62), with SME sign-off for domain answers. For extraction, corrected fields from the review UI can flow in almost automatically.
4. **Fix and verify**: the fix (prompt/retrieval/code/model) must make the new case pass **without regressing** the rest of the suite (CI eval, Q61). The case stays as a permanent regression test.
5. **Track**: failure categories over time (what's the biggest bucket now?), time from failure detection to fix, and the eval set's composition (keep it balanced; don't let it become only edge cases: maintain a representative core set plus a "hard cases" set).
6. **Cadence**: weekly triage, monthly review of category trends to decide bigger investments (e.g. "40% of failures are table extraction → invest there").

---

## G. FORWARD-LOOKING (longer ones)

### 85. If we gave you 3 months and 2 engineers to add AI to our product, how would you pick the first use case? What would make you say "not yet"?
**Picking the first use case (weeks 1–2)**:
1. **Collect candidates** from users, support, operations and sales: where do people spend lots of time on repetitive reading/writing/searching/classifying? Look at data: ticket categories, process timings, manual steps.
2. **Score each candidate** on:
   - **Value**: hours saved, revenue impact, user pain; measurable baseline exists.
   - **Feasibility**: data available and accessible (documents, history, labels), the task is something current models do well (extraction, summarisation, classification, search/Q&A, drafting), integration effort.
   - **Risk / cost of errors**: prefer use cases where **a human stays in the loop** and an error is cheap to catch (drafts, suggestions, triage, internal search) over autonomous high-stakes decisions (pricing, claims denial, hiring).
   - **Evaluability**: can we define success and build a golden set quickly?
   - **Data governance**: allowed to send this data to an LLM provider? Residency?
3. **Pick a narrow, high-value, low-risk, measurable** use case, e.g. for an insurance product: submission email triage + extraction with human review, or internal policy-wording Q&A for underwriters with citations. Not a general chatbot.
**Plan (3 months, 2 engineers)**: weeks 1–3: golden set with SMEs + baseline measurement + quick prototype to prove feasibility on real data; weeks 4–8: build the production version (gateway, guardrails, observability, evals in CI, human-review UX) for a pilot group; weeks 9–12: pilot with real users, measure against the baseline, iterate, decide on rollout. Ship something real to real users before the end, even if small.
**"Not yet" signals**: no measurable success criterion or baseline; **no access to representative data** (or legal won't allow sending it to any available provider); the task needs **deterministic, auditable correctness** that code/rules can deliver (then build that instead); error costs are high and there's no feasible human review; the underlying process is broken or undocumented (AI would automate chaos); no SME availability to define correct answers; or the stakeholder wants "AI" rather than an outcome. Saying "not yet, here's what needs to be true first" is a strong answer.

### 90. What would you do differently if you rebuilt your Espire RAG pipeline today?
**Your story:** answer from your real pipeline. A strong answer names **3–4 specific changes, each tied to an observed problem or a measurable expected gain**. Common, credible ones (use only those that apply):
1. **Evaluation from day one**: a golden set with SMEs (50–200 real questions with labelled sources), retrieval metrics (recall@k/MRR) and answer metrics (faithfulness, correctness, refusal rate) running in CI, so every change is measured instead of eyeballed. (If you had none, this is the #1 answer: say it plainly.)
2. **Hybrid search + reranking**: BM25 + vectors fused with RRF, plus a reranker (or Azure AI Search's semantic ranker), and fewer, better chunks in the prompt.
3. **Structure-aware chunking with context**: chunk by headings/sections, keep tables intact, prepend document title and section path (contextual chunk headers), store page numbers for citations.
4. **Permission-aware retrieval** (ACL metadata filtered inside the search) if it wasn't there, plus deletion handling and incremental re-indexing with change detection.
5. **"I don't know" behaviour**: a relevance gate and structured `answerable` output, with citations validated before display.
6. **Observability and feedback**: tracing per request (retrieval results, prompt version, tokens, cost), thumbs up/down with reasons feeding a triage queue that grows the eval set.
7. **Thinner code**: replace framework abstractions with direct SDK calls where they hid prompts or made debugging hard.
8. **Conversation handling**: query rewriting for follow-up questions.
Close with the result you'd expect and how you'd measure it ("I'd expect recall@5 to rise substantially for identifier-heavy questions; I'd prove it on the golden set before and after").
