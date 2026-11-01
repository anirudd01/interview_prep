# News feed at 100M requests a day — walk me through it

## Clarify first, then size it

Imagine the interviewer says: design the backend that serves a personalized news feed. A hundred million feed requests a day, each returning a ranked list of articles for that user. Walk me through it. The worst move is to start drawing boxes. A senior engineer starts with questions, because the answers change the design.

You ask how many users are logged in versus anonymous, because that drives cold start and feature storage. You ask about the latency target, and whether it's measured at the server or on the device. You ask how fresh breaking news must be. You ask whether the ML team owns the model. And you ask about traffic shape, flat or spiky, because that one question matters more than any other. Hold on to it.

The requirements: about twenty ranked articles per page, personalized by reading history, language and region, with infinite scroll. New articles appear within about five minutes normally, under one minute for breaking news. No repeats, no near-duplicates, like five outlets covering one event. You log impressions and clicks, because that's your training data and your A/B signal. You handle cold start for new users and new articles. Non-functionally: p50 of a hundred milliseconds, p95 of two hundred, errors under half a percent, availability of ninety-nine point nine percent. And the key attitude: a failed personalization should degrade to a generic feed, never return an error. A stale feed beats no feed. Everything is eventually consistent, since nobody is harmed if a click takes thirty seconds to influence the next feed.

Now the estimation, and there's one moment I want you to remember. A hundred million requests over eighty-six thousand four hundred seconds is about one point two thousand requests per second on average. But the peak is thirty-three thousand per second. Divide, and that's roughly twenty-eight times the average. Typical systems peak at two or three times. Twenty-eight is abnormal, and an abnormal number needs a cause. The cause is push notifications: one notification goes to millions of phones at once, and millions of people tap within seconds. So the traffic is scheduled, not random, and that changes the design. Autoscaling alone is too slow, so you pre-scale on the push calendar and shed load in tiers. Say that out loud and you've shown you read the numbers.

A few more figures. By Little's law, about sixty-six hundred requests are in flight at peak. The active corpus is up to half a million articles, and their embeddings come to about half a gigabyte, which fits in RAM on every retrieval replica. User features are about a hundred gigabytes, too big for one box, so a Redis cluster. Impression events run to two billion a day, around six hundred thousand per second at a push peak if you don't batch, so you batch on the client. Two numbers shape the design: the twenty-eight times spike, and the half gigabyte of embeddings, which lets retrieval live in memory.

## Retrieve, then rank

The core idea is two stages. Think of hiring. You can't interview half a million applicants, so a recruiter skims résumés and shortlists about five hundred, and then the hiring panel carefully scores that shortlist. Retrieval is the recruiter: cheap, fast, aiming for recall. Ranking is the panel: expensive, careful, aiming for precision. You cannot score half a million articles in forty milliseconds, so one big model over everything is off the table.

The feed service, a stateless FastAPI app on GKE, is the orchestrator. It owns the deadline and the fallbacks. If the client orchestrated, every failure would be user-visible. It fans out in parallel to four candidate sources, each with its own timeout. The personal source takes the user's vector and finds about three hundred nearest articles in an in-memory ANN index; that's the actual personalization, and without it everyone gets trending. The trending source returns about a hundred articles by click velocity for the user's region and language, giving freshness and rescuing cold start. The followed-topics source adds about a hundred from categories the user follows. The fresh or breaking source adds about fifty from the last few minutes, and it exists because a brand-new article has no clicks, so history-based similarity would find it late. If a source is slow, you drop it rather than wait.

Then the filter, which removes seen articles, wrong languages, blocked sources and near-duplicates. Repeats are the number one complaint in feeds. The seen set lives in Redis, per user, with a TTL of about three days, and a Bloom filter costs only a kilobyte or two per user, where a rare false "seen" is harmless.

Next, one batched lookup in the online feature store, a Redis cluster. About five hundred candidates, one MGET, user and article features together. Why fresh? Because ranking needs what you clicked two minutes ago, not what last night's batch job saw. Why batched? Five hundred separate GETs at half a millisecond each is two hundred fifty milliseconds, already over the entire budget.

The ranker scores those five hundred in one batch with a deliberately light model, gradient-boosted trees or a small two-tower network, because you're holding a CPU budget at forty thousand requests per second. In Python, CPU inference has to dodge the GIL, so use ONNX or another C-backed runtime, or process workers.

Last, the re-ranker applies business rules: no more than three per category in the top ten, a freshness boost, sponsored slots, editorial pins. The model optimizes clicks, and left alone it produces a clickbait monoculture. An experiment service hashes the user id into a bucket that picks the ranker version and rule weights, so every change ships behind an experiment.

## The three flows

Start with the read path, told as the story of the two hundred milliseconds. You spend about a hundred and ten of them and keep the rest as headroom. The request misses the CDN, since it's personalized, and hits the gateway for auth and rate limiting: five milliseconds. The feed service looks up the experiment bucket and checks for a cached ranked list; page two and beyond return right here. Otherwise it fans out to the four sources, each capped at forty milliseconds, costing thirty to forty in total because they run in parallel. Union and filter: three. One feature lookup: ten to fifteen. Ranking: thirty to forty. Re-ranking and caching the whole list for ten minutes under a feed request id: five. Respond with page one, and the client logs impressions with that same id. That id is gold: it joins every impression and click to the exact ranking that produced it. Without it you can't train or A/B test properly.

The new-article path is breaking news in under sixty seconds. The publisher's article enters ingestion, which validates it, clusters near-duplicates, classifies language and category, and embeds it. Then three writes: metadata to the article store, the vector to the ANN index, and the id to the fresh source. The next feed requests surface it before it has a single click. An article must be embedded before it can be recommended.

The feedback loop runs at two speeds. Online: the client batches events every thirty seconds or fifty events, and a 202 means accepted, asynchronous. The collector publishes to Pub/Sub or Kafka, decoupling the request path from analytics. A stream processor updates trending counters, seen sets, recent interests and article click rates in Redis within seconds, so if you clicked on cricket, your next feed has more cricket. Offline: events land in the data lake, daily jobs train the ranker and recompute user embeddings, and a batch job rebuilds the ANN index. New models go from the registry to shadow, scored but not served, then a five percent canary, then a ramp. Rollback is switching a version pointer.

## Two deep dives

First, holding p95 at two hundred milliseconds at thirty-three thousand requests per second. Budget it explicitly and enforce it with deadline propagation: the feed service passes the remaining budget into every call, with asyncio timeout-at. Fan out in parallel with per-source timeouts, because personalization is best effort; if ANN is slow, serve trending and topics. Batch everything. Use async I/O for the fan-out and push CPU work into a C-backed runtime or process pool, so you don't block the event loop or fight the GIL. Keep connection pools warm, because Postgres or Redis pool exhaustion shows up as a latency cliff, not as errors. For the spike: pre-scale on the push schedule, then shed in tiers. First drop the expensive personal ANN source, then serve the CDN trending feed. Never return a 5xx when a generic feed would do.

Second, precompute versus online. Fully precomputed feeds read fast but go stale, so breaking news is missed, and you'd store a hundred million users times twenty ids, much of it for people who never return. Fully online is fresh but expensive, and latency is hard to hold. The answer is a hybrid: precompute the slow parts, user embeddings daily, the ANN index, trending counters continuously, and do the cheap parts online, retrieval from memory and ranking five hundred candidates. Caching has layers: the CDN for the generic trending feed, the ranked-list cache for pagination stability where page two onward is nearly all hits, the Redis feature store, and the ANN index in process memory. The personalized first page is computed, not cached. And contrast this with a social feed: news is pull-and-rank on read, not fan-out-on-write, because there's no follower graph and relevance changes by the minute.

## Degrade, don't fail

Every failure answer is the same sentence. Ranker down? Fall back to candidate scores and alert. ANN unavailable? Trending, topics and fresh: less personal, not broken. Redis down? Default global features and still rank, or serve trending. Consumer lag? Trending goes stale and repeats creep in, so alert on lag. Push spike? Pre-scale, shed, fall back to the CDN. Bad model? Shadow and canary with guardrails, rollback by pointer. Client batches can be lost if the app is killed before flush, so persist on device and retry; collection is at-least-once and impressions dedupe on feed request id plus article id. The single point of failure you accept is one region behind a CDN fallback, since active-active isn't worth its cost here. At ten times traffic, Redis connections break first, then ranker CPU, then Postgres if metadata caching misses.

Know what you chose against: two-stage over one giant model; hybrid over nightly precompute, because freshness wins; in-memory ANN over a remote vector database, to save a network hop; Redis over Bigtable for latency, paying in memory; eventual consistency, because strong buys nothing; a light ranker over a deep one. For version one, with two engineers and six weeks, ship trending, topic candidates, simple category-affinity ranking, Redis, the CDN fallback and event logging. ANN, the ML ranker and experiments come later. The one thing you never defer is the feed request id and event logging, because without them you can never train or prove anything.

## Your turn: eight questions

Pause after each and answer out loud before I give the one-liner.

One: why is your peak twenty-eight times the average? Push notifications fire to millions at once, so pre-scale on the push calendar.

Two: how does a brand-new article get recommended with zero clicks? The fresh candidate source plus content embeddings, and an exploration boost for its first few impressions.

Three: a new user with no history? Regional trending from the CDN, onboarding topic picks, then streaming features personalize within a few clicks.

Four: how do you A/B test a ranker? Hash users into buckets, log feed request id and model version with every impression, compare CTR and dwell with latency and diversity guardrails.

Five: the ML team ships twice a day; how do you deploy safely? Registry, shadow, five percent canary with automatic guardrails, ramp; rollback is a pointer switch.

Six: what's cached, and at what hit ratio? CDN for the generic feed, ranked lists for pagination, features in Redis; the personalized first page is computed.

Seven: why not precompute every feed nightly? Stale for breaking news, wasted on users who don't return, and a hundred million times twenty writes a night.

Eight: what happens when Redis is down? Default features plus trending; the feed degrades and doesn't fail, protecting the half-percent error budget.

Finally, the part only you can answer, so these are open questions. From your Jio News work: your resume lists Pub/Sub, but in an earlier session you described Kafka. Which was it, and where? What drove your real peak, pushes, match days, elections, and did you pre-scale or rely on autoscaling? Where was your p95 measured? What was cached, at what hit ratio? Why did you split embedding and similarity into separate services? What exactly happened with the GIL and Postgres pooling, and what were the before and after numbers? What did the data science team own versus you? And how many pods at peak, what monthly cost, what did Redis and MongoDB each store? If you don't remember, estimate and say approximately.
