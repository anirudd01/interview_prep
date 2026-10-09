# Round 6 — Gap Fill & Staff Readiness: Answers, Section F (Linux, Networking & TLS Depth)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. Original question numbers are kept.
These are rapid-fire in the real round (60-120s each), so learn the mechanism and the two or three numbers per answer, then use the commands and "interviewer pushes on" notes to go deeper when asked. **Your story:** notes tell you what kind of real example to bring; fill them from your own incidents, don't memorise mine.

---

## F. LINUX, NETWORKING & TLS DEPTH

### 51. Walk through a TLS 1.3 handshake. What is SNI, how is the certificate chain validated, and what changes with mutual TLS?
**The handshake (1-RTT):**
1. **ClientHello** (plaintext): supported versions (TLS 1.3 is negotiated via the `supported_versions` extension, the legacy version field says 1.2), cipher suites (only 5 AEAD suites exist in 1.3, e.g. `TLS_AES_128_GCM_SHA256`, `TLS_CHACHA20_POLY1305_SHA256`), a **key_share** (the client guesses the group and sends its ephemeral public key up front, today usually the hybrid post-quantum `X25519MLKEM768` plus plain X25519), `signature_algorithms`, **SNI**, and **ALPN** (`h2`, `http/1.1`).
2. **ServerHello** (plaintext): picks the suite and sends its own key_share. Both sides now run (EC)DHE and derive the handshake keys via HKDF. If the server didn't like the client's group guess it sends a HelloRetryRequest, costing an extra round trip.
3. Everything after ServerHello is **encrypted**: `EncryptedExtensions` (ALPN result etc.), `Certificate`, `CertificateVerify` (a signature over the handshake transcript with the cert's private key, proving the server owns the key), `Finished` (MAC over the transcript).
4. Client verifies the chain and the signature, sends its own `Finished`, and application data flows. Total: one round trip before the client can send the request (vs two in TLS 1.2).

Key differences from 1.2 an interviewer likes: no RSA key exchange, so **forward secrecy is mandatory**; the certificate is encrypted; renegotiation, compression and CBC suites are gone. **Resumption** uses PSK tickets, and **0-RTT** lets the client send data in the first flight, but 0-RTT data is **replayable**, so only allow it for idempotent requests (or disable it, most backends should).

**SNI (Server Name Indication):** the hostname the client wants, sent in the ClientHello so a single IP (an ingress controller, App Gateway, Front Door) can choose which certificate to present and which backend to route to. It is in plaintext, which is why **ECH (Encrypted Client Hello)** exists: it encrypts the inner ClientHello with a key published in DNS (HTTPS records). Practical gotcha: clients that don't send SNI (old libraries, `openssl s_client` without `-servername`, connecting by IP) get the default cert and fail hostname checks.

**Chain validation**, in order:
- Build a path: leaf -> intermediates (sent by the server; a **missing intermediate** is the classic "works in Chrome, fails in Python" bug because browsers cache/fetch intermediates and `requests`/`certifi` don't) -> a root in the client's **trust store**.
- Verify each signature up the chain, validity dates (clock skew breaks this), `basicConstraints CA:TRUE` and path length on intermediates, key usage / EKU (`serverAuth`), name constraints.
- **Hostname match against the SAN** (Subject Alternative Name); CN is ignored by modern clients. Wildcards match one label only.
- Revocation: OCSP stapling or CRLs (the industry is moving away from OCSP; Let's Encrypt shut its OCSP service in 2025), and browsers also require **Certificate Transparency** SCTs.
- Context for 2026: CA/B Forum ballot SC-081 is shrinking public cert lifetimes (200 days from March 2026, 100 days in 2027, 47 days by 2029), so **automated renewal** (cert-manager, Key Vault auto-rotation, ACME) is no longer optional.

**Mutual TLS:** the server adds a **CertificateRequest** (with acceptable CAs) in its encrypted flight; the client replies with its own `Certificate` + `CertificateVerify`. The server validates the client chain against a **client CA bundle** (usually a private CA, not public roots), then maps the cert to an identity, typically from the SAN (in a service mesh that is a SPIFFE URI like `spiffe://cluster.local/ns/pulse/sa/rater`). What changes operationally: you now run a PKI (issuance, rotation, revocation), and authorization must still happen after authentication. Where TLS terminates matters: if App Gateway or APIM terminates mTLS, the backend only sees a forwarded header with the cert, which it must trust only from that proxy.

```bash
openssl s_client -connect api.example.com:443 -servername api.example.com -showcerts </dev/null
curl -v --cert client.pem --key client.key https://partner-api.example.com/health
```
**Your story:** GeoStorm (SOC2, OIDC) or Aurora/Pulse broker integrations are natural places for cert issues: an expired or missing intermediate, a partner requiring client certs, Key Vault cert rotation. Bring one concrete case if you have it.

### 52. A service intermittently fails with "connection reset by peer". List your hypotheses in order (idle timeouts, keep-alive mismatch, conntrack table, load balancer behaviour...).
"Connection reset" means a **TCP RST** arrived: something actively killed the connection. Step one is always finding **who sent the RST** (client side, server side, or a middlebox) with a packet capture on both ends. Hypotheses in rough order of likelihood for a cloud/K8s Python service:

1. **Keep-alive mismatch between client pool and server.** The client's pool reuses a connection the server already decided to close. Server idle timeouts are short: **uvicorn `timeout_keep_alive` = 5s**, **gunicorn `keepalive` = 2s**, Node 5s, nginx `keepalive_timeout` 75s. The client sends on a half-closed socket and gets an RST. Signature: fails on the **first request after an idle gap**, retry succeeds. Rule: **client idle timeout < server keep-alive timeout < load balancer idle timeout.**
2. **Middlebox idle timeout.** **Azure Load Balancer and Azure NAT Gateway default to 4 minutes** idle (LB configurable 4-100 min, with an optional "TCP reset on idle" that sends RSTs both ways); **AWS ALB 60s**, AWS NLB 350s, GCP Cloud NAT 1200s established. Long-lived DB, Redis or AMQP connections that sit idle die silently, and the next write gets an RST. Fix: TCP keepalives shorter than the timeout (Linux default `tcp_keepalive_time` is **7200s**, far too long), or app-level pings, or pool `pool_recycle`/`pool_pre_ping` in SQLAlchemy.
3. **Server-side process death / deploys.** Pods killed without graceful shutdown: in-flight connections get RST. Fix: `preStop` sleep so endpoints deregister before SIGTERM, handle SIGTERM, `terminationGracePeriodSeconds` longer than the longest request. Correlate failures with rollout and OOMKill times.
4. **Listen backlog overflow.** Accept queue full (slow worker, `somaxconn`, small `--backlog`); with `tcp_abort_on_overflow=1` the server RSTs, otherwise SYNs are dropped and you see timeouts. Check `nstat -az | grep -i listen` (`ListenOverflows`, `ListenDrops`).
5. **conntrack issues on nodes.** A full table (`nf_conntrack: table full, dropping packet` in dmesg) usually causes drops and timeouts rather than RSTs, but a known K8s failure mode is conntrack marking out-of-window packets INVALID, after which the pod answers with an RST; `net.netfilter.nf_conntrack_tcp_be_liberal=1` is the common fix. Check `conntrack -S` for `insert_failed`, `drop`.
6. **SNAT port exhaustion** on egress (see Q53): Azure outbound SNAT through the LB is limited per node, so connection attempts fail or get reset under bursty egress.
7. Less common: server closing a socket with **unread data in its receive buffer** (kernel sends RST instead of FIN), `SO_LINGER` with 0 timeout, firewalls/IDS injecting RSTs, TLS/proxy-protocol mismatch, MTU black holes (those look more like hangs).

```bash
tcpdump -i any -nn 'tcp[tcpflags] & tcp-rst != 0' -w rst.pcap   # who sends RSTs, to whom
ss -tino state established '( dport = :5432 )'                   # timers, keepalive, retrans
conntrack -S; sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max
```
**Interviewer pushes on:** "Retries fixed it, are we done?" No: retries on POST without idempotency keys can duplicate a quote or policy bind, and you've hidden the root cause. Fix the timeout ordering, then keep a single safe retry for idempotent calls.
**Your story:** Aurora/Pulse on AKS calling Cosmos/Postgres/Azure Functions, or Celery workers on the Jio ATS AKS cluster holding idle broker connections, are the classic places you'd hit the Azure 4-minute idle timeout. Bring a real one if you have it.

### 53. Ephemeral port exhaustion and TIME_WAIT: when does a high-throughput client hit them, and how do you fix it?
**Mechanism:** every outbound TCP connection needs a unique 4-tuple (src IP, src port, dst IP, dst port). To a **single destination IP:port**, the only variable is the source port, drawn from `net.ipv4.ip_local_port_range`, default **32768-60999 (about 28k ports)**. The side that **closes first** (the active closer) holds the socket in **TIME_WAIT for 60s** (hard-coded `TCP_TIMEWAIT_LEN`; `tcp_fin_timeout` is FIN_WAIT_2, a common mix-up). TIME_WAIT exists so late packets from the old connection aren't accepted by a new one with the same tuple.
So a client that opens a **new connection per request** and closes it can sustain only about **28,000 / 60s ≈ 470 new connections/sec** to one destination before `connect()` fails with **`EADDRNOTAVAIL` ("Cannot assign requested address")**. Through a proxy or a single LB VIP, every request looks like the same destination, so you hit it fast.

**When it bites in practice:** Python `requests.get()` without a `Session`, a new `httpx.Client` per call, Lambda/Functions creating clients inside the handler, load tests (locust) without connection reuse, and service-to-service calls through one VIP. In the cloud you often hit **SNAT exhaustion** first: Azure LB outbound rules allocate a fixed number of SNAT ports per node (only a few hundred to ~1k by default depending on pool size), and **Azure NAT Gateway gives 64,512 ports per public IP**; AKS exposes this as `allocatedOutboundPorts` and outbound IP count.

**Fixes, best first:**
1. **Reuse connections**: keep-alive + a pool (`requests.Session`, a long-lived `httpx.AsyncClient`, `aiohttp.TCPConnector(limit=...)`, DB pools). This removes the problem instead of tuning around it.
2. Make the **server** the active closer where you control it, so TIME_WAIT accumulates on the server (which has one listening port and no per-connection source-port cost).
3. Widen the range: `sysctl -w net.ipv4.ip_local_port_range="1024 65535"` (avoid ports your own services listen on).
4. `net.ipv4.tcp_tw_reuse=1`: lets **outbound** connections reuse TIME_WAIT sockets safely using TCP timestamps (recent kernels default to 2, loopback only). **Never `tcp_tw_recycle`**: it broke clients behind NAT and was removed in kernel 4.12.
5. More destination IPs/ports (multiple backends), or more egress IPs / NAT Gateway for SNAT.
6. `SO_LINGER(0)` to skip TIME_WAIT by sending RST: a hack, it can lose data. Mention it only to reject it.

```bash
ss -s                                        # summary incl. timewait count
ss -tan state time-wait | wc -l
ss -tan state time-wait '( dport = :443 )' | awk '{print $4}' | sort | uniq -c | sort -rn | head
sysctl net.ipv4.ip_local_port_range net.ipv4.tcp_tw_reuse
```
**Your story:** the Jio recommender at 100M req/day is roughly 1,150 req/s average and several times that at peak; if any hop opened a fresh connection per call (to Redis, Postgres, an internal API), you'd be over the 470/s ceiling. Be ready to say how your clients pooled connections there.

### 54. Load-balancing algorithms: round robin, least connections, consistent hashing, power-of-two-choices. When does each one behave badly?
- **Round robin** (and weighted RR): next backend in turn. Stateless, cheap, fair when requests cost the same and backends are identical. **Bad when** request costs vary a lot (one rater calculation takes 2s, another 20ms: slow requests pile up on unlucky backends), backends are heterogeneous (mixed node sizes, a noisy neighbour), or connections are long-lived (RR balances connections at setup time, not the load they carry later).
- **Least connections / least outstanding requests**: send to the backend with the fewest active connections or in-flight requests. Adapts to slow backends. **Bad when** connection count doesn't represent load (HTTP/2 or gRPC multiplexing, idle keep-alive connections), with many independent LB instances each seeing only part of the picture, and when a **new or freshly restarted instance** has zero connections and gets stampeded while its caches/JIT are cold (use slow-start / warm-up ramps). Nasty failure mode: a backend that **fails fast** (returns 500 in 1ms) always looks least loaded and becomes a **black hole** for traffic. Pair it with outlier detection / health checks.
- **Consistent hashing** (ring hash, Maglev, rendezvous/HRW): hash a key (user ID, session, cache key) to a backend so the same key lands on the same node, and adding/removing a node only moves about 1/N of keys. Used for cache affinity, sticky sessions, sharded state. **Bad when** keys are skewed (one hot tenant or broker floods one node), there are few virtual nodes (uneven ring), or capacity changes a lot (scale events still move keys and cause cache misses). Mitigation: **consistent hashing with bounded loads** (cap each node at about 1.25x average and overflow to the next) and enough vnodes.
- **Power of two choices (P2C)**: pick two backends at random, send to the less loaded one. Gets close to least-loaded quality with **exponentially better max load than random** and tolerates stale load info, which is why Envoy's `LEAST_REQUEST`, Linkerd and Finagle use it. **Bad when** the load signal is wrong (same fast-fail black-hole problem), the backend count is tiny (2-3 nodes, it degenerates), or the signal is very stale. Its whole point is that it beats "pick the global minimum", which with stale data makes every LB herd onto the same node.

**Interviewer pushes on:** "Which would you use for Pulse's rating API on AKS?" Reasonable answer: P2C/least-request at an L7 proxy because rating calls vary hugely in cost, with outlier ejection; consistent hashing only if a backend holds per-tenant compiled rater modules in memory (a Cellular-style cache), and then with bounded loads.

### 55. HTTP keep-alive and HTTP/2 multiplexing: why does gRPC load balancing break behind an L4 load balancer, and how do you fix it?
**Why it breaks:** an L4 balancer (Azure Standard LB, AWS NLB, and importantly a **Kubernetes ClusterIP Service** via kube-proxy iptables/IPVS) picks a backend **once per TCP connection**. HTTP/1.1 keep-alive already skews this a bit, but HTTP/1.1 can only carry one request at a time per connection, so clients open several connections and it roughly evens out. **gRPC runs on HTTP/2**, which multiplexes many concurrent streams over **one long-lived connection**, so a client opens one connection, it lands on one pod, and **every RPC from that client goes to that pod forever**. Symptoms: one pod at 90% CPU and others idle, and after you scale out, the new pods get **no traffic** because nobody reconnects.

**Fixes:**
1. **L7, request-aware proxy** that terminates HTTP/2 and balances per stream: Envoy, a service mesh (Istio sidecar or ambient waypoint, Linkerd, which balances gRPC per request out of the box), NGINX `grpc_pass`, Azure Application Gateway for Containers, or an Envoy-based gateway. Easiest at the platform level, costs a hop and some latency.
2. **Client-side load balancing**: point the client at a **headless Service** (`clusterIP: None`) so DNS returns all pod IPs, and enable the `round_robin` policy. The client keeps a subchannel per pod.
   ```python
   channel = grpc.insecure_channel(
       "dns:///rater-headless.pulse.svc.cluster.local:50051",
       options=[("grpc.lb_policy_name", "round_robin")],
   )
   ```
   Catch: gRPC re-resolves DNS mostly on connection failure, so new pods aren't discovered quickly. Pair it with (3).
3. **`MAX_CONNECTION_AGE` on the server** (`grpc.max_connection_age_ms`, plus a grace period): the server sends **GOAWAY** periodically, clients reconnect and re-resolve, and load spreads to new pods. This alone also mitigates the L4 case.
4. **Proxyless gRPC with xDS** (the client gets endpoints from a control plane): powerful, but heavy for most teams.

**Interviewer pushes on:** keep-alive pings. If the path has an idle timeout (Azure LB 4 min), configure `grpc.keepalive_time_ms` under it, and make sure server `keepalive_permit_without_calls` / min ping interval allows it, or the server answers with GOAWAY `too_many_pings`.
**Your story:** gRPC is on your resume. If you ran gRPC services on AKS/GKE, say how traffic was balanced (mesh, headless + round_robin, or honestly "one pod was hot and here's what we did").

### 56. strace, lsof, ss, tcpdump, perf: what does each tell you? Give a real debugging situation for each.
- **strace**: the **system calls** a process makes, with arguments, return values and timing. It answers "what is this process asking the kernel for, and what is it stuck on?" Example: a worker hangs with 0% CPU; `strace -fp PID` shows it sitting in `connect()` to an IP that turns out to be a stale DNS answer, or in `futex()` (lock/GIL wait), or `read()` on a socket with no timeout. `strace -c` gives a syscall summary (thousands of `stat()` calls from a misconfigured import path). Caveat: ptrace-based, **big overhead**, use briefly in prod; in K8s you need `SYS_PTRACE`, usually via `kubectl debug -it pod --image=... --target=app`.
- **lsof**: **open files and sockets per process** (everything is a file descriptor). Example: `OSError: [Errno 24] Too many open files` because an HTTP client is created per request and never closed: `lsof -p PID | wc -l` keeps climbing and most entries are sockets to the same API. Another classic: disk shows full but `du` disagrees, because a deleted log file is still held open: `lsof +L1`.
- **ss** (replaces netstat): **socket state from the kernel**: states, queues, timers, per-connection TCP info. Example: latency spikes; `ss -ltn` shows `Recv-Q` on the listening socket near the backlog size, meaning the accept queue is full and workers aren't accepting fast enough. `ss -tin` shows RTT, retransmits, cwnd per connection; `ss -s` shows TIME_WAIT buildup (Q53).
- **tcpdump**: the **actual packets on the wire**, the ground truth when apps and logs disagree. Example: proving who sends the RST in Q52, seeing a TLS handshake die after ClientHello (SNI/cipher mismatch), or DNS queries going out five times per lookup because of `ndots:5`. Capture to a file and open in Wireshark.
  ```bash
  tcpdump -i any -nn -s0 host 10.0.4.12 and port 5432 -w db.pcap
  tcpdump -i any -nn port 53
  ```
- **perf**: **CPU sampling profiler for user and kernel space** plus hardware counters. Example: a pod is CPU-throttled and py-spy shows nothing obvious; `perf top` reveals time in the kernel (softirq network processing, page faults, or `copy_user` from huge payload serialization). For Python, **3.12+ supports perf natively** (`python -X perf` or `PYTHONPERFSUPPORT=1`) so Python frames show up in perf flame graphs.
- Worth adding at staff level: **eBPF tools** (bcc/bpftrace: `tcpretrans`, `tcpconnect`, `opensnoop`, `execsnoop`, `biolatency`) give strace/tcpdump-like answers with near-zero overhead, which is what you use on a busy prod node. Order of use: metrics -> `ss`/`lsof` (cheap, read-only) -> `py-spy`/`perf` -> `strace`/`tcpdump` for a narrow window.

**Your story:** pick one real incident per tool if you can, even small ones (a leaked fd, a hung worker). Interviewers can tell "I have run this at 2 a.m." from "I know the man page", so don't claim tools you haven't used; say how you'd use them instead.

### 57. The Linux OOM killer: how does it pick a victim, and how does cgroup v2 memory accounting relate to Kubernetes memory limits?
**How it picks:** when the kernel can't satisfy an allocation even after reclaiming page cache and swapping, it invokes the OOM killer. It computes an **`oom_badness` score per process**, which is basically the process's memory footprint (RSS + swap + page tables) as a fraction of the available memory, then adds **`oom_score_adj`** (-1000 to +1000; -1000 means never kill). The highest score dies with SIGKILL. You can read `/proc/PID/oom_score` and `/proc/PID/oom_score_adj`. The evidence is in `dmesg`/kernel log: `Out of memory: Killed process ...` or `Memory cgroup out of memory`.
There are two scopes: **global OOM** (the whole node is out of memory) and **cgroup OOM** (a cgroup hit its own limit). The second one is what you see in Kubernetes almost every time.

**cgroup v2 and Kubernetes:**
- `resources.limits.memory` becomes the container cgroup's **`memory.max`**. Exceed it and the kernel OOM-kills inside that cgroup: the container exits with **137** and status **`OOMKilled`**. Since K8s 1.28 on cgroup v2, kubelet sets **`memory.oom.group=1`**, so the **whole container** is killed rather than one process (matters for gunicorn/Celery where a child worker used to die quietly while the master lived on; 1.32 added `singleProcessOOMKill` to opt out).
- `memory.current` counts **anon memory + page cache (file-backed) + kernel memory** (slab, socket buffers) charged to the cgroup. So writing big files or reading many blobs inflates usage, but page cache is reclaimable, which is why kubelet and `kubectl top` use **working set = usage - inactive_file**.
- `requests.memory` doesn't change the cgroup limit. It's used for **scheduling** and sets **QoS class**, which sets `oom_score_adj` for global OOM: **Guaranteed -997**, **BestEffort 1000**, **Burstable** in between (`1000 - 1000*request/node_capacity`, clamped). Under node memory pressure, BestEffort and over-request Burstable pods die first.
- Separate from the kernel OOM killer: **kubelet node-pressure eviction** (default hard threshold `memory.available<100Mi`) evicts pods before the node hits global OOM. Status `Evicted`, not `OOMKilled`. Different symptom, different fix.
- `memory.high` (throttle and reclaim before the hard limit) exists in cgroup v2; K8s uses it only with the MemoryQoS feature gate, which is still alpha.

**Practical advice:** for memory, set **request = limit** on critical services (memory isn't compressible like CPU; you can't throttle your way out). Python-specific: RSS rarely shrinks after spikes (pymalloc arenas, fragmentation), so a worker that parses one huge workbook stays big. Use `max-requests`/`max_tasks_per_child` recycling, stream large files instead of loading them, and size the limit from observed p99 working set plus headroom.
```bash
kubectl describe pod X | grep -A3 "Last State"      # Reason: OOMKilled, Exit Code: 137
cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.events
```
**Your story:** the ATS pipeline (100k resumes/day, Celery on AKS, ML models loaded in workers) or Cellular converting big rater workbooks are likely places you've seen OOMKilled pods. Be ready to say what was actually using the memory and what you changed (limits, worker concurrency, recycling, streaming).

### 58. What does a CDN actually do? Cache keys, TTL vs stale-while-revalidate, purging, and cases where putting a CDN in front makes things worse.
**What it does:** a network of edge PoPs close to users that (1) **caches** responses so the origin isn't hit, (2) **terminates TLS near the user** and keeps warm, reused connections back to the origin (a big latency win even for uncacheable requests), (3) does **request collapsing** (a thousand simultaneous misses for the same object become one origin fetch) and **origin shielding** (a mid-tier cache in front of origin), and (4) absorbs **DDoS** and hosts the **WAF**, bot rules and rate limits. Examples: Azure Front Door, CloudFront, Cloudflare, Akamai, Fastly.

**Cache key:** what makes two requests "the same object". Default is roughly scheme + host + path + query string. Get it wrong in two directions: too broad and users get each other's content (forgot to vary on `Accept-Language`, or on auth); too narrow and the hit ratio collapses (tracking params like `utm_*`, unordered query params, `Vary: User-Agent`, cookies in the key). Normalise: whitelist the query params that matter, strip cookies on static paths.

**TTL vs stale-while-revalidate:**
- `Cache-Control: max-age=N` (browser + CDN) and `s-maxage=N` (shared caches only); `CDN-Cache-Control` / `Surrogate-Control` target only the CDN. `private` / `no-store` keep personalised responses out of shared caches.
- Plain TTL: once it expires, the next request waits on the origin.
- **`stale-while-revalidate=N`** (RFC 5861): after expiry, serve the stale copy immediately and refresh in the background, so users never pay origin latency for popular objects. **`stale-if-error=N`**: keep serving stale if the origin is down, a cheap resilience win.
- Best practice for static assets: **content-hashed filenames** (`app.3f9a1c.js`) with `max-age=31536000, immutable`, so deploys never need a purge. Short TTL + SWR for HTML and semi-dynamic API responses.

**Purging:** by URL, by wildcard/prefix, or by **tag / surrogate key** (tag responses with `quote-123`, purge everything tagged when it changes). Propagation takes seconds to minutes depending on provider and isn't atomic across PoPs. A full purge followed by peak traffic is a **thundering herd on origin**, so use shielding and collapsing. Design so you rarely need purges (versioned URLs) instead of depending on them.

**When a CDN makes things worse:**
- **Personalised or authenticated responses cached by mistake**: one broker sees another broker's quote. Plus **web cache deception** (`/account/profile.css` gets cached because the path looks static) and **cache poisoning** via unkeyed headers (`X-Forwarded-Host` reflected into a cached page).
- **Low hit ratio, dynamic APIs**: an extra hop, extra cost and another component that can fail, for no caching benefit (still useful for TLS/WAF, but be honest about why it's there).
- **Long-lived or streaming connections**: SSE, WebSockets and long polls break on buffering and edge timeouts (Front Door and CloudFront default origin response timeouts are around 30-60s; Cloudflare about 100s). Your RLHF dashboard streamed model responses over SSE, which needs buffering disabled and timeouts raised, or bypassing the CDN.
- **Stale data after deploys** or on data that must be fresh (quote prices, policy status), plus harder debugging ("is it the edge or the origin?"; check `Age`, `X-Cache`, provider debug headers).
- **Origin still directly reachable**: attackers bypass the WAF. Lock origin to the CDN (Front Door Private Link / `X-Azure-FDID` header check, CloudFront OAC for S3).
- **Signed/expiring URLs** (Azure SAS links for Pulse policy documents) cached past their expiry, or the signature stripped from the cache key so one user's link serves everyone.

**Interviewer pushes on:** "How would you put Aurora/Pulse behind Front Door?" Cache the SPA's static assets aggressively with hashed names, mark all quote/policy APIs `private, no-store`, use the CDN for TLS, WAF and anycast routing only, serve documents through short-lived SAS URLs that are never cached, and lock the origin to Front Door.
