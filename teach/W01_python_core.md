# W01: Python Core and the Data Model

**Dates:** Mon 2026-10-19 → Sun 2026-10-25 · **PREP_TODO:** Week 1 · **Knowledge map:** `python_core` (developing → solid)

**Goal:** stop losing easy points. A 7–8-year Python engineer is expected to answer these instantly and precisely. Last time, shallow vs deep copy came out reversed, and that's exactly the kind of slip this week removes.

| Day | Mode | Plan |
| --- | --- | --- |
| Mon | 🎓 Teach | Warm-up, then concepts 1–6 |
| Tue | 🎓 Teach | Concepts 7–12 |
| Wed | 🔧 Lab | Gotcha snippets, LRU cache, retry decorator |
| Thu | ✍️ Recall | One-page cheat sheet from memory, then diff it against the answers |
| Fri | 🎤 Quiz | R2 A + R6 J, plus spaced review |
| Sat | 🤖 AI | A-01, LLM basics (see PREP_TODO) |
| Sun | 📋 Review | Weekly checklist, then the infographic |

## Sources

```pack
answers/ROUND_2_fundamentals_breadth_answers.md: 1-6, 8, 9, 14, 15
answers/ROUND_3_python_and_backend_advanced_answers.md: 12
answers/ROUND_6_J_modern_python_code_reading_answers.md: 85-89
```

## Warm-up diagnostic (Mon, 5 min)

Ask these quickly, without teaching. Use the answers to decide what to skip.

1. "What does `b = a` do when `a` is a list? Is anything copied?"
2. "Why is `def f(x=[])` a bug?"
3. "What's the difference between an iterable and an iterator?"
4. "Why do we use `functools.wraps`?"

---

## MONDAY

### 1. Names, objects, identity and mutability

**Teach.**
- In Python, variables are **names bound to objects**, not boxes holding values. Assignment never copies; it binds another name to the same object.
- Every object has an **identity** (`id()`), a **type**, and a **value**. `is` compares identity; `==` compares value (it calls `__eq__`).
- **Mutable** objects (list, dict, set, most user classes) can change in place. **Immutable** ones (int, float, str, tuple, frozenset, bytes) can't; "changing" them makes a new object.
- Function arguments are passed by **object reference** (sometimes called "call by sharing"). The function gets a new name for the same object. Mutating it inside the function is visible outside; rebinding the name isn't.

**Picture it.** Names are sticky notes; objects are the things they're stuck to. `b = a` sticks a second note on the same thing.

**Your anchor.** At Jio ATS, if a parsed resume dict was passed into several scoring functions and one of them did `resume["skills"].append(...)`, every later scorer would see it. Shared mutable state across a pipeline is a real bug class.

**Interning detail (interviewers love this).**
- CPython caches small ints **-5 to 256**, so `a = 256; b = 256; a is b` is `True`, while for 257 it's *usually* `False`.
- Inside one compiled unit (a single function or file), the compiler may reuse equal constants, so `257 is 257` can be `True` there.
- Some strings (identifier-like literals) are interned too.
- **Conclusion: never use `is` for value comparison.** Only use it for singletons: `None`, `True`/`False`, sentinels.

**Check.** "Explain why `x is None` is right but `x is 300` is wrong, and what pass-by-object-reference means for a function that does `items.append(1)` vs `items = [1]`."

**Traps.** "Python is pass-by-reference" (no; you can't rebind the caller's name). "Tuples are fully immutable" (a tuple holding a list can have that list mutated).

**Interview angle.** R2 Q6.

### 2. Shallow vs deep copy ⚠️ open miss

**Teach.**
- **Shallow copy** (`list(a)`, `a[:]`, `a.copy()`, `copy.copy(a)`) creates a **new outer container**, but the elements are the **same objects**.
- **Deep copy** (`copy.deepcopy`) recursively copies the elements too, using a memo dict to handle cycles. It's slower, and some objects (sockets, locks) can't be deep-copied.

```python
a = [[1, 2], [3]]
s = a[:]                 # new outer list, SAME inner lists
s[0].append(99)          # a is now [[1, 2, 99], [3]]   <- shared
s.append([4])            # a unchanged: outer lists are different
import copy
d = copy.deepcopy(a)
d[0].append(7)           # a unchanged
```

**Picture it.** A shallow copy photocopies a table of contents: the chapters are still the same physical pages.

**Your anchor.**
- Building a default config or template dict and handing out "copies" per request/tenant (Aurora/Pulse quote templates). A shallow copy means one tenant's nested override leaks to the others.
- `dict(DEFAULTS)` is shallow.

**Check.** "I do `new = old.copy()` on a dict of dicts, then `new['limits']['max'] = 5`. What happens to `old`? How do you fix it two ways?" (deepcopy, or rebuild the nested dict).

**Traps.** Thinking `copy()` is deep. Forgetting that `[[0]*3]*3` creates three references to the *same* inner list.

**Interview angle.** R2 Q4.

### 3. Built-in containers and their costs

**Teach.**
- **list:** a dynamic array. Index O(1); append amortized O(1) (it over-allocates); insert/pop at the front O(n); `x in list` O(n).
- **dict:** a hash table. Get/set/del/`in` average O(1). Insertion order has been guaranteed since 3.7. Since 3.6 it's a "compact dict": a dense entries array plus a sparse index table, which saves memory.
- **set:** a hash table without values. `in` is O(1); set algebra is fast.
- **tuple:** immutable, hashable if its contents are, slightly smaller. Use it for fixed records and dict keys.
- **collections:**
  - `deque`: O(1) at both ends, so use it for queues, not `list.pop(0)`
  - `defaultdict`, `Counter`, `OrderedDict` (`move_to_end` is handy for LRU)
  - `heapq`: a min-heap on a list; push/pop O(log n); good for top-k and schedulers
  - `bisect`: binary search on sorted lists

**Picture it.** A list is a numbered shelf; a dict is a coat check (you hand in a ticket = the hash, and get the coat straight back).

**Your anchor.** Jio recommender top-N: `heapq.nlargest(k, scores)` is O(n log k), vs sorting everything at O(n log n). Turing task claim queues.

**Check.** "When would you pick a tuple over a list for a *real* reason, not style?" (a hashable key, e.g. `(policy_id, version)` as a cache key; a fixed-shape record; signalling immutability). "Why is `list.pop(0)` in a loop a performance bug?"

**Traps.** "dict is O(1) always" (it's average; worst case O(n) with pathological collisions, and resizes cost O(n), amortized). "Sets are ordered" (they're not).

**Interview angle.** R2 Q2.

### 4. Hashing and equality: the contract

**Teach.**
- Hash-based containers require that **if `a == b` then `hash(a) == hash(b)`**, and that the hash doesn't change while the object is in the container.
- Mutable built-ins are unhashable for that reason.
- If you define `__eq__` on a class, Python sets `__hash__ = None`, so it becomes unhashable until you define `__hash__` too.
- `@dataclass` with `eq=True` (the default) does the same unless `frozen=True` (or `unsafe_hash=True`).

**Picture it.** The hash tells you which drawer to look in. If an object changes after you file it, you'll search the wrong drawer forever.

**Your anchor.** Using a Pydantic or dataclass model as a cache key or set member for deduplicating submissions. It needs to be frozen.

**Check.** "I put an object in a set, then mutate a field that's part of its hash. What happens on lookup?" (It's effectively lost: lookups go to the wrong bucket, or the equality check fails.)

**Traps.** Defining `__eq__` and being surprised the class can't go in a set. Using floats as keys (`0.1 + 0.2 != 0.3`).

### 5. Functions: defaults, closures and late binding

**Teach.**
- **Default arguments are evaluated once, at `def` time**, not per call. A mutable default (`x=[]`) is shared across calls. Fix: `x=None`, then `if x is None: x = []`.
- **Closures:** an inner function captures *variables* from the enclosing scope (cells), not values. Rebinding inside it needs `nonlocal`.
- **Late binding:** `[lambda: i for i in range(3)]` all return 2, because each lambda reads `i` when *called*. Fix: `lambda i=i: i` (a default binds early), or `functools.partial`.

**Picture it.** A closure holds the *address* of a variable, not a photograph of its value.

**Your anchor.** Registering per-endpoint handlers or retry callbacks in a loop (e.g. creating Celery or webhook handlers per provider). The classic late-binding bug.

**Check.** "Explain the bug in `handlers = [lambda: i for i in range(3)]` and give two fixes." (This is R6 J Q87a; it will come up Friday.)

**Traps.** Thinking the mutable-default bug is about lists specifically. Any mutable default is shared, including dicts, sets and objects.

**Interview angle.** R2 Q3, R6 J Q87.

### 6. Iterables, iterators and generators

**Teach.**
- **Iterable:** anything with `__iter__` that returns an iterator (lists, dicts, files).
- **Iterator:** has `__next__` and raises `StopIteration` when it's exhausted; its `__iter__` returns itself. **One-shot.**
- **Generator function:** any function containing `yield`. Calling it returns a generator object (an iterator) **without running the body**. Each `next()` runs to the next `yield`, then pauses with its local state frozen.
- **Generator expression** `(x for x in ...)`: lazy, constant memory.
- `yield from sub` delegates to a sub-generator.
- **Why use them:** stream huge data in constant memory, build pipelines, avoid building big lists.
- **When they're wrong:** you need `len()`, random access, multiple passes, or you'll consume the data twice (the second pass silently yields nothing).
- **itertools essentials:** `islice`, `chain`, `groupby` (it needs sorted input!), `batched` (3.12), `tee`.

**Picture it.** A list is a printed book; a generator is a storyteller who tells you the next page only when you ask, and can't go back.

**Your anchor.** The DataWeave crawler, or ingesting 100k resumes a day: streaming file lines or rows through parse → validate → enqueue with generators instead of loading whole files. `batched(rows, 500)` for bulk DB inserts.

**Check.** "What's the difference between an iterable and an iterator? Why does looping twice over a generator give nothing the second time?"

**Traps.** `groupby` on unsorted data. Passing a generator to two consumers. Returning a generator from a function that holds a DB cursor or file after the `with` block has closed it.

**Interview angle.** R2 Q5.

---

## TUESDAY

### 7. Exceptions done properly

**Teach.**
- **Hierarchy:** `BaseException` → `Exception` → everything you normally catch. `KeyboardInterrupt`, `SystemExit` and (since 3.8) `asyncio.CancelledError` inherit from `BaseException`, *not* `Exception`. That's why a bare `except Exception` doesn't swallow cancellation, and why bare `except:` is dangerous.
- `raise NewError(...) from err` chains the cause (`__cause__`); `from None` hides it.
- `try/except/else/finally`: `else` runs only when nothing was raised; `finally` always runs. A `return` inside `finally` **swallows** any in-flight exception (a famous bug).
- **3.11:** `ExceptionGroup` plus `except*`, for multiple concurrent failures (TaskGroup raises these; you'll see them in W3). `add_note()` adds context.
- **Production style:** catch narrowly, translate at boundaries (DB error → domain error → HTTP 409), never `except: pass`, and log once with context, at the boundary.

**Your anchor.** The error model question you got partial on (R3 Q24). Domain exceptions map to problem-details responses with a retryable flag. That's W4, but the mechanism starts here.

**Check.** "Why is `while True: try: return call_api() except Exception: pass` dangerous?" (R6 J Q87e: it hides bugs, spins with no backoff, and has no limit.) "What's the difference between `raise X from e` and just `raise X`?"

**Traps.** Catching `Exception` around everything. Re-raising with `raise e`, which adds the current line to the traceback; prefer a bare `raise`.

### 8. Context managers

**Teach.**
- `with obj as x:` calls `obj.__enter__()` (the return value goes to `x`), and guarantees `obj.__exit__(exc_type, exc, tb)` runs on any exit.
- If `__exit__` returns `True`, the exception is **suppressed**. Usually return `False`/`None`.
- `contextlib.contextmanager` turns a generator into one: the code before `yield` is enter, after it is exit, and you put the `yield` in `try/finally` for cleanup.
- Also: `ExitStack` (a dynamic number of resources), `suppress`, `closing`, `nullcontext`.

**Picture it.** A hotel room: check-in hands you the key; check-out happens even if you leave through the fire exit.

**Your anchor.** Request-scoped DB sessions in FastAPI (R3 Q25, which you covered). A `Depends` with `yield` is literally a context manager: begin, yield the session, then commit or rollback in `finally`.

**Check.** "Write (out loud) a context manager *without* contextlib that times a block and logs it, even when the block raises." (R2 Q8.)

**Traps.** Forgetting `try/finally` around the `yield` in `@contextmanager`, so cleanup doesn't run when there's an exception.

### 9. Decorators

**Teach.**
- Functions are objects, so `@dec` above `def f` means `f = dec(f)`.
- A decorator returns a wrapper that calls the original. **`functools.wraps`** copies `__name__`, `__doc__`, `__wrapped__` and so on. Without it, logs, FastAPI routing and introspection see "wrapper".
- **Decorators with arguments** have three layers: `@retry(times=3)` calls `retry(3)`, which returns the real decorator, which returns the wrapper.
- **Stacking:** the decorator closest to `def` is applied first. At call time, the outermost wrapper runs first.
- **Class decorators** and decorating methods (watch `self`). Async functions need an `async def` wrapper that awaits.

```python
def retry(times=3, base=0.2):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(times):
                try:
                    return fn(*args, **kwargs)
                except TransientError:
                    if attempt == times - 1:
                        raise
                    time.sleep(base * 2 ** attempt * random.random())  # full jitter
        return wrapper
    return deco
```

**Your anchor.** Retry and timing decorators on external API calls (Cellular rater APIs, Azure blob calls), and auth decorators in Flask-era code.

**Check.** "Walk me through what Python does, step by step, when it sees `@retry(times=3)` on a function." (R2 Q9.)

**Traps.** Forgetting `wraps`. Retrying non-idempotent operations. Sync wrappers around async functions (it returns a coroutine and never awaits it).

### 10. The data model: dunder methods

**Teach.** Dunders are how your objects plug into Python syntax.

| Dunder | What it does |
| --- | --- |
| `__repr__` | Unambiguous, for developers; ideally `eval`-able |
| `__str__` | For users |
| `__eq__`, `__lt__` (+ `functools.total_ordering`) | Comparisons |
| `__hash__` | Hashing; see concept 4 |
| `__len__` | `len()`; also used for truthiness (`__bool__` falls back to it) |
| `__getitem__` | Indexing, *and* iteration via the old sequence protocol |
| `__iter__` | Iteration |
| `__contains__` | `in` |
| `__call__` | Makes instances callable (stateful functions, class-based decorators) |
| `__enter__` / `__exit__` | Context managers |
| `__init__` vs `__new__` | `__new__` creates the instance, `__init__` initialises it; `__new__` matters for immutables and singletons |

Method types:
- plain method: gets `self`
- `@classmethod`: gets `cls`; used for alternative constructors like `Policy.from_row(row)`
- `@staticmethod`: gets nothing; a namespaced function

**Your anchor.** Cellular: a `Cell` or `Range` object implementing `__getitem__` and `__iter__` so generated code can do `sheet["B2:B10"]`. A `Money` type with `__add__` and `__eq__` over Decimal.

**Check.** "Which dunders have you actually implemented in production, and why?" (R2 Q15; have 3 real examples ready.) "classmethod vs staticmethod, with one real use each." (R2 Q14.)

### 11. Records: dataclass vs NamedTuple vs TypedDict vs Pydantic

**Teach.**

| | Validation | Mutability | Cost | Use for |
| --- | --- | --- | --- | --- |
| `@dataclass` | None (type hints aren't enforced) | Mutable (or `frozen=True`) | Cheap | Internal domain objects; `slots=True` saves memory |
| `NamedTuple` | None | Immutable | Cheap | Tuple-compatible records, unpacking, lightweight returns |
| `TypedDict` | None at runtime (static only) | It's just a dict | Free | Typing JSON-shaped dicts you don't control |
| Pydantic `BaseModel` | **Runtime validation and coercion** | Configurable | Higher (Rust core in v2, still real) | Trust boundaries: API input, config, **LLM structured output** |

- Use `field(default_factory=list)`, never `= []` (the same bug as concept 5; dataclasses actually raise an error on it).

**Your anchor.** Pydantic at FastAPI boundaries everywhere; dataclasses inside the Cellular-generated modules; Pydantic again for LLM extraction schemas (this Saturday's A-02 and next week's work).

**Check.** "When would you *not* use Pydantic for an internal object?" (Hot loops: validation cost. Inside the trust boundary, data is already validated.)

**Interview angle.** R3 Q12.

### 12. Modern-Python traps (code-reading prep for Friday)

**Teach.** These come up as "what's wrong with this code?" (R6 J Q86–89):
- **Mutating a dict while iterating** → `RuntimeError: dictionary changed size during iteration`. Iterate over `list(d)` or build a new dict.
- **Floats for money:** `0.1 + 0.2 != 0.3`. Use `Decimal` built from *strings*, `quantize` with an explicit rounding mode. Excel's ROUND is half-away-from-zero, which is `ROUND_HALF_UP` in Decimal terms, while Python's `round()` is banker's rounding (`ROUND_HALF_EVEN`). **Directly relevant to Cellular rater parity.**
- **Datetimes:**
  - Naive vs aware: `datetime.utcnow()` is deprecated (3.12) because it returns a *naive* value. Use `datetime.now(UTC)`.
  - Store UTC and convert at the edges, with `zoneinfo`.
  - Policy dates that start "at midnight local time" should be stored as a local date plus a timezone, not as a UTC instant.
- **Shared mutable module-level state** in a threaded server (a module-level DB session shared by every request).
- **`match`/`case`:** a good use is destructuring structured messages or ASTs (e.g. Cellular formula nodes). A misuse is using it as a glorified if/elif on plain values, or forgetting that a bare name *captures* rather than compares.

**Check.** The agent reads R6 J Q87 snippets (a) to (e) aloud, one at a time: "What's the bug?"

---

## Wednesday lab (60–75 min)

Put this in a scratch folder (or `scripts/python_core/` if you want to keep it; ask Claude to tidy it into the scripts style).

1. **Gotcha file:** write `gotchas.py` with one function per trap (mutable default, late binding, shallow copy of nested lists, `is` on 257 in the REPL vs a file, dict mutation during iteration, float money). Before running each one, **write your predicted output in a comment.** Then run it and score yourself.
2. **LRU cache by hand:** `OrderedDict` with `get` (`move_to_end`) and `put` (`popitem(last=False)` when over capacity). Then compare with `functools.lru_cache` and `cache_info()`.
3. **Retry decorator:** the version from concept 9, plus an `async` variant. Test it with a function that fails twice and then succeeds.
4. **Bonus:** a `Money` class over `Decimal` with `__add__`, `__eq__`, `__repr__` and `quantize`-on-create; prove `Money("0.1") + Money("0.2") == Money("0.3")`.

## Thursday cheat sheet: what your one-pager must contain

Write it from memory first, *then* check the answer files and fix it in a different colour.

- [ ] The names-and-objects model in one sentence, plus when `is` is correct
- [ ] Shallow vs deep copy with a nested example, the right way round
- [ ] The complexity table: list / dict / set / deque / heapq
- [ ] The hash/eq contract in one line
- [ ] Mutable default and late-binding bugs, with fixes
- [ ] Iterable vs iterator vs generator; when generators are wrong
- [ ] Exception hierarchy (where CancelledError sits), `raise from`, `return` in `finally`
- [ ] The context manager protocol plus the `@contextmanager` skeleton
- [ ] The three-layer decorator-with-args skeleton
- [ ] Six dunders you'd actually implement
- [ ] dataclass / NamedTuple / TypedDict / Pydantic: one line each
- [ ] Decimal rounding modes and Excel parity

## Friday quiz (interviewer mode, 30–40 min)

- **New:** R2 Q1–6, Q8, Q9, Q14, Q15 (pick 6); R6 J Q86 + Q87 (all five snippets) + Q89.
- **Spaced review from misses:** R2 Q4 (shallow/deep, must be right now), plus 1 more of the oldest open misses.
- **Grade:** log to `session_log.md`; update `python_core`; new misses go to `misses.md`; if R2 Q4 was correct, set its Hits to `1/2`.

## Infographic brief (Sunday, after your cheat sheet)

Title: **"Python Core in One Page"**. Panels:
1. Names → objects diagram (two sticky notes on one list); `is` vs `==`.
2. Shallow vs deep copy: box-and-arrow picture of the nested lists.
3. Complexity table: list / dict / set / deque / heap.
4. A "Bugs that bite" strip: mutable default, late binding, dict-mutation-while-iterating, float money, naive datetime. Each with its one-line fix.
5. The decorator-with-args 3-layer skeleton and the context manager skeleton side by side.
6. Records decision mini-table.

## Done when

- [ ] You explained shallow vs deep copy and generators vs iterators with no hesitation
- [ ] Friday quiz: no `weak`/`gap`; at most 2 `partial`
- [ ] The Wednesday lab predictions were at least 80% right, or the wrong ones are now in misses
