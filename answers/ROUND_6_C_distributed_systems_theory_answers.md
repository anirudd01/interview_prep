# Round 6 — Gap Fill & Staff Readiness: Answers, Section C (Distributed Systems Theory)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. Original question numbers are kept.
These are rapid-fire theory questions: learn the mechanism in each answer well enough to explain it in 60-120 seconds, then use the "push" notes to rehearse the follow-up a real interviewer would ask. Grading is on precision, so "Raft is for consensus" without terms, quorums and log matching is a fail.

---

## C. DISTRIBUTED SYSTEMS THEORY

### 19. Linearizability vs serializability vs sequential consistency vs eventual consistency: explain each with an example. What does "strict serializable" mean?
The key thing to get right: these come from two different worlds. **Linearizability** and **sequential consistency** are about **single objects / registers** (replication, "what does a read of key X return"). **Serializability** is about **transactions over many objects** (isolation, "do concurrent transactions look like they ran one at a time").

- **Linearizability**: every operation appears to take effect atomically at some instant between its start and its end, and that order respects **real time**. If write `x=5` finished before my read started, my read must see 5 (or something newer). Example: a leader-based etcd key, or a Postgres primary read. This is what people mean by "strong consistency".
- **Sequential consistency**: all clients see operations in **one single total order** that respects each client's own program order, but that order does **not** have to match wall-clock time. Example: client B might still read the old value after A's write completed, as long as everyone agrees on the same order eventually. Weaker than linearizable; ZooKeeper reads served by followers behave roughly like this (writes are linearizable, reads can lag unless you `sync`).
- **Serializability**: the result of concurrent transactions equals **some** serial execution of them, in **any** order, not necessarily real-time order. Example: T1 commits, then T2 starts and still logically "runs before" T1 is allowed. Postgres `SERIALIZABLE` (SSI) gives this.
- **Eventual consistency**: if writes stop, all replicas **converge** to the same value eventually. No guarantee about what a read returns in the meantime: stale reads, reading your own write missing, out-of-order. Example: DNS, Cosmos DB "Eventual" level, an async read replica.

**Strict serializability** = serializability **plus** linearizability's real-time constraint: transactions appear to execute one at a time **in an order consistent with real time**. If T1 committed before T2 began, T2 must see T1. Spanner (via TrueTime commit-wait), CockroachDB (close to it), FoundationDB, and a single-node Postgres `SERIALIZABLE` provide this.

Insurance anchor: a broker binds a quote, gets a 200, and immediately fetches the policy from another pod. If that read hits a lagging replica and returns "quote not bound", you've violated linearizability (read-your-writes is the minimum you need there). Cosmos DB's five levels are a good map: Strong (linearizable), Bounded Staleness, Session (read-your-writes per session), Consistent Prefix, Eventual.

**Push:** "Is Postgres REPEATABLE READ serializable?" No, it's snapshot isolation, which allows **write skew** (two on-call doctors both go off call). Only `SERIALIZABLE` (SSI) prevents it.

### 20. Explain Raft at a high level: terms, leader election, log replication. Why do you need a majority quorum, and why are clusters usually 3 or 5 nodes?
Raft makes a cluster agree on a **replicated log** of commands, so every node applies the same commands in the same order (replicated state machine). It's used by etcd (so every Kubernetes cluster), Consul, CockroachDB, TiKV, Kafka KRaft.

- **Terms**: time is divided into numbered terms (a logical clock). Each term has at most one leader. Any message with a higher term makes the receiver step down and adopt that term; stale leaders are rejected.
- **Leader election**: nodes start as followers. If a follower hears no heartbeat within a **randomized election timeout** (e.g. 150-300 ms), it becomes a candidate, increments the term, votes for itself and sends `RequestVote`. Each node votes **once per term**, and only for a candidate whose log is **at least as up to date** as its own (higher last term, or same term and longer). A candidate with a majority becomes leader. Randomized timeouts make split votes rare.
- **Log replication**: clients send writes to the leader. The leader appends to its log and sends `AppendEntries` (with the previous index and term so followers can detect gaps). Once a **majority** has persisted the entry, it's **committed**; the leader applies it and replies to the client. Followers that diverged get their conflicting suffix overwritten by the leader's log.

**Why majority**: any two majorities **overlap in at least one node**. So a new leader's majority always includes someone who has every committed entry, and the up-to-date-log voting rule guarantees the winner has them too. Committed data survives leader changes, and two leaders can't both commit in the same term.

**Why 3 or 5**: a cluster of N tolerates `floor((N-1)/2)` failures. 3 tolerates 1, 5 tolerates 2. **Even numbers buy nothing**: 4 nodes still tolerate only 1 failure (majority is 3) but add a node to every write quorum. Going above 5 makes writes slower (more acks needed, slowest of the majority dominates) without much availability gain. So etcd recommends 3 or 5, and AKS's managed control plane runs etcd for you on that basis.

**Push:** "What happens during a network partition?" The minority side can't elect a leader or commit writes, so it's unavailable for writes (CP). An old leader on the minority side keeps thinking it's leader until it sees a higher term; that's why linearizable reads need either a quorum round-trip (ReadIndex) or a leader lease.

### 21. Quorum reads and writes (R + W > N): explain them. What anomalies can still happen even when the inequality holds?
This is Dynamo-style **leaderless replication** (Cassandra, Riak, DynamoDB internally). Each key is stored on N replicas. A write is "successful" once W replicas ack; a read queries R replicas and takes the newest version. If `R + W > N`, the read set and the last write set **overlap in at least one replica**, so the read should see the latest write. Common setting: N=3, W=2, R=2. Tuning: W=N, R=1 for read-heavy; W=1 for fast writes with weaker durability.

Anomalies that still happen even with R + W > N:
- **Sloppy quorums and hinted handoff**: during a partition, writes may land on "substitute" nodes outside the key's home N. The overlap guarantee is gone until the hints are handed back.
- **Concurrent writes / clock-based LWW**: two clients write at the same time; with last-write-wins on timestamps, one write is **silently lost**, and clock skew can make an older write "win".
- **Write fails partially**: W wasn't reached, the client got an error, but the value landed on 1 replica and is **not rolled back**. Later reads may or may not see it.
- **Read concurrent with a write**: the write is on some replicas and not others; one read sees new, a later read sees old. No **linearizability**, even with strict quorums, unless reads do synchronous **read repair** before returning plus writers that also wait for quorum before acknowledging (and LWW timestamps still break it).
- **A replica holding the new value fails** and is restored from an older copy, dropping the count of replicas with the new value below W.
- **No monotonic reads** across different coordinators unless you add session stickiness.

So quorums give you **probabilistic, usually-fresh** reads, not strong consistency. If you need compare-and-set or uniqueness (e.g. "one active policy number per quote"), use a consensus-backed store or a single-leader DB.

### 22. Two-phase commit: how does it work, why does it block, and why do microservice architectures avoid it?
**2PC** makes a transaction atomic across multiple participants (databases, queues) via a **coordinator**:
1. **Prepare phase**: the coordinator asks every participant "can you commit?". Each participant does all the work, writes it durably (redo log, locks held) and votes **yes** or **no**. A yes vote is a **promise**: it can no longer unilaterally abort.
2. **Commit phase**: if all voted yes, the coordinator writes "commit" to its own log (the real commit point) and tells everyone to commit; if any voted no, it tells everyone to abort.

**Why it blocks**: if the coordinator crashes after participants voted yes but before they heard the decision, those participants are **in doubt**. They can't commit (maybe someone voted no) and can't abort (maybe the coordinator decided commit), so they hold their locks **until the coordinator recovers**. Meanwhile every other transaction touching those rows waits. It's a blocking protocol; 3PC tries to fix it but assumes bounded network delay, so nobody uses it. The real fix is making the coordinator itself fault-tolerant via consensus (what Spanner does: 2PC over Paxos groups).

**Why microservices avoid it**:
- It couples availability: the transaction succeeds only if **every** service and the coordinator are up, so availability multiplies down.
- Locks held across network round-trips kill throughput and latency.
- Many participants don't support XA at all (Kafka/Event Hubs, Redis, HTTP APIs, Cosmos across partitions, most SaaS APIs).
- It breaks service autonomy: one service's DB locks are held hostage by another team's service.

What they use instead: **sagas** (a sequence of local transactions with **compensating actions**, orchestrated or choreographed), the **transactional outbox** (write the business row and the event in the same local DB transaction, a relay publishes it), and **idempotent consumers**. Insurance example: "bind policy" = create policy in policy service, charge premium in billing, issue documents. If billing fails, the saga runs "cancel policy" rather than holding a cross-service lock.

**Push:** "Sagas give up isolation, what goes wrong?" Other requests can see intermediate state (policy exists, payment not yet taken). You handle it with semantic locks / status fields like `PENDING_PAYMENT`, and by ordering steps so the riskiest or most-likely-to-fail one goes first.

### 23. What is split-brain? How do leases and fencing tokens prevent it?
**Split-brain** is when two nodes both believe they are the leader (or lock holder, or primary) at the same time and both accept writes, so data diverges or gets corrupted. Classic causes: a network partition, or a **long GC / VM pause**: the old leader freezes for 30 s, the cluster elects a new one, the old one wakes up and carries on writing because from its point of view nothing happened.

**Leases**: leadership is granted for a bounded time (e.g. 10 s). The holder must renew before expiry; if it can't reach the lease authority it must **stop acting as leader** when its lease expires. Others wait until the lease has definitely expired (plus a clock-drift margin) before taking over. Kubernetes leader election (the `Lease` object in `coordination.k8s.io`) works this way for controllers. Weakness: it relies on bounded clock drift and on the holder **checking** the lease, and a process paused right after checking still writes with an expired lease.

**Fencing tokens** close that gap: every time the lock/lease is granted, the lock service hands out a **monotonically increasing number** (e.g. etcd revision, ZooKeeper zxid, a Postgres sequence). The client sends that token with every write, and the **storage layer rejects** any write with a token lower than the highest it has seen. The paused old leader comes back with token 33, the new leader already wrote with 34, so the storage refuses 33. Safety is enforced by the resource, not by the client's good behaviour.

```sql
-- fencing at the resource: only accept writes from the current or newer token
UPDATE rater_job SET state = 'done', fence = :token
WHERE job_id = :id AND fence <= :token;
-- 0 rows updated -> you are a zombie, stop
```

Common mistake: using a Redis `SET NX PX` lock (or Redlock) as if it were safe for correctness. It's fine for efficiency (avoid doing work twice), but without fencing it is not safe against pauses. Celery Beat running twice after a failover, or two workers both re-generating the same policy document, are exactly this bug.

**Your story:** if you've used Redis locks for task claim/unclaim (the RLHF dashboard) or for a singleton scheduler on AKS, be ready to say whether a pause could double-process, and how you made it idempotent or fenced.

### 24. What are CRDTs? Explain one (G-Counter, LWW-Register or OR-Set) and where you would use it.
**CRDTs (Conflict-free Replicated Data Types)** are data structures where replicas accept writes **independently, without coordination**, and are mathematically guaranteed to converge to the same state once they've exchanged updates. For state-based CRDTs this works because the **merge** function is commutative, associative and idempotent (a join-semilattice), so order, duplication and delay of messages don't matter. You get **strong eventual consistency**: same updates seen means same state.

**G-Counter (grow-only counter)**: each replica keeps a vector with one slot per replica. A replica only increments **its own slot**. Value = sum of all slots. Merge = **element-wise max**.

```python
def increment(state: dict[str, int], me: str) -> None:
    state[me] = state.get(me, 0) + 1

def merge(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {k: max(a.get(k, 0), b.get(k, 0)) for k in a.keys() | b.keys()}

def value(state: dict[str, int]) -> int:
    return sum(state.values())
```

Replica A has `{A:3, B:1}`, B has `{A:2, B:4}`, merge gives `{A:3, B:4}` = 7 no matter the merge order or how many times you re-merge. A **PN-Counter** is two G-Counters (increments minus decrements).

Others in one line: **LWW-Register** keeps the value with the highest (timestamp, replica-id), simple but loses concurrent writes. **OR-Set (observed-remove set)** tags each add with a unique id, and remove only deletes the tags it has observed, so a concurrent add wins over remove.

Where to use: multi-region active-active counters and sets (likes, view counts, rate-limit counters across regions), collaborative editing (Yjs, Automerge), shopping carts, presence. Redis Enterprise Active-Active and Riak use CRDTs; Cosmos DB multi-region writes offer custom conflict resolution with LWW by default.

Where **not** to use: invariants that need coordination, like "balance never below zero" or "only one bound policy per quote". CRDTs can't enforce those; you need consensus or a single writer.

### 25. Tail latency at scale: why does a fan-out to 100 backends make p99 latency the common case? Explain hedged requests and tied requests.
If a single backend is slow (above its p99) 1% of the time, a request that waits for **all** of 100 backends is fast only if every one is fast: `0.99^100 ≈ 0.366`. So **~63% of user requests see at least one p99-slow backend**. The backend's tail becomes the user's median. This is from Dean and Barroso's "The Tail at Scale". Causes of tails are mundane: GC pauses, noisy neighbours on a shared AKS node, compaction, cold caches, queueing, a background job.

**Hedged requests**: send the request to one replica; if it hasn't answered within roughly the **p95 latency**, send a second copy to another replica and take whichever answers first (cancel the other). Costs only ~5% extra load but cuts the tail dramatically. Must only be used for **idempotent/read** operations, and you should cap hedging (e.g. hedge budget of 5-10% of traffic) so it doesn't amplify load during an incident. gRPC has built-in hedging policy.

**Tied requests**: send the request to **two** replicas at once, each copy tagged with the other's identity. Whichever replica **starts executing** first sends a cancel to the other. This attacks queueing delay specifically, since the cost is mostly sitting in queues, and the duplicated work is small because the cancel happens at dequeue time. Add a small random delay between sends so both don't dequeue simultaneously.

Other tail tools worth naming: return partial results with a deadline (search, recommendation fan-out like the Jio recommender), micro-partitioning so load rebalances, probation for slow replicas, and simply reducing fan-out. For a rater fan-out across many insurer pricing modules, "return the quotes that came back in 1.5 s, mark the rest pending" is a legitimate product decision.

```python
import asyncio

async def hedged(call, replicas, hedge_after=0.05):
    first = asyncio.create_task(call(replicas[0]))
    done, _ = await asyncio.wait({first}, timeout=hedge_after)
    if done:
        return first.result()
    second = asyncio.create_task(call(replicas[1]))
    done, pending = await asyncio.wait({first, second}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    return done.pop().result()
```

### 26. Design the timeout budget for a request that calls three services in sequence with a 2-second SLA. What is deadline propagation, and what goes wrong without it?
Start from the SLA and work backwards. Reserve some time for the edge itself (auth, serialization, network to client), say ~200 ms, leaving ~1.8 s for A then B then C. Split by each service's observed p99, not evenly: e.g. A p99 = 150 ms, B (the rater) p99 = 700 ms, C p99 = 250 ms. Set per-call timeouts a bit above p99: A 300 ms, B 900 ms, C 400 ms = 1.6 s, leaving ~200 ms slack. Retries must fit inside the budget: at most one retry, only on idempotent calls, only if the **remaining** time is larger than that service's p50, with jittered backoff.

But fixed per-hop timeouts are not enough on their own, which is why you add **deadline propagation**: the entry point computes an **absolute deadline** (`now + 2s`) and passes it downstream (gRPC does this natively via `grpc-timeout`; over HTTP use a header like `X-Request-Deadline`). Each hop computes `remaining = deadline - now - safety_margin`, uses `min(own_timeout, remaining)` for its downstream calls, and **refuses to start work** if remaining is already below what's needed (fail fast with 504 instead of doing doomed work). Queued Celery/worker jobs should also check the deadline at dequeue and drop expired ones.

```python
async def call_downstream(client, url, deadline: float):
    remaining = deadline - time.monotonic() - 0.05
    if remaining <= 0:
        raise DeadlineExceeded()
    return await client.get(url, timeout=remaining,
                            headers={"X-Request-Deadline": str(remaining)})
```

What goes wrong without it:
- **Wasted work**: the client gave up at 2 s, but B and C keep computing for a response nobody will read. Under load this is pure capacity loss.
- **Retry amplification**: the client retries while the original chain is still running, so each user action becomes 2-3x load. With retries at every layer, 3 layers x 3 attempts = up to 27x on the bottom service.
- **Inconsistent timeouts**: a common bug is downstream timeouts longer than upstream (gateway at 2 s, service A calls B with 5 s, httpx default of 5 s, or no timeout at all). The inner timeout can never usefully fire.
- **Feeds metastable failure** (see 28): slow requests hold connections and threads, queues grow, everything times out, everything retries.

Also mention: clock skew means you propagate a **relative remaining time** per hop (or use monotonic time locally), not trust wall clocks across machines.

### 27. Gossip protocols and failure detection (e.g. phi-accrual): where are they used, and why not just send heartbeats to a central server?
**Gossip (epidemic) protocols**: every interval (e.g. 1 s), each node picks a few random peers and exchanges state (membership list, heartbeat counters, metadata). Information spreads like an infection and reaches all N nodes in **O(log N)** rounds, with each node doing constant work per round. It's robust: no single point of failure, tolerates message loss and node churn.

Where it's used: **Cassandra** and ScyllaDB (membership, schema, token ownership), **Consul/Serf and HashiCorp memberlist** (SWIM protocol), Redis Cluster's cluster bus, Akka Cluster, and the original Amazon Dynamo ring membership.

**SWIM** improves plain heartbeating: a node pings a random peer; if no ack, it asks k other nodes to ping it **indirectly** (so a single bad link doesn't cause a false accusation), then marks it "suspect" before "dead", and disseminates membership changes by piggybacking on pings.

**Phi-accrual failure detector** (Cassandra, Akka): instead of a binary "no heartbeat for 5 s = dead", it keeps a sliding window of heartbeat inter-arrival times and computes **phi** = how unlikely the current silence is given that history (phi = -log10 of the probability that a heartbeat would still arrive this late). Phi of 8 means about a 1-in-10^8 chance of being wrong. The application picks a threshold. It **adapts** to each link's normal jitter, so a cross-region peer with noisy latency isn't flagged as often as a fixed timeout would flag it.

Why not a central heartbeat server:
- It's a **single point of failure** and a scalability bottleneck (N nodes x heartbeats/s all hitting one box).
- It only measures "can the **center** reach X", not "can X's peers reach X"; a partition between the center and a healthy node produces false positives for the whole cluster.
- Detection and dissemination latency is bounded by one server's capacity.

The honest counterpoint: centralised is fine and often better at small scale or when you already have a consensus store. Kubernetes does exactly this: kubelets renew a `Lease` in the API server (etcd-backed) every ~10 s and the node controller marks nodes NotReady after ~40 s. That works because the control plane is already a replicated, highly available component, and a few thousand nodes is manageable.

### 28. What is a metastable failure? Why can a system stay down after the original trigger is gone, and how do you design against it?
A **metastable failure** is when a **trigger** (deploy, traffic spike, cache flush, brief network blip, a slow DB failover) pushes a system into a bad state that is then held there by a **sustaining feedback loop**, so it **stays down after the trigger is removed**. The system was running in a "vulnerable" state (efficient, high utilization) that has two stable equilibria, and the trigger knocks it from the good one into the bad one. Term from the 2021 HotOS paper (Bronson et al.) and the 2022 OSDI follow-up from AWS/academia.

Classic sustaining loops:
- **Retry storms**: latency rises, clients time out and retry, load doubles, latency rises further. Even when the original spike passes, retries keep load above capacity. Requests time out before completing, so **goodput drops to zero** while the servers are 100% busy.
- **Cache-miss loop**: Redis is flushed or a node restarts, all reads hit Postgres, Postgres slows, requests time out before they can repopulate the cache, so the cache never warms.
- **Queue backlog**: the worker queue (Celery/Event Hubs) builds a backlog of already-expired work; workers spend all their time on requests whose callers left, so fresh requests also expire.
- **Autoscaling / connection loops**: new pods each open connection pools to an overloaded DB, adding load; health checks fail under load and Kubernetes restarts pods, reducing capacity further.

How to design against it (the theme: **break the feedback loop and shed load early**):
- **Retry budgets and backoff with jitter**: cap retries as a fraction of traffic (e.g. retries at most 10% of requests, token-bucket per client), retry at one layer only, use circuit breakers so a failing dependency gets fewer calls, not more.
- **Load shedding and admission control**: reject excess work fast with 429/503 at the edge rather than letting queues grow. Prefer **LIFO or bounded queues** and drop items whose deadline has passed (deadline propagation from 26).
- **Keep spare capacity**: don't run at 90% utilization; the vulnerable zone is the efficient zone.
- **Cache warming and request coalescing** (single-flight) so a cold cache doesn't stampede the DB; serve stale-while-revalidate.
- **Separate liveness from readiness** in K8s so overloaded pods are taken out of rotation rather than killed and restarted.
- **Recovery levers**: a way to drop traffic hard (kill-switch, rate-limit at the API gateway / Front Door) so the system can drain and climb back to the good state, then ramp traffic back gradually.
- **Test it**: load-test past saturation and check that goodput plateaus instead of collapsing, and that it **recovers** once load drops.

**Your story:** if any Aurora/Pulse or rater incident looked like "the DB recovered but the service stayed broken until we scaled down or restarted everything", that is a metastable failure, and naming the sustaining loop (retries, cold cache, backlog) is exactly the staff-level signal the interviewer wants. Don't claim one if it didn't happen; explain how you'd recognise it from metrics instead (high CPU, flat or falling success rate, rising retries per request).
