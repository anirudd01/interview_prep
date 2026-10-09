# Round 6 — Gap Fill & Staff Readiness: Answers, Section H (Data Engineering & Event Streaming)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. Original question numbers are kept.
Each answer leads with the mechanism, then the trade-offs, then how it maps to an insurance platform like Aurora/Pulse. Where a question touches your own experience there is a **Your story:** note. Fill it from what you actually did and don't invent anything.

---

## H. DATA ENGINEERING & EVENT STREAMING

### 67. Batch vs streaming vs micro-batch: decision criteria. What are the Lambda and Kappa architectures?
**Batch** processes a bounded dataset on a schedule (nightly bordereaux, month-end premium reconciliation). **Streaming** processes an unbounded dataset record by record as it arrives (Flink, Kafka Streams). **Micro-batch** cuts the stream into small bounded chunks every few seconds and runs a mini batch job on each one (Spark Structured Streaming's default trigger, Databricks/Fabric streaming jobs).

Decision criteria, in the order I'd actually ask them:
1. **Latency the business needs.** "Broker dashboard updates within seconds" means streaming. "Finance needs GWP by 9am" means batch. Most "we need real time" requests turn out to be "every 5-15 minutes" once you ask what decision depends on it.
2. **Correctness and completeness.** Batch sees the whole dataset, so joins, dedup and late corrections are trivial. Streaming has to reason about late and out-of-order data (see Q73) and keep state.
3. **Cost and operational burden.** A streaming job is a 24/7 stateful service: checkpoints, state stores, rebalances, on-call. A batch job is a scheduled container that can fail and retry.
4. **Statefulness of the logic.** Stateless filter/enrich is easy in any mode. Large windowed joins or aggregations over days are expensive to keep as streaming state.
5. **Team skills.** A team that knows SQL and Airflow ships batch reliably. Flink in production needs people who understand checkpoints and watermarks.

Micro-batch is the pragmatic middle: seconds-to-minutes latency, exactly-once into Delta with idempotent commits, and the same code/API as batch.

**Lambda architecture** (Nathan Marz): two parallel paths. A **batch layer** recomputes accurate views from the immutable master dataset, a **speed layer** gives approximate low-latency views over recent data, and a **serving layer** merges them. The problem is you write and maintain the same business logic twice, in two frameworks, and they drift.

**Kappa architecture** (Jay Kreps): one path. Everything is a stream from a durable, replayable log (Kafka with long retention or tiered storage). To fix a bug or change logic, you deploy a new version of the streaming job, replay the log from offset 0 into a new output table, and switch readers over. It needs a log that holds enough history and a processor that can replay fast.

Modern reality: most lakehouse teams do a "Kappa-ish" design with Delta/Iceberg tables as the replayable source, where the same Spark code runs as streaming or as a batch backfill. For insurance, a common honest answer is: stream for operational views (quotes per broker, bind rate), batch for the book of record (GWP to finance, regulatory returns), because finance numbers must be reproducible and reconciled.

### 68. Lakehouse basics: Parquet, Delta Lake, Apache Iceberg. What do table formats add over plain Parquet files in S3/Blob (ACID, time travel, schema evolution)?
**Parquet** is a columnar **file format**: one file, organised into row groups, each row group holding column chunks with encoding, compression and min/max statistics. It knows nothing about other files. A "table" of plain Parquet in ADLS is just a folder convention like `policies/year=2026/month=10/*.parquet`.

Problems with plain Parquet folders:
- **No atomicity.** A job writing 200 files that dies at file 120 leaves a half-written table, and readers see it.
- **No isolation.** A reader listing the folder while a writer adds or deletes files gets an inconsistent snapshot.
- **No updates or deletes.** Changing one policy row means rewriting files yourself. GDPR "delete this broker's data" is painful.
- **Schema is implied by the files**, and different files can silently disagree.
- **Listing is slow** on object storage at millions of files, and query planning has to open footers to get statistics.

A **table format** adds a **metadata layer** on top of the Parquet files that defines exactly which files make up the table at each version.
- **Delta Lake**: a `_delta_log/` folder of ordered JSON commit files (`00000000000000000042.json`), each listing files added/removed, plus periodic Parquet checkpoints. A commit is an atomic "put if absent" of the next log file, which gives **optimistic concurrency**: two writers race, one wins, the other retries or fails on conflict. Delta is the native format of Databricks and **Microsoft Fabric OneLake**.
- **Apache Iceberg**: a tree of metadata JSON file -> manifest list -> manifests -> data files, with a **catalog** (REST catalog, Polaris, Unity Catalog, Glue) holding the pointer to the current metadata file. A commit is an atomic swap of that pointer. Iceberg's standout features are **hidden partitioning** (partition by `days(bound_at)` without users having to filter on a derived column) and **partition evolution** without rewriting data.

What the format gives you:
- **ACID transactions**: readers see a consistent snapshot, writes are all-or-nothing, `MERGE`/`UPDATE`/`DELETE` work (via file rewrites or deletion vectors).
- **Time travel**: query an old version, e.g. "what did the policy table look like when we sent the September bordereau?" Old files are kept until `VACUUM` (Delta) or snapshot expiry (Iceberg) removes them, so retention is a cost/compliance decision.
- **Schema enforcement and evolution**: writes with mismatched schema are rejected; adding a column is a metadata change. Iceberg tracks columns by ID, so renames and drops are safe.
- **Performance metadata**: per-file statistics in the log enable file skipping without opening every footer; compaction (`OPTIMIZE`) and clustering (Z-order, liquid clustering) fix the small-files problem from streaming writes.

```sql
-- Delta: upsert today's policy changes, then audit an old version
MERGE INTO lake.policies t
USING staging.policy_changes s ON t.policy_id = s.policy_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;

SELECT SUM(gross_premium) FROM lake.policies VERSION AS OF 1830;
```

As of 2026 the Delta vs Iceberg war is mostly a truce: Delta UniForm writes Iceberg metadata too, Fabric and Databricks read both, and the catalog choice matters more than the file format. On Azure the typical stack is ADLS Gen2 or OneLake storage, Delta tables, and Fabric or Databricks for compute.

### 69. Kafka log compaction, retention and tombstones: when do you use a compacted topic?
A Kafka partition is an append-only log split into **segments**. Each topic has a `cleanup.policy`:
- **`delete`** (default): whole segments are deleted once older than `retention.ms` (7 days default) or once the partition exceeds `retention.bytes`. It's time/size based and ignores keys. Use it for event streams: "QuoteRequested", "PolicyBound", click logs.
- **`compact`**: a background log cleaner keeps **at least the latest record per key** and removes older records with the same key. The active segment is never compacted, and `min.compaction.lag.ms` / `min.cleanable.dirty.ratio` control how soon cleaning happens. So compaction is eventual: consumers can still see duplicates for a key, just never lose the latest one.
- **`compact,delete`**: latest per key, but also drop anything older than retention.

**Tombstone**: a record with a key and a **null value**. It means "this key is deleted". Compaction removes older values for that key, keeps the tombstone for `delete.retention.ms` (24h default) so slow consumers still see the delete, then removes the tombstone too. A consumer that's offline longer than that can miss deletes, which is a real bug source.

When to use a compacted topic: when the topic represents **current state per entity** rather than a history of events, and a new consumer should be able to rebuild the full state by reading from the beginning.
- Reference data: broker table keyed by `broker_id`, product/rater config keyed by `product_code`, FX rates keyed by currency pair.
- CDC snapshots of a table (Debezium, keyed by primary key) that downstream services materialise into a local cache.
- Kafka's own internals: `__consumer_offsets`, and Kafka Streams changelog topics for state stores, are compacted.

When not to: anything where history matters (premium changes, audit trail, event sourcing). Compaction throws away the intermediate states. For an event-sourced policy you want `delete` with long retention or tiered storage, or the events landed in Delta.

Azure note: **Event Hubs** speaks the Kafka protocol, and supports log compaction on the Premium and Dedicated tiers. Retention is capped by tier (up to 90 days on Premium/Dedicated), so "replay from the beginning of time" designs usually land events in ADLS via Event Hubs Capture or a Fabric eventstream.

### 70. Event schema evolution: Avro / Protobuf / JSON Schema with a schema registry. Explain backward, forward and full compatibility, and which side (producer or consumer) needs which.
**Schema registry** (Confluent Schema Registry, Apicurio, Azure Event Hubs Schema Registry): a service that stores versioned schemas per **subject** (usually `<topic>-value`). The producer serializer registers or looks up the schema and prefixes each message with a small **schema ID** (Confluent wire format: magic byte + 4-byte ID), so messages don't carry the whole schema. The consumer deserializer fetches the writer's schema by ID and resolves it against its own reader schema. The registry **rejects a new schema version** that breaks the subject's configured compatibility rule, which is how you stop breaking changes at CI or deploy time instead of in production.

Definitions are always about **which schema reads which data**:
- **Backward**: the **new** schema can read data written with the **old** schema. Consumers upgrade first.
- **Forward**: the **old** schema can read data written with the **new** schema. Producers upgrade first.
- **Full**: both. Upgrade in any order.

| Mode | Guarantee | Allowed changes (Avro) | Who upgrades first |
|---|---|---|---|
| BACKWARD (Confluent default) | New reader reads old data | Delete a field; add a field **with a default** | **Consumers** first, then producers |
| FORWARD | Old reader reads new data | Add a field; delete a field **that had a default** | **Producers** first, then consumers |
| FULL | Both directions | Add or delete only fields **with defaults** | Either order |
| NONE | No checks | Anything | Coordinated big-bang (avoid) |

Each mode also has a `_TRANSITIVE` variant (e.g. `BACKWARD_TRANSITIVE`), which checks against **all** previous versions, not just the last one. You want transitive when consumers may replay the topic from the beginning and hit version-1 messages.

Worked example: the `PolicyBound` event gets a new `broker_commission_pct` field.

```json
{
  "type": "record", "name": "PolicyBound", "namespace": "com.aventum.pulse",
  "fields": [
    {"name": "policy_id", "type": "string"},
    {"name": "gross_premium", "type": {"type": "bytes", "logicalType": "decimal", "precision": 18, "scale": 2}},
    {"name": "currency", "type": "string"},
    {"name": "broker_commission_pct", "type": ["null", "double"], "default": null}
  ]
}
```

Because the new field has a default, it's FULL compatible: an old consumer ignores the unknown field, a new consumer reading an old message gets `null`. Renaming `gross_premium` to `gwp` is not compatible in any mode (it's a delete plus an add without a default); in Avro you'd use `aliases` or, better, add the new field and deprecate the old one over two releases.

Format notes:
- **Avro**: needs the writer schema to decode, which is why the registry is essential. Defaults are what make evolution work.
- **Protobuf**: fields are identified by **field number**, not name. Adding fields is safe, renaming is safe on the wire, but never reuse or change the type of a number; mark removed numbers `reserved`. In proto3 every field is effectively optional, so "required" must be enforced in code or contracts. `buf breaking` checks this in CI.
- **JSON Schema**: the most familiar, but compatibility is trickier because of open vs closed content models (`additionalProperties`). Adding a field to a closed schema breaks old readers. Payloads are also bigger.

Interview-ready summary: "Backward means I can upgrade consumers first, forward means I can upgrade producers first. For a topic many teams consume, I'd pick FULL_TRANSITIVE and make every new field optional with a default, so nobody has to coordinate a deploy order."

### 71. Data contracts: what are they, and how do they stop an upstream team from silently breaking your pipeline?
A **data contract** is an explicit, versioned agreement between a data **producer** (usually an application team) and its **consumers** about a dataset or event stream, treated like an API. It typically covers:
- **Schema**: fields, types, nullability, allowed values (e.g. `currency` is ISO 4217, `gross_premium >= 0` except on cancellations).
- **Semantics**: what a field actually means. "`gross_premium` is annual premium in policy currency, before commission and tax." This is where most real breakage happens, not in types.
- **SLAs**: freshness (bordereau delivered by 06:00 UTC), completeness, latency, volume ranges.
- **Ownership**: a named owning team and an on-call/escalation path.
- **Change policy**: compatibility rule, deprecation period, how consumers are notified.
- **Classification**: PII fields, retention, who may access it.

It's usually a YAML file in the producer's repo (Open Data Contract Standard / ODCS is the common spec now) that compiles into concrete checks.

How it stops silent breakage: by moving the check to the **producer's side, before the change ships**, instead of discovering it when your 2am job fails or, worse, succeeds with wrong numbers.
1. **CI gate on the producer**: a PR that changes the `PolicyBound` schema or the `policies` table is checked against the contract and the registry's compatibility rule. Breaking change -> the build fails, and the PR has to bump the major version and follow the deprecation process.
2. **Runtime enforcement at the boundary**: the schema registry rejects incompatible schemas; a validation step (Great Expectations, Soda, dbt tests, DLT expectations in Databricks) checks semantic rules like "premium not negative", "currency in allowed set", row counts within expected range. Bad records go to a quarantine/dead-letter table instead of into the gold layer.
3. **Versioning**: breaking changes publish as `policy_bound.v2` alongside v1 for an agreed overlap window.
4. **Ownership and alerting**: the producer gets paged on contract violations, not the consumer.

The cultural part is the real point at staff level: the contract makes the producer team accountable for downstream impact, which they never were when the "interface" was just "we read their database". The strongest version of this is "no consumer reads another team's operational database directly; they read a contracted event stream or published table."

**Your story:** think of a time a rater workbook or upstream data change in Aurora/Pulse or Cellular broke something downstream (a renamed column, a changed rating factor format). How was it detected, and what would a contract plus CI check have caught? If you put a Pydantic model or JSON Schema at an API boundary to validate inputs, that is a lightweight contract; say so and explain how you'd extend it.

### 72. Airflow / Dagster: DAGs, idempotent tasks, backfills, and why tasks should not pass large data between each other through the orchestrator (e.g. Airflow XCom).
A **DAG** is a directed acyclic graph of tasks with dependencies, plus a schedule. The orchestrator decides what runs when, retries failures and records state. It should **orchestrate work, not do the work**; heavy compute runs in Spark, a warehouse, a K8s pod, or an Azure Function.

**Airflow** is task-centric: you define tasks and their order. Each DAG run has a **logical date / data interval** (e.g. 2026-10-08 00:00 to 2026-10-09 00:00), which tasks should use to decide what data to process. Airflow 3 (2025) added DAG versioning, a Task SDK that isolates task execution from the metadata DB, and renamed datasets to **assets** for data-aware scheduling. **Dagster** is asset-centric: you declare the tables/files you want to exist (`@asset def daily_gwp(policies): ...`) and Dagster derives the graph, tracks lineage and freshness, and has first-class **partitions** (daily, per broker). Many teams find Dagster's model maps better to "I want this table to be correct" thinking.

**Idempotent task**: running it twice for the same interval gives the same end state as running it once. That's what makes retries and backfills safe. Rules:
- Parameterise by the run's data interval, never by `now()`.
- Write by **overwriting a partition** or `MERGE` on a key, never blind `INSERT`/append.
- Make side effects safe: an email or an API post to a broker needs a dedup key.
- Keep tasks deterministic: same inputs, same outputs.

```python
@task
def load_daily_premium(data_interval_start=None, data_interval_end=None):
    day = data_interval_start.date()
    # Overwrite exactly one partition: rerunning the 2026-10-08 run replaces, never duplicates
    spark.sql(f"""
        INSERT OVERWRITE lake.daily_gwp PARTITION (bound_date = '{day}')
        SELECT broker_id, currency, SUM(gross_premium) AS gwp
        FROM lake.policies
        WHERE bound_at >= '{data_interval_start}' AND bound_at < '{data_interval_end}'
        GROUP BY broker_id, currency
    """)
```

**Backfill**: running the DAG for past intervals, e.g. after fixing a premium calculation bug you rerun 1 Jan to 30 Sep. In Airflow: `airflow backfill create --dag-id gwp --from-date 2026-01-01 --to-date 2026-09-30` (Airflow 3 runs backfills through the scheduler), with `max_active_runs` capping parallelism so you don't flatten the warehouse. `catchup=False` on new DAGs stops an accidental backfill of years of history at deploy. Backfills only work if tasks are idempotent and partitioned by interval; otherwise you double-count.

Why not pass large data through XCom:
- XCom values are stored in the **Airflow metadata database** (Postgres/MySQL). Pushing a 500MB DataFrame bloats the DB that the scheduler depends on, slows every scheduler loop, and can take the whole Airflow instance down.
- Serialisation through the DB is slow and memory-hungry on workers.
- It couples tasks to the orchestrator's storage and makes data invisible to everything else (no lineage, no reuse, no query).

The pattern: tasks write data to durable storage (ADLS/Blob, a Delta table) and pass only a **reference** through XCom: a path, a table name plus partition, a row count. Airflow supports custom XCom backends (object storage) if you must, and Dagster formalises this with **IO managers** that persist each asset to storage and load it for the next step.

**Your story:** you've used Celery, cron and APScheduler. Be ready to say how those differ from an orchestrator: they schedule jobs but don't model dependencies, data intervals or backfills. If any Cellular or Aurora batch jobs (e.g. Azure Functions on a timer) had to be rerun for a past day, explain whether they were idempotent.

### 73. Stream processing: event time vs processing time, watermarks, tumbling/sliding/session windows, late data. Explain with "gross written premium per hour".
**Event time** is when the thing actually happened, stamped by the source: the policy was bound at 10:58. **Processing time** is when the stream processor sees the record: 11:04, because the broker portal's outbox was backed up, or a consumer was restarting. Aggregating by processing time is easy but wrong for finance: a pod restart moves premium from one hour to another. GWP per hour must be computed on **event time**.

The problem with event time is that the stream is **out of order** and **never complete**: the processor can't know if more 10:00-hour policies are still coming. A **watermark** is the processor's estimate of event-time progress: "I believe I have now seen all events with event time <= W." The common heuristic is `W = max event time seen - allowed delay`. When the watermark passes the end of a window, the window is considered complete, its result is emitted, and its state can be dropped. The delay is the trade-off: bigger means more complete, but later results and more state.

**Window types**, all on GWP:
- **Tumbling**: fixed-size, non-overlapping. GWP per clock hour: [10:00, 11:00), [11:00, 12:00). Each policy belongs to exactly one window. This is the question's case.
- **Sliding (hopping)**: fixed size, overlapping, advancing by a slide. "GWP over the last 24 hours, updated every hour": each event lands in 24 windows. Good for dashboards and anomaly alerts.
- **Session**: dynamic windows per key, closed after an inactivity gap. "Broker quoting session": all quote events from one broker with gaps under 30 minutes form one session; useful for quote-to-bind conversion, not for GWP.

**Worked example**: tumbling 1-hour windows on `bound_at`, watermark delay 10 minutes.

| Event | Event time | Arrives (processing time) | Watermark at arrival (approx) | Outcome |
|---|---|---|---|---|
| P1, 1,000 GBP | 10:12 | 10:12 | 10:02 | Into [10:00, 11:00) |
| P2, 2,500 GBP | 10:58 | 11:04 | 10:48 | Out of order but **on time**: watermark < 11:00, so window still open. Goes into 10:00 hour, not 11:00. |
| P3, 4,000 GBP | 11:11 | 11:11 | 11:01 | Watermark crosses 11:00: window [10:00, 11:00) **fires** with 3,500 GBP |
| P4, 1,200 GBP | 10:47 | 11:25 | 11:15 | **Late**: its window already closed |

P2 shows why event time matters: by processing time it would have been counted in the 11:00 hour. P4 is late data, and you must choose a policy explicitly:
1. **Drop** it (the default in Spark Structured Streaming once outside the watermark). Silent loss of premium is unacceptable for finance numbers.
2. **Allowed lateness**: keep window state longer (Flink `allowedLateness(Duration.ofHours(2))`) and emit an **updated** result for [10:00, 11:00) = 4,700 GBP. The sink must be an **upsert** keyed by window (Delta `MERGE`, a compacted topic keyed by `hour`), not an append.
3. **Side output** late records to a dead-letter/late table and alert on volume.
4. **Reconcile in batch**: the stream gives a provisional hourly figure for dashboards, and a nightly batch over the complete Delta table produces the book-of-record GWP. This is the standard insurance answer.

```python
from pyspark.sql import functions as F

gwp_hourly = (
    policy_bound_stream                      # from Event Hubs via Kafka API
    .withWatermark("bound_at", "10 minutes")
    .groupBy(F.window("bound_at", "1 hour"), "currency")
    .agg(F.sum("gross_premium").alias("gwp"))
)
# outputMode("update") + foreachBatch MERGE into a Delta table keyed by (window, currency)
```

Insurance-specific traps a good interviewer will push on: **endorsements and cancellations** produce negative or adjusting premium events, so "GWP" is a sum of signed deltas, not of bound policies; **currency**: aggregate per currency, convert at a defined FX rate date; **duplicates**: at-least-once delivery means dedup on `event_id` (`dropDuplicatesWithinWatermark` in Spark); and the source must stamp event time, because a timestamp added by the consumer is processing time in disguise. Azure options: Spark on Databricks/Fabric, Fabric Real-Time Intelligence eventstreams, or Azure Stream Analytics (`TumblingWindow(hour, 1)` with late-arrival policy settings).

### 74. Row vs columnar storage: why columnar compresses well and scans fast, and at what point Postgres stops being enough for analytics.
**Row storage** (Postgres heap, MySQL InnoDB) stores each row's columns together in 8KB pages. Great for OLTP: fetch or update one policy by primary key is one or two page reads. Bad for analytics: `SELECT broker_id, SUM(gross_premium) FROM policies GROUP BY broker_id` on a 60-column table reads **every column of every row** from disk to use two of them.

**Columnar storage** (Parquet, ClickHouse, Fabric Warehouse, Snowflake, DuckDB) stores each column's values contiguously, in chunks (row groups / granules).

Why it compresses well: values in one column have the same type and often low variety, so lightweight encodings work extremely well before general compression even starts.
- **Dictionary encoding**: `currency` has maybe 10 distinct values across 50M rows, so store small integer codes.
- **Run-length encoding**: sorted or clustered columns (`status = 'BOUND'` repeated 10,000 times) become (value, count).
- **Delta and bit-packing**: timestamps and IDs stored as small differences in a few bits.
- Then zstd/snappy on top. 5-10x compression vs row format is normal, which also means less I/O.

Why it scans fast:
- **Column pruning**: read only the 2 columns the query touches.
- **Data skipping**: min/max statistics per row group (and partitioning) let the engine skip chunks entirely: `WHERE bound_at >= '2026-10-01'` skips everything older.
- **Vectorised execution**: operate on batches of thousands of same-typed values with tight loops and SIMD, instead of interpreting one row tuple at a time. Often operating directly on compressed data.

The cost: single-row updates and point lookups are expensive (a row is spread across many column chunks), so columnar systems prefer bulk appends and batch merges.

When Postgres stops being enough for analytics, the signals rather than a magic row count:
- Analytical queries over **tens to hundreds of millions of rows** take minutes, even with good indexes, because they're full scans by nature.
- Analytics **hurts OLTP**: long reporting queries hold snapshots (bloating tables, blocking vacuum), saturate I/O, and slow down quote/bind latency.
- You need to join across domains and systems (policies + claims + broker CRM + bordereaux files), which doesn't belong in an operational DB.
- Data volume and retention (years of history for actuarial work) make the DB too big to back up and restore quickly.

The escalation ladder I'd describe:
1. Fix the basics: indexes, `EXPLAIN (ANALYZE, BUFFERS)`, materialised views or summary tables refreshed on a schedule, declarative **partitioning** by date, BRIN indexes on time columns.
2. Move reporting to a **read replica** so it can't hurt the primary.
3. Columnar inside Postgres: extensions like Citus columnar or pg_duckdb, if you want to stay on one engine for moderate scale.
4. Real separation: **CDC** (Debezium, or Fabric mirroring for Azure SQL / Postgres) from Postgres into a lakehouse (Delta on ADLS/OneLake) and query with Fabric Warehouse / Databricks SQL, or an OLAP engine like ClickHouse for low-latency dashboards. DuckDB is a great answer for single-node analysis over Parquet up to hundreds of GB.

Good one-liner: "Postgres is my system of record. The moment analytics needs full scans over most of the history or starts competing with transactional latency, I replicate it out to columnar storage instead of tuning Postgres into something it isn't."

**Your story:** your resume lists Athena and Qubole, which are both columnar/lake query engines over S3. Be ready to say what data you queried with them, whether it was Parquet or raw JSON/CSV, and roughly how much. If the Jio recommender or ATS had reporting running against Postgres or MongoDB, describe where it started hurting and what you did about it.
