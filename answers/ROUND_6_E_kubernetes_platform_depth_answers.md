# Round 6 — Gap Fill & Staff Readiness: Answers, Section E (Kubernetes & Platform Depth)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. Original question numbers are kept. Each answer leads with the mechanism, then the practical design, then what an interviewer will push on. Where a **Your story:** note appears, fill it in from real work (Jio ATS on AKS, Jio recommender on GKE, Dataweave on Azure K8s, the Aventum Azure estate), not from my wording.

---

## E. KUBERNETES & PLATFORM DEPTH

### 39. What happens, component by component, when you run `kubectl apply` on a Deployment? (API server, etcd, controllers, scheduler, kubelet, container runtime, kube-proxy.)
The key idea: Kubernetes is a set of **independent control loops watching the API server**. Nobody "calls" the scheduler or the kubelet; each one notices a change in desired state and reacts.

1. **kubectl** reads the YAML, picks the API group/version (`apps/v1`), and sends a request to the API server. With client-side apply it computes a three-way merge using the `last-applied-configuration` annotation; with `--server-side` (the better default now) it sends the whole object and the server tracks field ownership via `managedFields`.
2. **API server** runs the request pipeline: **authentication** (client cert, OIDC token; on AKS usually Entra ID via kubelogin), **authorization** (RBAC: can this user `patch deployments` in this namespace?), **mutating admission** (webhooks and policies that inject defaults or sidecars), **schema validation**, **validating admission** (Pod Security, Gatekeeper/Kyverno, ValidatingAdmissionPolicy). Then it persists.
3. **etcd** stores the Deployment object. The write goes through Raft, so it's committed once a majority of etcd members ack it. The object's `resourceVersion` changes and a **watch event** is emitted to everyone watching Deployments.
4. **Deployment controller** (in kube-controller-manager) sees the new or changed spec, computes the pod-template hash, and creates or updates a **ReplicaSet**. On a template change it creates a new ReplicaSet and scales new up / old down according to `maxSurge` / `maxUnavailable`.
5. **ReplicaSet controller** sees desired replicas > current and creates **Pod** objects with no `nodeName`.
6. **kube-scheduler** watches for pods with empty `nodeName`. It **filters** nodes (resources requests fit, taints/tolerations, node affinity, volume zone constraints) and **scores** the survivors (spread, image locality, balanced allocation), then writes a **Binding** that sets `nodeName`.
7. **kubelet** on that node watches for pods bound to it. It calls the **container runtime via CRI** (containerd on AKS/EKS): create the pod sandbox, call the **CNI plugin** to set up the network namespace and assign a pod IP (Azure CNI Overlay / Cilium on AKS, VPC CNI on EKS), mount volumes via **CSI**, pull images, start init containers then app containers. It then runs startup/readiness/liveness probes and reports **pod status** back to the API server.
8. **EndpointSlice controller** sees the pod become Ready and adds its IP to the EndpointSlices of every Service whose selector matches.
9. **kube-proxy** (or Cilium's eBPF agent) on every node watches Services and EndpointSlices and programs iptables/nftables/IPVS rules or eBPF maps so the ClusterIP now load-balances to the new pod.

**What they push on:** "where does a Pending pod get stuck?" (scheduler: insufficient CPU, untolerated taint, PVC in another zone) vs "ContainerCreating" (kubelet: CNI out of IPs, image pull, volume attach). Also: the scheduler doesn't start containers, and readiness gates Service traffic, not the rollout alone. A strong answer mentions that everything is level-triggered: if a controller crashes, it relists and converges again.

### 40. Scheduling controls: node affinity, pod anti-affinity, taints and tolerations, topology spread constraints. Design the placement of a highly available service across 3 zones.
- **Node affinity**: "this pod wants (or requires) nodes with these labels", e.g. `agentpool=apps` or a GPU SKU. `requiredDuringSchedulingIgnoredDuringExecution` is hard, `preferred...` is soft. It's the pod choosing nodes.
- **Taints and tolerations**: the opposite direction, the node repels pods. A taint `sku=gpu:NoSchedule` keeps everything off the GPU pool unless the pod tolerates it. Tolerations **allow**, they don't **attract**; to dedicate a pool you need taint + toleration + node affinity together. `NoExecute` also evicts running pods (that's how node-not-ready eviction works).
- **Pod anti-affinity**: "don't put me where pods with label X already are", per `topologyKey` (hostname or zone). Hard anti-affinity on hostname caps you at one replica per node, and it's expensive for the scheduler at scale.
- **Topology spread constraints**: the modern tool for spreading. "Keep the count of matching pods per zone within `maxSkew` of each other." Much more flexible than anti-affinity because you can run 9 replicas across 3 zones evenly.

Design for a stateless HA API across 3 zones (AKS with zone-redundant node pools across zones 1/2/3, or EKS managed node groups spanning 3 AZs):
- Minimum **3 replicas**, ideally 6, so losing a zone leaves 2/3 capacity. Size HPA so the surviving two zones can absorb peak (run at ~60% utilisation per zone).
- Zone spread **hard** (`DoNotSchedule`), host spread **soft** (`ScheduleAnyway`) so a node shortage doesn't block scheduling.
- A **PDB** (question 41) so drains don't take out too many at once.
- Dedicated system node pool for CoreDNS/metrics etc., apps on a user pool via taint/affinity (AKS pattern: `CriticalAddonsOnly=true:NoSchedule` on the system pool).
- Zonal dependencies matter too: zone-redundant load balancer (AKS Standard LB is by default), ZRS storage, and remember **Azure Disks are zonal**, so a stateful pod with a PVC is pinned to the disk's zone. That's the classic "pod Pending after zone failure" trap. Use `WaitForFirstConsumer` binding mode.

```yaml
spec:
  replicas: 6
  template:
    metadata:
      labels: { app: quote-api }
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector: { matchLabels: { app: quote-api } }
          matchLabelKeys: [pod-template-hash]   # spread each rollout's ReplicaSet, not the mix
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector: { matchLabels: { app: quote-api } }
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - { key: agentpool, operator: In, values: [apps] }
```

**What they push on:** spread is only evaluated at scheduling time, so after a zone recovers the pods stay skewed until something reschedules them (the descheduler, or the next rollout). Also, the cluster autoscaler must be able to add nodes per zone: on AKS one zone-spanning pool is fine but some teams use one pool per zone so the autoscaler can target a specific zone (and set `balance-similar-node-groups` on EKS).

### 41. PodDisruptionBudgets: what do they protect against, and how can a badly configured PDB block a cluster upgrade or node drain?
A PDB limits **voluntary disruptions**: anything that goes through the **Eviction API**, i.e. `kubectl drain`, node pool upgrades, cluster autoscaler scale-down, Karpenter consolidation. It says "at least `minAvailable` pods (or at most `maxUnavailable`) of this selector must remain healthy". When an eviction would violate it, the API server returns **429 Too Many Requests** and the drainer retries.

It does **not** protect against involuntary disruptions: node crash, kernel panic, zone outage, OOM kills, or someone doing `kubectl delete pod` (delete bypasses eviction). A Deployment rollout also isn't governed by the PDB; `maxUnavailable` on the Deployment handles that.

How a bad PDB blocks upgrades:
- **`minAvailable` equal to replicas** (e.g. `minAvailable: 1` with 1 replica, or `maxUnavailable: 0`). Allowed disruptions is permanently 0, so the drain never succeeds. This is the number one cause of stuck AKS/EKS node pool upgrades.
- **Pods already unhealthy**: if 2 of 3 pods are CrashLooping, the budget is already used up, so even the broken pods can't be evicted. Fix in newer K8s: `unhealthyPodEvictionPolicy: AlwaysAllow` (GA since 1.31) lets not-Ready pods be evicted regardless.
- **Selector overlap**: two PDBs matching the same pods, eviction refuses entirely.
- **Not enough capacity**: the PDB is fine but the evicted pod can't reschedule (no surge node, anti-affinity, zonal PVC), so it never becomes Ready and the next eviction waits forever.

What the platforms do: AKS waits up to the node pool's **drain timeout** (default 30 min) and then fails the upgrade, or with `undrainableNodeBehavior: Cordon` it parks the stuck node and carries on. EKS managed node groups fail with `PodEvictionFailure` unless you force. Karpenter respects PDBs and just won't consolidate.

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: { name: quote-api }
spec:
  maxUnavailable: 1                    # prefer maxUnavailable: it scales with replicas
  unhealthyPodEvictionPolicy: AlwaysAllow
  selector: { matchLabels: { app: quote-api } }
```

**Rule of thumb:** every multi-replica service gets a PDB with `maxUnavailable: 1` (or 25%); single-replica workloads should not have a PDB that blocks, they should either get a second replica or accept the blip. Enforce this with admission policy (question 49).

### 42. Service types (ClusterIP, NodePort, LoadBalancer, headless): how does traffic actually reach a pod via kube-proxy (iptables/IPVS) or an eBPF data plane like Cilium?
- **ClusterIP**: a virtual IP that exists on no interface. It's only a rule in each node's data plane. Reachable inside the cluster.
- **NodePort**: ClusterIP plus a port (30000-32767) opened on **every node**; traffic to any node on that port gets forwarded to a backend pod, possibly on another node.
- **LoadBalancer**: NodePort plus a cloud LB provisioned by the cloud controller manager. On AKS that's a frontend on the Azure Standard Load Balancer (public or `service.beta.kubernetes.io/azure-load-balancer-internal: "true"`); on EKS the AWS Load Balancer Controller creates an NLB, ideally in **IP target mode** so it targets pod IPs directly and skips the NodePort hop.
- **Headless** (`clusterIP: None`): no VIP, no load balancing. DNS returns the **pod IPs** directly (and per-pod records for StatefulSets like `pg-0.pg.ns.svc`). Used for StatefulSets, client-side load balancing (gRPC), and discovery.

How a packet reaches the pod:
- **kube-proxy iptables mode**: for each Service there's a `KUBE-SERVICES` rule matching the ClusterIP:port, jumping to a `KUBE-SVC-*` chain that picks an endpoint with **random probability** rules, then a `KUBE-SEP-*` chain that **DNATs** to the pod IP. Conntrack remembers the translation so replies get un-NATed. Problems: rules are evaluated linearly, so with thousands of Services updates are slow and the per-packet cost grows; rule rewrites can take seconds.
- **IPVS mode**: kernel L4 load balancer with hash tables, O(1) lookup and real algorithms (rr, least-conn). Upstream is moving away from it; **nftables mode** (GA in 1.33) is the intended successor to iptables mode, with much faster incremental updates.
- **eBPF (Cilium)**: kube-proxy is replaced entirely. eBPF programs attached at the socket layer (`connect()`) translate the ClusterIP to a backend **before the packet is even built**, so pod-to-service traffic has no per-packet NAT at all; for external traffic, programs at tc/XDP do the load balancing using eBPF maps. Benefits: scales to large Service counts, fewer conntrack issues, supports Maglev consistent hashing and DSR, plus Hubble flow visibility and identity-based network policy. On AKS this is **Azure CNI Powered by Cilium**; on EKS you'd install Cilium yourself (often in chaining mode with VPC CNI).

`externalTrafficPolicy: Local` keeps traffic on the node that received it: it **preserves the client source IP** and avoids a second hop, at the cost of uneven balancing and the LB health-checking only nodes with local pods. `Cluster` (default) SNATs and may hop nodes.

**What they push on:** HTTP routing is not a Service concern; that's Ingress / **Gateway API**. Worth knowing that the community **ingress-nginx** controller was retired in early 2026, so new designs use Gateway API implementations (Envoy Gateway, Istio, Cilium, Application Gateway for Containers on AKS, AWS Load Balancer Controller on EKS).

### 43. Helm vs Kustomize: when do you use each? What are the pain points of Helm at scale?
**Helm** is a **package manager with templating**: Go templates + `values.yaml` render manifests, and it tracks **releases** (stored as Secrets in the namespace) with revision history and `helm rollback`. Use it to **distribute** software to people who shouldn't read your manifests: third-party charts (cert-manager, KEDA, ingress controllers), or an internal "golden chart" that every service team consumes with a small values file.

**Kustomize** is **template-free patching**: a plain-YAML `base` plus `overlays/dev|staging|prod` with strategic-merge or JSON patches, generated ConfigMaps/Secrets with hash suffixes, image tag overrides. Built into `kubectl apply -k`. Use it for **your own apps' per-environment differences**, where the manifests are yours and the deltas are small.

Very common combination: Helm for third-party charts, Kustomize overlays for your apps, or Kustomize's `helmCharts` / Argo CD rendering a chart and then patching it ("post-rendering").

Helm pain points at scale:
- **Templating YAML with text templates**: whitespace and `nindent` bugs, no type safety, charts grow into unreadable `if` forests to expose every field ("values.yaml becomes a worse copy of the K8s API").
- **Values sprawl and layering**: many `-f` files across environments, hard to know the effective config. You need `helm template` + diff in CI to see what's changing.
- **Release state can wedge**: a failed upgrade leaves the release in `pending-upgrade`/`failed`, and you have to roll back or fix it manually. Release Secrets also have size limits for huge charts.
- **CRD handling**: Helm installs CRDs from `crds/` once and never upgrades or deletes them, so CRD lifecycle needs a separate process.
- **Drift**: Helm 3 uses three-way merge against the last release, but it isn't a continuous reconciler; manual `kubectl edit` changes persist until the next upgrade. That's why GitOps sits on top.
- **Hooks** (pre-install jobs for migrations) are fragile and interact badly with GitOps tools.
- **Library chart versioning**: a shared golden chart bump has to roll out to 50 repos.

Current state: **Helm 4** (released late 2025) moved to server-side apply and improved some of this, but the templating model is the same. Interviewers like hearing that you'd keep charts thin, render and diff in CI, and pin chart versions.

**Your story:** you've likely consumed Helm charts on AKS for Jio ATS (Prometheus/Grafana stack, Redis, Celery workers). Be ready to say how you handled per-environment values and whether you diffed renders before deploying.

### 44. GitOps with Argo CD or Flux: how does reconciliation work, how are secrets handled, and how do you promote a release between environments?
**Reconciliation:** Git is the desired state; an **in-cluster agent pulls** and converges. Argo CD's repo server clones the repo (polls every ~3 min by default, or a webhook triggers it), renders the manifests (plain YAML, Kustomize, Helm), and the application controller **diffs rendered vs live** objects. The `Application` shows Synced/OutOfSync and Healthy/Degraded. With **auto-sync**, `prune` (delete objects removed from Git) and `selfHeal` (revert manual `kubectl edit`), drift is corrected automatically. Sync waves and hooks order things (CRDs before CRs, migrations before deploy). **ApplicationSet** templates many Applications across clusters/envs. Flux does the same with `GitRepository`/`OCIRepository` sources plus `Kustomization` and `HelmRelease` controllers.

Why pull-based: CI never holds cluster credentials, every change is a reviewed commit, and rollback is `git revert`.

**Secrets** (never plaintext in Git), options in order of my preference on Azure:
- **External Secrets Operator** or the **Secrets Store CSI Driver with the Azure Key Vault provider**: Git holds only a reference (`ExternalSecret` pointing at a Key Vault secret name), the operator fetches with **workload identity** (question 47). Rotation happens in Key Vault. AWS equivalent: Secrets Manager / Parameter Store.
- **SOPS** (encrypted with Azure Key Vault / AWS KMS keys, Flux decrypts natively, Argo via a plugin) or **Sealed Secrets** (encrypted with the controller's public key). Fine, but the secret still lives in Git and rotation means a commit.
- Best of all: no secret at all, using managed identity to reach Azure SQL, Storage, Service Bus directly.

**Promotion between environments:** CI builds the image once (immutable tag or digest), then promotion is **a Git change**, not a rebuild:
- Repo layout: `apps/quote-api/base` + `overlays/dev|staging|prod`, each overlay pinning an image digest. CI auto-commits the new digest to dev; promoting to staging/prod is a **PR that bumps the digest** in that overlay, gated by tests and approvals. Tools like Kargo, Argo CD Image Updater or Flux image automation can automate the bump.
- Prefer folders per environment over **branches per environment**; branch-per-env leads to merge drift and cherry-pick hell.
- Progressive delivery on top: Argo Rollouts / Flagger for canary with metric analysis.

**What they push on:** "someone hotfixes prod with kubectl at 2am, what happens?" (self-heal reverts it unless they also commit). And "how do you handle DB migrations in GitOps?" (a PreSync hook job or, better, backward-compatible expand/contract migrations run by the app's pipeline).

### 45. Operators and CRDs: what is the operator pattern, and when would you write an operator instead of shipping a Helm chart?
A **CRD** extends the API with your own resource type (`kind: PostgresCluster`), stored in etcd, with an OpenAPI schema, validation, and RBAC like any built-in. A **controller** watches those objects and runs a **reconcile loop**: read desired spec, observe actual state, take one step toward it, write `status`, requeue. An **operator** is CRD + controller that encodes **operational knowledge** a human SRE would otherwise do: provisioning, backup, failover, version upgrades, scaling, certificate rotation.

Mechanics that matter in interviews: reconcile must be **idempotent and level-triggered** (react to current state, not to the event), use **finalizers** to clean up external resources before deletion, **owner references** for garbage collection, `status.conditions` and `observedGeneration` for reporting, leader election so only one replica acts. Built with **kubebuilder / controller-runtime** in Go, or **kopf** in Python.

Helm vs operator:
- Helm is **install-time templating**: it renders YAML once per upgrade and walks away. Good when the app is stateless and day-2 is "just restart pods".
- An operator is **continuous day-2 automation**. Write (or adopt) one when the software has stateful lifecycle logic: ordered failover, backups, schema/version upgrades with steps, rebalancing, or when you want to offer a **platform API** to other teams ("create a `TenantEnvironment` and you get a namespace, quotas, a database, DNS and Key Vault access").

When not to: most of the time. Use existing operators (CloudNativePG, Strimzi for Kafka, cert-manager, KEDA, Azure Service Operator / Crossplane for cloud resources) rather than writing your own. A custom operator is a distributed system you now own, with upgrade and CRD versioning burden.

**Your story:** a natural pitch from the Aventum world: an operator or Crossplane composition that provisions a new broker/tenant environment for Pulse (namespace, config, storage container, identity) from one CR. Present it as "would", not "did", unless you built something like it.

### 46. Service mesh (Istio, Linkerd): which problems does it solve (mTLS, retries, traffic splitting, telemetry), what does it cost, and when is it not worth it?
A mesh moves cross-cutting network concerns out of application code into a **data plane** of proxies, configured by a **control plane**.

What it solves:
- **mTLS everywhere** with automatic cert issuance and rotation, plus identity-based authorization ("only `quote-api` may call `rater`"), using SPIFFE identities derived from ServiceAccounts. This is usually the real driver (zero-trust / compliance).
- **Traffic management**: retries, timeouts, circuit breaking / outlier detection, weighted traffic splitting for canaries, header-based routing, fault injection.
- **Uniform telemetry**: golden-signal metrics and traces for every hop, without instrumenting each service.

What it costs:
- **Latency and resources**: sidecar Envoy adds roughly a millisecond or two per hop at p99 and tens of MB of memory plus CPU per pod; at hundreds of pods that's real money.
- **Operational complexity**: another control plane to upgrade, CRDs (VirtualService, DestinationRule, AuthorizationPolicy), debugging through proxies ("is it the app or Envoy?"), sidecar startup/shutdown ordering issues for Jobs.
- **Retry storms**: mesh retries stacked on application retries multiply load (ties to metastable failure, question 28).

Modern options: **Istio ambient mode** (GA since late 2024) removes sidecars: a per-node **ztunnel** does L4 mTLS, and optional per-namespace **waypoint** proxies do L7, which cuts most of the per-pod cost. **Linkerd** is simpler and lighter (Rust micro-proxy). **Cilium** offers mutual auth and L7 policy in the CNI. AKS has a managed **Istio add-on**; on EKS it's self-managed Istio/Linkerd (AWS App Mesh is discontinued).

When not worth it: a handful of services, one team, mostly calling managed PaaS (Azure SQL, Service Bus, Blob) rather than each other. Then TLS at the ingress, network policies, workload identity and a good HTTP client library with timeouts/retries get you 80% for 5% of the cost. Adopt a mesh when you have many services, multiple teams, and a hard mTLS or traffic-shifting requirement.

### 47. Kubernetes RBAC: Role vs ClusterRole, ServiceAccounts, and how a pod gets a cloud identity (AKS workload identity / EKS IRSA) without any stored secret.
**RBAC basics:** permissions are purely additive (no deny rules). A **Role** grants verbs on resources **within one namespace**; a **ClusterRole** is cluster-scoped and is used either for cluster-wide resources (nodes, CRDs, namespaces) or as a reusable template. A **RoleBinding** grants a Role or ClusterRole **in one namespace**; a **ClusterRoleBinding** grants across all namespaces. Common pattern: one ClusterRole `app-deployer`, bound per namespace with RoleBindings. Subjects are users, groups (on AKS, Entra ID groups via AKS-managed Entra integration, ideally with local accounts disabled) and **ServiceAccounts**.

**ServiceAccounts** are identities for pods. Since 1.24 pods get a **projected, short-lived, audience-bound token** (auto-rotated by the kubelet), not a long-lived Secret. Good hygiene: one SA per workload, `automountServiceAccountToken: false` if the pod never talks to the API server, and never grant `*` verbs or `secrets` list to app SAs. Check with `kubectl auth can-i --as=system:serviceaccount:pulse:quote-api list secrets`.

**Cloud identity without a secret (OIDC federation):** the cluster acts as an **OIDC issuer** and signs SA tokens. The cloud's identity system is configured to trust tokens from that issuer for a specific subject.

AKS workload identity:
1. Enable `--enable-oidc-issuer --enable-workload-identity` on the cluster.
2. Create a **user-assigned managed identity**, give it Azure RBAC (e.g. `Key Vault Secrets User`, `Storage Blob Data Reader`).
3. Create a **federated identity credential** on that identity: issuer = cluster OIDC URL, subject = `system:serviceaccount:<ns>:<sa>`, audience `api://AzureADTokenExchange`.
4. Annotate the SA and label the pod. The workload identity **mutating webhook** injects `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_FEDERATED_TOKEN_FILE` and a projected token volume.
5. In Python, `DefaultAzureCredential()` (azure-identity) finds the token file and exchanges it with Entra ID for an access token. No secret anywhere.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: quote-api
  namespace: pulse
  annotations:
    azure.workload.identity/client-id: "<managed-identity-client-id>"
---
# in the Deployment pod template
metadata:
  labels:
    azure.workload.identity/use: "true"
spec:
  serviceAccountName: quote-api
```

EKS equivalents: **IRSA**, where the SA is annotated `eks.amazonaws.com/role-arn: arn:aws:iam::<acct>:role/quote-api` and the IAM role trust policy trusts the cluster's OIDC provider for that `sub`; the SDK calls `AssumeRoleWithWebIdentity`. Newer and simpler: **EKS Pod Identity**, an agent add-on plus a pod identity association API, so no per-cluster OIDC provider or trust-policy edits.

**What they push on:** the old AAD Pod Identity (NMI intercepting IMDS) is deprecated, so don't propose it. Also, the federated credential subject is exact, so renaming the namespace or SA silently breaks auth. And node-level managed identity (kubelet identity) shouldn't be what apps use, because every pod on the node would share it.

**Your story:** if the Azure Functions / blob / indexer work at Aventum used managed identity, say so; if any AKS workload used connection strings in Secrets, say how you'd migrate it to workload identity.

### 48. How do you upgrade a production AKS/EKS cluster with zero downtime? Control plane vs node pools, surge settings, version skew, and deprecated API removals.
**Order:** control plane first, then node pools, one minor version at a time (you can't skip minors on the control plane).

**Before:**
- Check **deprecated / removed APIs**: scan manifests and Helm releases with `pluto` or `kubent`, check the API server's `apiserver_requested_deprecated_apis` metric, AKS's deprecated-API usage detection (it can block the upgrade if removed APIs were called recently), or **EKS upgrade insights**. Classic removals: `extensions/v1beta1` Ingress, `policy/v1beta1` PDB and PodSecurityPolicy, `batch/v1beta1` CronJob, `flowcontrol` beta versions.
- Check add-on and operator compatibility (CNI, CSI, ingress/Gateway controller, cert-manager, KEDA, Istio).
- Upgrade **non-prod first** with the same add-ons; let it soak.
- Make sure workloads are drain-safe: 2+ replicas, sane PDBs (question 41), readiness probes, `preStop` sleep + `terminationGracePeriodSeconds` so in-flight requests finish while endpoints are removed.
- Check quota/IP space for surge nodes (Azure CNI without overlay burns subnet IPs per pod; this is a common surprise).

**Control plane:** managed and HA on both AKS (use the Standard tier for the uptime SLA) and EKS; the API server is briefly less available but running workloads aren't affected. **Version skew policy:** kubelets may be up to **three minor versions older** than the API server (never newer), so nodes can lag the control plane while you roll them; kubectl is supported within one minor either way.

**Node pools:** both AKS and EKS managed node groups do **surge upgrades**: add new nodes on the new version, cordon and drain old ones (respecting PDBs), delete them.
- AKS `maxSurge` (e.g. `33%` for production pools: faster, but needs quota), plus `drainTimeoutInMinutes`, `nodeSoakDurationInMinutes` (wait between nodes to catch problems) and `undrainableNodeBehavior`. Set surge explicitly rather than trusting defaults.
- Upgrade the **system pool** first, then user pools one at a time.
- Alternative with the strongest rollback story: **blue/green node pools**. Create a new pool on the new version, cordon the old pool, drain it gradually, keep it around for a few hours, delete. For really risky jumps, **blue/green clusters** behind Front Door / Traffic Manager / Route 53 weighted records.
- Node OS / image patching is separate: AKS node OS upgrade channel (`NodeImage` or `SecurityPatch`), EKS AMI updates or Bottlerocket. On EKS, Karpenter handles node replacement via drift detection.

**Automation:** AKS auto-upgrade channels (`patch`, `stable`, `rapid`) with **planned maintenance windows**; EKS has standard and extended support windows, so don't fall off the end of standard support (extended support costs extra). Pin to N-1 and upgrade on a cadence, roughly quarterly, because K8s minors are supported for about a year.

**After:** watch error rates and pod restarts, verify add-ons, then move the next environment.

**What they push on:** "the upgrade is stuck at 60%, what do you look at?" Answer: a PDB with zero allowed disruptions, a pod that can't reschedule (zonal PVC, anti-affinity, no capacity), or subnet IP exhaustion for surge nodes. `kubectl get pdb -A`, events on the stuck node, `az aks show` provisioning state.

### 49. Admission control: Pod Security Standards, OPA Gatekeeper, Kyverno. Which policies would you enforce on day one, and how do you roll them out without breaking existing workloads?
**Mechanism:** admission runs inside the API server after authn/authz: **mutating** admission first (inject defaults, sidecars, labels), then schema validation, then **validating** admission (allow or deny). Policy engines plug in as webhooks, or now in-process.
- **Pod Security Admission** (built in, replaced PodSecurityPolicy, which was removed in 1.25): applies the **Pod Security Standards** `privileged` / `baseline` / `restricted` per namespace via labels, in `enforce`, `audit` or `warn` mode. Coarse but free.
- **OPA Gatekeeper**: policies written in **Rego** as ConstraintTemplates + Constraints, with an audit controller reporting existing violations. On AKS, the **Azure Policy add-on** is managed Gatekeeper with built-in initiatives (plus AKS **Deployment Safeguards**).
- **Kyverno**: policies written as **YAML** (and CEL), easier for platform teams; validates, **mutates** (add default labels, set `imagePullPolicy`), **generates** resources (default NetworkPolicy per new namespace) and verifies image signatures.
- **ValidatingAdmissionPolicy** (GA in 1.30): native CEL rules evaluated in the API server, no webhook to run or fail. Good for simple rules; MutatingAdmissionPolicy is following it.

Day-one policies (roughly in this order):
1. **Pod Security `baseline` enforced** everywhere, `restricted` in warn/audit, moving to enforce for app namespaces: no privileged containers, no hostPath/hostNetwork/hostPID, run as non-root, drop capabilities, no privilege escalation, seccomp `RuntimeDefault`.
2. **Images only from trusted registries** (your ACR / ECR), no `:latest`, ideally signature verification (Notation / cosign).
3. **Resource requests and limits required** (at least memory limit and CPU request), otherwise noisy neighbours and broken autoscaling.
4. **Required labels** (owner, app, cost-centre) for ownership and FinOps.
5. **Probes required** on Deployments, and PDB sanity (no `maxUnavailable: 0`).
6. Block `LoadBalancer` services that are public unless annotated as approved; default-deny **NetworkPolicy** generated per namespace.

Rollout without breaking things:
- Start in **audit / warn / dry-run** mode cluster-wide (`pod-security.kubernetes.io/warn: restricted`, Gatekeeper `enforcementAction: dryrun`, Kyverno `validationFailureAction: Audit`). Collect a violation report per team.
- Fix or grant **time-boxed exceptions** (Kyverno `PolicyException`, Gatekeeper excluded namespaces) with an owner and expiry. Exclude `kube-system` and platform namespaces deliberately.
- Shift left: run the same policies in CI (`kyverno apply`, `conftest`, `gator`) so PRs fail before the cluster does.
- Enforce namespace by namespace, new namespaces first, with a published date.
- Webhook safety: run the policy engine HA, set `failurePolicy` thoughtfully (`Fail` for security-critical, but then a dead webhook blocks all deploys; scope with `namespaceSelector` so it never blocks `kube-system`), and keep timeouts short.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: pulse
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
```

**Your story:** GeoStorm was built "SOC2 from day 1" on AWS; that's a natural bridge to explain how you'd turn compliance requirements into admission policies on a cluster.

### 50. CoreDNS and `ndots:5`: why can DNS lookups from pods be slow or flaky, and how do you fix it?
Each pod's `/etc/resolv.conf` looks like:

```
nameserver 10.0.0.10
search pulse.svc.cluster.local svc.cluster.local cluster.local <node-search-domain>
options ndots:5
```

**`ndots:5`** means: if a name has **fewer than 5 dots**, try it with every search domain appended **before** trying it as-is. So resolving `myvault.vault.azure.net` (3 dots) from a pod queries `myvault.vault.azure.net.pulse.svc.cluster.local`, `...svc.cluster.local`, `...cluster.local`, `...<node domain>`, each returning NXDOMAIN, and only then the real name. glibc sends **A and AAAA** in parallel for each, so one external lookup can be **8-10 queries**. Multiply by every outbound call to Key Vault, Blob, Service Bus, OpenAI endpoints and CoreDNS gets hammered. The default exists so short names like `rater` and `rater.pulse` resolve within the cluster.

Why it becomes flaky, not just slow:
- **conntrack race on UDP**: glibc sends A and AAAA from the same socket at the same time; through kube-proxy DNAT the two packets can race in conntrack and one gets dropped, so the client waits the **5-second resolver timeout** and retries. The tell-tale symptom is latency spikes of exactly 5s (or 10s).
- **CoreDNS under-provisioned**: only 2 replicas for a big cluster, CPU-throttled, or OOM; plus upstream forwarding to Azure DNS (168.63.129.16) or the VPC resolver, which have **per-VM/ENI packet rate limits** (AWS's is 1024 packets/sec per ENI, a common EKS failure).
- **Alpine/musl** resolver handles search lists and TCP fallback differently from glibc, causing odd failures.
- Apps that don't cache DNS and open a new connection per request.

Fixes, cheapest first:
1. **Use FQDNs with a trailing dot** for external hosts in config (`myvault.vault.azure.net.`), which skips the search list entirely. Use full in-cluster names (`rater.pulse.svc.cluster.local`) for service calls.
2. **Lower `ndots`** per workload via `dnsConfig`, e.g. 2: short in-cluster names still work, external names with 2+ dots go straight out.
3. **NodeLocal DNSCache**: a caching DNS agent on every node on a link-local IP; pods query locally, it talks to CoreDNS over **TCP**, which avoids the conntrack race and offloads CoreDNS. On AKS the managed equivalent is **LocalDNS**; on EKS deploy the NodeLocal DNSCache add-on.
4. **Scale CoreDNS** properly: cluster-proportional autoscaler or HPA, spread across zones, check `coredns_dns_requests_total`, `coredns_cache_hits_total` and SERVFAIL rates. On AKS customise via the `coredns-custom` ConfigMap (bigger cache, conditional forwarders to on-prem/private DNS) rather than editing the managed one.
5. `options single-request-reopen` (glibc) as a band-aid for the race, use glibc-based images, and enable connection pooling / DNS caching in the app (keep-alive HTTP clients in `httpx`/`aiohttp` mostly make this go away).

```yaml
spec:
  dnsConfig:
    options:
      - name: ndots
        value: "2"
      - name: single-request-reopen
```

**What they push on:** "how would you prove DNS is the problem?" Answer: intermittent 5s latency in traces on connect, `kubectl exec` and time `getent hosts` in a loop, CoreDNS metrics and logs (`log` plugin temporarily), and conntrack `insert_failed` counters on nodes. A strong candidate connects it to real symptoms: "Key Vault / Blob calls occasionally take 5 seconds" is a classic AKS DNS ticket.

**Your story:** if you ever chased intermittent 5s latency or `Temporary failure in name resolution` errors on AKS (Jio ATS calling Blob storage, Celery workers hitting Redis/Mongo by external hostnames), tell it in that order: symptom, how you proved it was DNS, the fix, and the before/after numbers.
