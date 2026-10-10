"""
08 - Production patterns: worker pool, retries + jitter, token bucket, graceful shutdown
=========================================================================================

Run:  python scripts/async/08_production_patterns.py      (Python 3.11+)

This file puts scripts 01-07 together into the shapes you'd actually whiteboard.

PATTERN 1 - Bounded worker pool over 10,000 URLs (Round 3 Q20 WHITEBOARD)
------------------------------------------------------------------------
Two ways to bound concurrency:
  a) Semaphore + gather: simple, but creates 10k coroutine objects up front
     (memory) and gather has the orphan-on-failure problem.
  b) N workers pulling from a Queue: constant memory, natural backpressure,
     easy per-worker retry/metrics. Preferred for big or unbounded inputs.
What a strong answer adds: per-request timeout, retries with jittered backoff only
for retryable errors (timeouts, 429, 5xx - not 4xx), a results/errors split,
progress metrics, and a shared HTTP client (one connection pool, not one per call).

PATTERN 2 - Retry with exponential backoff + FULL jitter (Round 3 Q27)
---------------------------------------------------------------------
  delay = random.uniform(0, min(cap, base * 2**attempt))
Without jitter every client retries at the same instants -> synchronized retry
waves that keep a recovering service down ("thundering herd"). Also cap total
attempts, respect Retry-After, and pair with a circuit breaker so you stop
retrying a service that is clearly down.

PATTERN 3 - Token bucket rate limiter (Round 3 Q26 - you were hazy on this one)
-------------------------------------------------------------------------------
Bucket holds up to `capacity` tokens and refills at `rate` tokens/sec. Each call
takes one token; if empty, wait. Allows BURSTS up to capacity while enforcing
the average rate - that's why APIs (Stripe, AWS, GitHub) use it.
  vs fixed window: bursts at window edges (2x limit across a boundary).
  vs sliding log: exact, but stores a timestamp per request (memory).
This version is per-process. Across pods, keep the bucket in Redis (Lua script
for atomic refill+take) or enforce at the gateway/edge (Envoy, API Gateway, APIM).

PATTERN 4 - Graceful shutdown (Round 3 Q29 + the K8s preStop gap)
-----------------------------------------------------------------
K8s sequence when a pod is deleted:
  1. Pod marked Terminating. IN PARALLEL: endpoints controller starts removing the
     pod from Services, and kubelet runs the preStop hook, then sends SIGTERM.
  2. Endpoint removal propagates to kube-proxy/ingress over ~a few seconds, so
     traffic can still ARRIVE after SIGTERM. That race is why preStop exists:
     `preStop: exec: sleep 5` delays SIGTERM until routing has caught up.
  3. App on SIGTERM: stop accepting new work, finish in-flight work with a
     deadline, close pools, exit 0.
  4. After terminationGracePeriodSeconds (default 30, which INCLUDES preStop
     time) -> SIGKILL.
Uvicorn already does step 3 for HTTP; you must do it yourself for background
workers/consumers - shown below.
"""

import asyncio
import random
import signal
import time

START = time.perf_counter()


def t() -> str:
    return f"[{time.perf_counter() - START:5.2f}s]"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


class RetryableError(Exception):
    """Timeouts, 429, 502/503/504 - worth retrying."""


class FatalError(Exception):
    """400/401/404/422 - retrying won't help."""


async def fake_fetch(url: str) -> str:
    """Simulated HTTP call: mostly fast, some slow, some flaky, a few fatal."""
    roll = random.random()
    await asyncio.sleep(random.uniform(0.001, 0.005))
    if roll < 0.05:
        raise RetryableError(f"503 from {url}")
    if roll < 0.06:
        raise FatalError(f"404 for {url}")
    if roll < 0.07:
        await asyncio.sleep(1)  # hangs -> will hit our per-request timeout
    return f"200 {url}"


# ---------------------------------------------------------------------------
# Retry with backoff + full jitter
# ---------------------------------------------------------------------------
async def with_retries(fn, *args, attempts: int = 4, base: float = 0.01, cap: float = 0.2,
                       timeout: float = 0.1):
    for attempt in range(attempts):
        try:
            async with asyncio.timeout(timeout):  # per-attempt timeout
                return await fn(*args)
        except FatalError:
            raise  # don't retry client errors
        except (RetryableError, TimeoutError):
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(random.uniform(0, min(cap, base * 2 ** attempt)))


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------
class TokenBucket:
    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate                # tokens added per second
        self.capacity = capacity        # max burst size
        self.tokens = float(capacity)   # start full
        self.updated = time.monotonic() # monotonic: immune to wall-clock jumps
        self.lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    async def acquire(self) -> None:
        async with self.lock:  # serialise waiters so they don't all wake and race
            self._refill()
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)  # exact wait for next token
                self._refill()
            self.tokens -= 1


async def demo_token_bucket() -> None:
    section("1. Token bucket: rate=10/s, capacity=5 -> burst of 5, then ~10/s")
    bucket = TokenBucket(rate=10, capacity=5)
    s = time.perf_counter()
    for i in range(12):
        await bucket.acquire()
        print(f"  request {i:2d} allowed at +{(time.perf_counter() - s) * 1000:6.0f} ms")
    print("=> first 5 immediate (burst), then one every ~100ms (steady rate)")


# ---------------------------------------------------------------------------
# Worker pool
# ---------------------------------------------------------------------------
async def crawl(urls: list[str], n_workers: int) -> tuple[dict, dict]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=n_workers * 2)  # bounded
    results: dict[str, str] = {}
    errors: dict[str, str] = {}

    async def worker() -> None:
        while True:
            url = await queue.get()
            try:
                results[url] = await with_retries(fake_fetch, url)
            except Exception as e:  # record and move on; one bad URL mustn't kill the pool
                errors[url] = f"{type(e).__name__}: {e}"
            finally:
                queue.task_done()

    async with asyncio.TaskGroup() as tg:
        workers = [tg.create_task(worker()) for _ in range(n_workers)]
        for url in urls:
            await queue.put(url)  # backpressure: producer waits when queue is full
        await queue.join()
        for w in workers:
            w.cancel()
    return results, errors


async def demo_worker_pool() -> None:
    n = 10_000
    section(f"2. Worker pool: {n:,} URLs, 200 workers, retries + per-request timeout")
    urls = [f"https://example.com/item/{i}" for i in range(n)]
    s = time.perf_counter()
    results, errors = await crawl(urls, n_workers=200)
    elapsed = time.perf_counter() - s
    print(f"ok={len(results):,}  failed={len(errors):,}  in {elapsed:.2f}s "
          f"({n / elapsed:,.0f} req/s)")
    kinds: dict[str, int] = {}
    for msg in errors.values():
        kinds[msg.split(":")[0]] = kinds.get(msg.split(":")[0], 0) + 1
    print(f"failure kinds after retries: {kinds}")
    print("=> FatalError is never retried; Retryable/Timeout only fail after 4 attempts")


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
async def demo_graceful_shutdown() -> None:
    section("3. Graceful shutdown of a background consumer")
    stop = asyncio.Event()
    in_flight: set[asyncio.Task] = set()

    loop = asyncio.get_running_loop()
    try:
        # Real SIGTERM/SIGINT hook (Linux/macOS - i.e. in your container).
        loop.add_signal_handler(signal.SIGTERM, stop.set)
        loop.add_signal_handler(signal.SIGINT, stop.set)
        print("signal handlers installed (POSIX)")
    except NotImplementedError:
        # Windows' event loop doesn't support add_signal_handler. Containers are
        # Linux, so this branch is only for running the demo locally.
        print("Windows: no add_signal_handler - simulating SIGTERM with a timer")
    loop.call_later(0.35, lambda: (print(f"{t()} >>> SIGTERM received"), stop.set()))

    async def process(msg_id: int) -> None:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        print(f"{t()}   finished message {msg_id}")

    async def consumer() -> None:
        msg_id = 0
        while not stop.is_set():  # 1. stop pulling new work once signalled
            msg_id += 1
            task = asyncio.create_task(process(msg_id))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
            await asyncio.sleep(0.05)  # poll interval
        print(f"{t()} consumer: stopped accepting, {len(in_flight)} in flight")

    await consumer()

    # 2. drain in-flight work with a deadline shorter than terminationGracePeriodSeconds
    if in_flight:
        done, pending = await asyncio.wait(in_flight, timeout=0.2)
        print(f"{t()} drained {len(done)}, {len(pending)} still running after deadline")
        # 3. whatever didn't finish gets cancelled (and should be safely redelivered:
        #    commit Kafka offsets / ack RabbitMQ only AFTER processing succeeds)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    # 4. close pools/clients here, then exit 0
    print(f"{t()} clean exit")


async def main() -> None:
    random.seed(7)
    await demo_token_bucket()
    await demo_worker_pool()
    await demo_graceful_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
