# Round 6 — Gap Fill & Staff Readiness: Answers, Section J (Modern Python & Code Reading)

Companion to `questions/ROUND_6_gap_fill_staff_readiness.txt`. Original question numbers are kept.
For the code-reading questions (86, 87), practise saying the bug out loud in one sentence before you look at the fix. That is what the interviewer is grading first. Where a question asks about your own experience, the **Your story:** note tells you what to fill in from real work.

---

## J. MODERN PYTHON & CODE READING

### 83. Python packaging in 2026: pyproject.toml, wheels vs sdists, lockfiles, uv vs pip vs Poetry. How do you guarantee reproducible builds in a Docker image?
**pyproject.toml** is the single standard config file (PEP 517/518/621). It declares the project metadata, dependencies (as ranges, e.g. `fastapi>=0.115`), optional groups, the **build backend** (hatchling, setuptools, uv_build, poetry-core), and tool config (ruff, mypy, pytest). `setup.py` and `requirements.txt` as the source of truth are legacy.

**Wheel vs sdist**: a **wheel** (`.whl`) is a pre-built archive. Installing it is basically unzip-and-copy, no code runs, and for C extensions it is compiled for a specific platform tag (e.g. `manylinux_2_28_x86_64`, `cp313`). An **sdist** is source; installing it runs the build backend on your machine, which needs compilers, can execute arbitrary code, and can produce different results on different machines. For reproducible, fast, safe builds you want wheels only (`uv sync --no-build` or `pip install --only-binary :all:`), and you treat "had to build from sdist" as a signal.

**Lockfiles**: pyproject says what you *allow*; the lockfile says exactly what you *got*: every package, transitive dependency, exact version, and artifact **hash**. Without one, two builds a week apart can resolve differently. Options: `uv.lock` (cross-platform, one file for all OS/Python combinations), `poetry.lock`, pip-tools' hashed `requirements.txt`, and **PEP 751 `pylock.toml`**, the standard lockfile format accepted in 2025 that tools are converging on (uv can export to it).

**uv vs pip vs Poetry**:
- **pip**: the baseline installer. No real project management or lockfile by itself (pip 25.1 added an experimental `pip lock`). Fine inside images if you feed it a hashed lock.
- **Poetry**: mature project manager with its own lockfile and resolver. Slower, historically had its own non-standard metadata (Poetry 2 now supports standard `[project]` tables).
- **uv** (Astral, Rust): resolver, installer, venv manager, Python version manager, and lockfile in one, 10-100x faster than pip, with a global cache. In 2026 it is the default choice for new projects. `uv add`, `uv lock`, `uv sync`, `uv run`.

**Reproducible Docker build**: commit `uv.lock`, pin the base image (ideally by digest) and the uv version, install from the lockfile without re-resolving, and separate dependency install from source copy so layer caching works.

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/   # pin an exact uv version (and digest) in real use
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# 1) dependencies only: this layer is cached until uv.lock / pyproject.toml change
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# 2) then the project itself
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim AS runtime
RUN useradd --create-home --uid 10001 app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER app
WORKDIR /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Points to say out loud: `--frozen` installs exactly what is in `uv.lock` and never updates it; `--locked` is stricter and *fails* if the lock is out of date with pyproject, which is what I'd run in CI. Both stages use the same base image so the venv's interpreter path matches. No compilers in the runtime image, non-root user, no dev dependencies. Dependabot/Renovate bumps the lock in a PR so upgrades are reviewed, not accidental. For full supply-chain rigour add an SBOM and image signing in the pipeline.

**Your story:** say what Aurora/Pulse and Cellular actually used (requirements.txt, Poetry, uv?) in ADO pipelines and Azure Functions packaging. If it was unpinned requirements, say so and explain what you'd change and why. That self-critique is staff-level signal.

### 84. Typing beyond basics: TypeVar, Generic, ParamSpec (for typing decorators), Literal, @overload, TypeIs/TypeGuard, Self. Where have you needed one in real code?
- **TypeVar / Generic**: a type parameter, so the output type is tied to the input type. `def first[T](xs: list[T]) -> T` (PEP 695 syntax, 3.12+), or the older `T = TypeVar("T")`. `class Repository[T]: def get(self, id: str) -> T` gives you `Repository[Quote]` and `Repository[Policy]` with one implementation. Bounds and constraints: `[T: BaseModel]`. TypeVar defaults (PEP 696) landed in 3.13.
- **ParamSpec**: captures a function's whole parameter list so a decorator can preserve the signature. Without it, decorated functions become `Callable[..., Any]` and mypy stops checking callers.
- **Literal**: a restricted set of values, `mode: Literal["quote", "bind", "renew"]`. Catches typos statically and pairs well with discriminated unions in Pydantic.
- **@overload**: multiple signatures for one function when the return type depends on the argument, e.g. `get(key) -> str | None` but `get(key, default: str) -> str`. Only the final non-decorated implementation runs.
- **TypeGuard vs TypeIs**: user-defined narrowing functions. `TypeGuard[X]` (3.10) narrows only in the `True` branch and doesn't need X to relate to the input type. **`TypeIs[X]`** (PEP 742, 3.13) narrows in *both* branches (in `else` it removes X) and requires X to be consistent with the input type. Prefer `TypeIs` for normal `is_foo(obj)` helpers.
- **Self** (3.11): return type for methods returning the instance, so fluent builders and `@classmethod` constructors type correctly in subclasses: `def with_broker(self, b: str) -> Self`.

A decorator typed with ParamSpec:

```python
import asyncio
import functools
from collections.abc import Awaitable, Callable

def retry[**P, R](times: int) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(times):
                try:
                    return await fn(*args, **kwargs)
                except ConnectionError:
                    if attempt == times - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)
            raise AssertionError("unreachable")
        return wrapper
    return decorator

@retry(times=3)
async def get_rate(quote_id: str, *, version: int) -> float: ...

# mypy now checks this call: get_rate(123) is an error, return type is float
```

Pre-3.12 spelling is `P = ParamSpec("P"); R = TypeVar("R")`. `Concatenate[Request, P]` is the tool when the decorator injects or removes a leading argument. One 3.14 note: annotations are now evaluated lazily (PEP 649/749), so `from __future__ import annotations` is mostly no longer needed for forward references.

**Your story:** good candidates from your work are a typed retry/timing decorator around Azure SDK calls, a generic repository over Cosmos/Postgres, or `Literal` for rater modes in Pulse. If you mostly used plain hints, say so and name the one you'd add first (ParamSpec on decorators is the most common real gap).

### 85. Structural pattern matching (`match`/`case`): give a good use case and a misuse.
`match` (3.10) is **structural**: it matches on the *shape* of data (sequence length, mapping keys, class attributes) and destructures in the same step. It is not a C-style switch.

**Good use**: dispatching on heterogeneous, nested messages, like webhook/event payloads, parsed commands, or AST-like trees, where you'd otherwise write nested `isinstance` + key checks.

```python
match event:
    case {"type": "quote.created", "quote": {"id": str(qid), "premium": premium}}:
        create_quote(qid, premium)
    case {"type": "policy.bound", "policy_id": str(pid), **rest} if rest.get("backdated"):
        flag_for_review(pid)
    case {"type": "policy.bound", "policy_id": str(pid)}:
        bind(pid)
    case {"type": str(t)}:
        log.warning("unhandled event %s", t)
    case _:
        raise ValueError("malformed event")
```

Mapping patterns ignore extra keys, `str(qid)` checks the type and binds, the guard (`if ...`) adds conditions, and order matters (first match wins). Class patterns work nicely with dataclasses: `case Point(x=0, y=y):`.

**Misuses**:
1. **The capture-name trap**: `case MAX_RETRIES:` does not compare against the constant, it *binds* any value to a new variable called `MAX_RETRIES`. Python rejects it with a SyntaxError if other cases follow ("makes remaining patterns unreachable"), but as the last case it silently matches everything. Use dotted names (`case Status.ACTIVE:`, `case config.LIMIT:`) or a guard.
2. **Using it as a fancy if/elif on simple values** where a dict lookup or plain `if` is clearer.
3. **Replacing polymorphism**: a big `match` on `type(obj)` across your own domain classes, which should be a method on each class. Matching is best on *data you don't own* (external payloads), not on your own object hierarchy.

### 86. What is wrong with this code?
```python
async def fetch_all(urls):
    tasks = []
    for url in urls:
        tasks.append(asyncio.create_task(fetch(url)))
    return [t.result() for t in tasks]
```
One-sentence answer: **it never awaits the tasks**, so `t.result()` is called on tasks that haven't finished (they haven't even started, since there was no `await` to yield to the event loop), and **`Task.result()` on an unfinished task raises `asyncio.InvalidStateError`**. It doesn't block and wait like `concurrent.futures.Future.result()` does.

Follow-on problems once that exception is raised:
- The remaining tasks are left running as **orphans**: nobody awaits them, their exceptions surface later as "Task exception was never retrieved" log noise, and they keep consuming connections.
- **No error policy**: even with awaiting fixed, one failed URL should either fail the whole call or be reported per-URL; the code doesn't decide.
- **Unbounded concurrency**: 10,000 URLs means 10,000 simultaneous connections, which will exhaust sockets/file descriptors or get you rate-limited.
- No timeout, and presumably `fetch` creates its own client per call instead of sharing one connection pool.

Fix 1, all-or-nothing with structured concurrency (3.11+):

```python
async def fetch_all(urls: list[str], limit: int = 20) -> list[bytes]:
    sem = asyncio.Semaphore(limit)

    async def bounded(url: str) -> bytes:
        async with sem:
            return await fetch(url)

    async with asyncio.timeout(30):
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(bounded(u)) for u in urls]
    return [t.result() for t in tasks]   # safe now: every task is done
```

If any fetch fails, the TaskGroup cancels the others and raises an `ExceptionGroup` (catch with `except*`). Calling `t.result()` after the `async with` block is correct because the group waits for all tasks.

Fix 2, partial failure acceptable:

```python
results = await asyncio.gather(*(bounded(u) for u in urls), return_exceptions=True)
ok = [r for r in results if not isinstance(r, BaseException)]
failed = [(u, r) for u, r in zip(urls, results) if isinstance(r, BaseException)]
```

`gather` keeps input order. Without `return_exceptions=True` it raises the first error but does **not** cancel the other tasks, which is why TaskGroup is the default for "all must succeed" (consistent with Round 3 Q16).

Extra points: share one `httpx.AsyncClient` (created in the FastAPI `lifespan`) so all requests reuse a connection pool; retry only idempotent requests on transient errors; for very large URL lists, use a fixed pool of N worker coroutines pulling from an `asyncio.Queue` instead of creating one task per URL up front.

### 87. Read each snippet aloud. What is the bug? (a) handlers = [lambda: i for i in range(3)]; print([h() for h in handlers]) (b) for key in config: if config[key] is None: del config[key] (c) premium = 0.1 + 0.2   # later: if premium == 0.3: apply_discount() (d) session = Session()   # module level, shared by every request in a threaded server (e) while True: try: return call_api() except Exception: pass
```python
# (a)
handlers = [lambda: i for i in range(3)]; print([h() for h in handlers])
# (b)
for key in config:
    if config[key] is None: del config[key]
# (c)
premium = 0.1 + 0.2   # later: if premium == 0.3: apply_discount()
# (d)
session = Session()   # module level, shared by every request in a threaded server
# (e)
while True:
    try: return call_api()
    except Exception: pass
```

**(a) Late-binding closure.** Prints `[2, 2, 2]`, not `[0, 1, 2]`. Each lambda captures the *variable* `i`, not its value, and looks it up when called; by then the comprehension has finished and `i` is 2. Fix: bind at definition time with a default argument, `lambda i=i: i`, or `functools.partial(f, i)`. Same bug shows up when registering callbacks or creating tasks in a loop.

**(b) Mutating a dict while iterating it.** Deleting a key changes the dict's size, and the next iteration step raises **`RuntimeError: dictionary changed size during iteration`**. Fix: iterate over a snapshot, `for key in list(config):`, or build a new dict, `config = {k: v for k, v in config.items() if v is not None}` (better if nothing else holds a reference to the old dict; otherwise mutate via the snapshot loop).

**(c) Float equality.** `0.1 + 0.2` is `0.30000000000000004` in IEEE-754 binary floating point, so `premium == 0.3` is `False` and the discount silently never applies. Fix for money: `Decimal("0.1") + Decimal("0.2") == Decimal("0.3")` is `True` (construct from strings, see Q89). For genuinely float-valued quantities (scores, geo coordinates), compare with a tolerance: `math.isclose(a, b, rel_tol=1e-9, abs_tol=...)`. Never `==` on computed floats.

**(d) Shared mutable client state across threads.** `requests.Session` is not documented as thread-safe. The connection pool underneath (urllib3) is fine to share, but the session also holds **mutable per-session state**: the cookie jar, default headers, auth. In a threaded server, a `Set-Cookie` from one user's upstream response gets sent on another user's request, and code that does `session.headers["Authorization"] = token` per request leaks one user's token to concurrent requests. That's a data-isolation bug, not just a race. Also `requests` has **no default timeout**, so one hung upstream ties up a worker thread forever.
Fix: keep the shared session stateless (set only static config at startup, never mutate it per request, pass per-request auth/headers as call arguments, disable or ignore cookies), or use one session per thread via `threading.local()`. Always pass `timeout=`. In an async FastAPI service, use a single `httpx.AsyncClient` created in `lifespan` and closed on shutdown, again with per-request headers passed as arguments.

**(e) Unbounded, silent retry loop.** Several bugs:
- **No limit**: if the API is down for an hour, this spins for an hour; the caller never gets an error.
- **No backoff**: it retries immediately in a tight loop, burning CPU and hammering a struggling dependency (a self-inflicted retry storm when every instance does it).
- **Swallows everything**: `except Exception` also catches non-transient errors, e.g. a `TypeError` from a bug in your code, a 401 or 400 that will never succeed, a JSON decode error. Those should fail fast.
- **No logging**: the failures are invisible.
- Be precise on what it does *not* catch: `KeyboardInterrupt`, `SystemExit`, and `asyncio.CancelledError` (since 3.8) subclass `BaseException`, not `Exception`, so Ctrl+C, shutdown, and task cancellation still get through. A bare `except:` would catch those too, which is worse.

Fix: bounded retries, exponential backoff with jitter, retry only transient errors, log, re-raise at the end.

```python
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

@retry(
    retry=retry_if_exception_type((httpx.TransportError, UpstreamUnavailable)),  # 5xx/429 mapped to this
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=0.5, max=10),
    reraise=True,
)
def call_api_with_retry():
    return call_api()
```

Plus: only retry idempotent operations (or use an idempotency key), honour `Retry-After` on 429, and consider a circuit breaker so you stop calling a dependency that is clearly down.

### 88. Dates and timezones: naive vs aware datetimes, why `datetime.utcnow()` is deprecated, DST transitions, and how you store and compare policy effective dates that start at midnight local time in different countries.
**Naive vs aware**: a **naive** datetime has no `tzinfo`, so it's just a wall-clock reading with no defined instant. An **aware** datetime has a `tzinfo` and represents an exact point in time. Comparing them: `==` between naive and aware returns `False`, and `<`/`>` raises `TypeError`. Mixing them is a common source of bugs.

**Why `utcnow()` is deprecated (3.12)**: it returns a **naive** datetime whose value happens to be UTC. Python treats naive datetimes as *local time* in methods like `.timestamp()` and `.astimezone()`, so on a server not set to UTC you get silently shifted values. Same for `utcfromtimestamp()`. Use `datetime.now(UTC)` (`from datetime import UTC`, 3.11+) or `datetime.now(timezone.utc)`, which are aware.

**DST transitions**:
- **Spring forward**: some local times don't exist (e.g. 02:30 on the change day in Europe/London). `zoneinfo` won't raise; it gives you a datetime with some offset, so you need to detect it if it matters.
- **Fall back**: some local times happen twice. The `fold` attribute (PEP 495) picks which: `fold=0` is the first occurrence, `fold=1` the second.
- **Arithmetic trap**: subtracting or adding to aware datetimes with the *same* tzinfo is wall-clock arithmetic and ignores offset changes. `local + timedelta(hours=24)` across a DST change is not "24 real hours later". For durations, convert to UTC first.
- Use **`zoneinfo`** (stdlib, 3.9+) with **IANA names** (`Europe/London`, `Asia/Kolkata`, `America/New_York`), never fixed offsets like `+05:30` or abbreviations like `EST`, since offsets change with DST and law. Add the `tzdata` package so it works on Windows and minimal container images. `pytz` is legacy.

**Policy effective dates at local midnight**: the business fact is "the policy starts on 2026-11-01 in the insured's (or the contract's governing) jurisdiction". So store the **intent**, not just a converted instant:
- `effective_date` (DATE, e.g. `2026-11-01`)
- `effective_tz` (TEXT, IANA name, e.g. `Europe/London`)
- `effective_at` (TIMESTAMPTZ, the computed UTC instant), for querying and comparing across countries

```python
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

def effective_instant(d: date, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    local = datetime.combine(d, time(0, 0), tzinfo=tz)
    instant = local.astimezone(UTC)
    # midnight can be skipped on a DST day in some zones; detect it via round-trip
    if instant.astimezone(tz).replace(tzinfo=None) != local.replace(tzinfo=None):
        raise ValueError(f"{d} 00:00 does not exist in {tz_name}")  # or apply a business rule, e.g. first valid instant
    return instant

effective_instant(date(2026, 11, 1), "Europe/London")    # 2026-11-01 00:00:00+00:00
effective_instant(date(2026, 11, 1), "Asia/Kolkata")     # 2026-10-31 18:30:00+00:00
```

Comparisons ("is this policy in force at the moment of this claim?") use the UTC instants: `effective_at <= event_at < expiry_at`. Note that Postgres `TIMESTAMPTZ` stores only the UTC instant, not the zone, which is exactly why you keep `effective_tz` separately. Keeping the local date + zone as the source of truth also means that if a government changes its DST rules before a future policy starts, you can recompute `effective_at` with updated tzdata. Midnight isn't always safe: Brazil used to start DST at 00:00, so local midnight didn't exist that day. Also decide explicitly whether expiry is "end of day local" (i.e. next day's 00:00 local, exclusive) and use half-open intervals to avoid off-by-one-second gaps.

**Your story:** Aventum is a Lloyd's/London market business with international risks, so tie this to how Pulse stored inception/expiry dates. If they were naive dates or server-local datetimes, say what you'd change.

### 89. Money in Python: why float is wrong, `Decimal` contexts, rounding modes (ROUND_HALF_UP vs ROUND_HALF_EVEN), `quantize`, and how this connects to matching Excel's ROUND.
**Why float is wrong**: floats are binary fractions, so most decimal values like 0.1 can't be represented exactly. Errors are tiny per operation but accumulate across rating steps and show up as wrong comparisons and off-by-a-penny totals (Q87c). Money needs exact decimal arithmetic.

**`Decimal`**: exact base-10 arithmetic. Always construct from **strings or ints**: `Decimal("0.1")` is exact, but `Decimal(0.1)` faithfully copies the float error (`0.1000000000000000055511151231257827...`). For floats coming from Excel/JSON, go through the string: `Decimal(str(x))` (shortest repr, which round-trips the float).

**Contexts**: a `Context` sets **precision** (significant digits, default 28, not decimal places), the default **rounding** mode, and **traps** (which conditions raise, e.g. `InvalidOperation`, `DivisionByZero`; you can enable `Inexact` or `FloatOperation` to catch accidental float mixing). `decimal.getcontext()` is per-thread (and per-asyncio-task, since it is backed by contextvars). Use `with decimal.localcontext() as ctx:` to change it locally rather than mutating the global one. Precision governs intermediate results; it doesn't round to pennies for you.

**`quantize`**: rounds to a fixed exponent, which is how you round to 2 decimal places:

```python
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN

PENNY = Decimal("0.01")
Decimal("2.675").quantize(PENNY, rounding=ROUND_HALF_UP)    # Decimal('2.68')
Decimal("2.665").quantize(PENNY, rounding=ROUND_HALF_EVEN)  # Decimal('2.66')
Decimal("-2.5").quantize(Decimal("1"), rounding=ROUND_HALF_UP)  # Decimal('-3')  (away from zero)
```

**Rounding modes**:
- **ROUND_HALF_UP**: ties go **away from zero** (2.5 → 3, -2.5 → -3). This is what most people expect and what **Excel's `ROUND`** does.
- **ROUND_HALF_EVEN** ("banker's rounding"): ties go to the nearest even digit (2.5 → 2, 3.5 → 4). Statistically unbiased over many sums, so it's used in accounting aggregation and is the IEEE-754 default. It's also **Decimal's default** context rounding.
- Python's built-in **`round()`** is banker's rounding too: `round(2.5) == 2`, `round(0.5) == 0`. On floats it also suffers representation error: `round(2.675, 2)` gives `2.67` because the float is actually 2.67499999.... So `round()` is never the tool for matching Excel.
- Excel's `ROUNDUP`/`ROUNDDOWN` map to `ROUND_UP`/`ROUND_DOWN` (away from / toward zero), not ceiling/floor.

**Matching Excel**: Excel computes in IEEE doubles but its `ROUND` behaves like decimal half-away-from-zero on the displayed value (Excel `ROUND(2.675, 2)` = 2.68). To reproduce a rater workbook: carry values as `Decimal` (converting any float inputs via `str`), apply `quantize(..., ROUND_HALF_UP)` at **exactly the same steps where the workbook calls ROUND**, and nowhere else. Rounding per line item vs on the total gives different answers, so the rounding points are business rules and must match the sheet. Even then, Excel's intermediate results are floats, so in rare edge cases (long chains of division, values near a .5 boundary) Decimal can disagree with Excel in the last digit. The honest engineering answer is **golden testing**: run a large set of inputs through the real workbook and the Python module and diff the outputs to the penny.

Storage: Postgres `NUMERIC(p, s)` (never `float8`/`real`) or integer minor units, serialise as strings in JSON, and keep the currency code next to the amount.

**Your story:** this is Cellular. Be ready to say how the generated Python modules handled Excel's ROUND (Decimal + ROUND_HALF_UP, or floats?), how you validated parity with the workbooks, and any penny-difference bug you hit. If parity was checked by a test harness against the original sheets, that's a strong answer; quote how many test cases.

### 90. pandas vs Polars vs DuckDB: memory model, performance, and when you would reach for each inside a backend service or a data job.
**pandas**: eager, in-memory DataFrame, traditionally NumPy-backed (optional Arrow-backed dtypes since 2.0; pandas 3.x makes Copy-on-Write the default, which removes the `SettingWithCopyWarning` class of bugs). Most operations are single-threaded. Rule of thumb: you need several times the data size in RAM because intermediate results get materialised and copied. Biggest ecosystem: every library accepts a pandas DataFrame, and the Excel IO (`read_excel` via openpyxl) is mature.

**Polars**: Rust, built on **Apache Arrow** columnar memory, **multi-threaded** by default, and releases the GIL. The **lazy API** (`pl.scan_parquet(...).filter(...).group_by(...).collect()`) builds a query plan and optimises it: predicate and projection pushdown (read only needed columns/rows), common subexpression elimination. Its streaming engine can process data larger than RAM in batches. Usually several times to 10x+ faster than pandas on group-bys/joins, with lower memory, plus a stricter, more consistent expression API (no index).

**DuckDB**: an **in-process analytical SQL database** (think "SQLite for analytics"): columnar, vectorised execution, multi-threaded, and it **spills to disk**, so it handles larger-than-memory joins and aggregations. It queries Parquet/CSV/JSON files directly (including on S3/Azure Blob via extensions) and can query pandas/Polars/Arrow objects in place with near-zero copy. Great when the transformation is naturally SQL.

**When I reach for each**:
- **Inside a backend request path**: ideally none, for large data. A web worker should not load a 2 GB frame per request; push aggregation to Postgres or precompute. For small in-request transforms, Polars is the better fit (fast, GIL-released, so it doesn't block other threads; for async services still run it in a thread pool so it doesn't block the event loop). Watch per-worker memory multiplied by worker count and pod limits.
- **DuckDB in a service**: ad-hoc analytics or reporting endpoints over Parquet in blob storage without standing up a warehouse, or as an embedded engine for an internal dashboard.
- **pandas**: when the ecosystem requires it (data scientists' code, scikit-learn, Excel-heavy IO, plotting), small data, or notebooks. Fine, and the team already knows it.
- **Data jobs (batch ETL)**: Polars lazy or DuckDB for single-node jobs up to hundreds of GB; both comfortably replace a lot of what people used to spin up Spark for. Reach for Spark/Databricks (or a warehouse) when the data is truly distributed-scale or you need the platform's governance and scheduling.
- They interoperate through Arrow, so the pragmatic answer is often mixed: DuckDB to filter/join Parquet, hand an Arrow table to Polars or pandas for the last step.

**Your story:** anchors are the Dataweave data-ingestion pipelines (where you cut manual effort by 60%), the Jio ATS batch processing of 100k resumes/day, and the Cellular/Pulse rater data that comes from Excel. Say what you used (likely pandas) and, if you'd rebuild it today, where Polars or DuckDB would have cut memory or runtime, with a rough number if you have one.
