# W02: Python Internals and Modern Python

**Dates:** Mon 2026-10-26 → Sun 2026-11-01 · **PREP_TODO:** Week 2 · **Knowledge map:** `python_internals` (weak → developing/solid)

**Goal:** this is your weakest Python area: three straight `gap`s on R3 Q1–3. At Staff level, interviewers use internals to tell "uses Python" apart from "understands Python". You don't need to know CPython source; you need to explain the **mechanisms** cleanly and say when they matter in a service.

| Day | Mode | Plan |
| --- | --- | --- |
| Mon | 🎓 Teach | Warm-up, then concepts 1–6 (runtime, memory, GIL, attribute lookup) |
| Tue | 🎓 Teach | Concepts 7–12 (descriptors, metaclasses, imports, typing, tooling, profiling) |
| Wed | 🔧 Lab | dis, a GC cycle, a validating descriptor, a profiling exercise |
| Thu | ✍️ Recall | Cheat sheet from memory |
| Fri | 🎤 Quiz | R3 A + R3 K + 3 open misses (Q1, Q2, Q3 from 2026-10-06) |
| Sat | 🤖 AI | A-02, structured outputs |
| Sun | 📋 Review | Checklist, then the infographic |

## Sources

```pack
answers/ROUND_2_fundamentals_breadth_answers.md: 7, 10
answers/ROUND_3_python_and_backend_advanced_answers.md: 1-11, 13
answers/ROUND_6_J_modern_python_code_reading_answers.md: 83, 84
```

## Warm-up diagnostic (Mon, 5 min)

1. "What actually runs when you execute a `.py` file? Is Python compiled or interpreted?"
2. "When does the GIL get released?" (open miss R2 Q1)
3. "What is `self.x` looking through when you access it?"
4. "Have you ever had a circular import? How did you fix it?"

---

## MONDAY

### 1. How CPython runs your code

**Teach.**
- Source → **tokenize/parse to an AST** → **compile to bytecode** (cached in `__pycache__/*.pyc`) → the **interpreter loop** executes bytecode instructions on a stack machine, one at a time.
- So "Python is compiled *and* interpreted": compiled to bytecode, then interpreted.
- `dis.dis(fn)` shows the bytecode. 3.11 added the *specializing adaptive interpreter* (a big speed-up for hot code), and 3.13 has an experimental JIT.
- Why it matters in practice:
  - The cost model: each bytecode op is relatively expensive, so pushing work into C (built-ins, comprehensions, `sum`, `str.join`, NumPy) is faster.
  - `.pyc` caching affects container start-up.

**Picture it.** Bytecode is sheet music; the eval loop is a musician playing it one note at a time.

**Check.** "Is a list comprehension faster than a for-loop with append? Why?" (Fewer bytecode ops per item: no attribute lookup and call for `.append` each time. Since 3.12, comprehensions are also inlined, PEP 709.)

### 2. Memory: reference counting + the cyclic GC

**Teach.**
- **Reference counting:** every object has a count of references to it. When it hits 0, the object is freed **immediately**. That makes memory release deterministic for most objects.
- **The problem: cycles.** `a.other = b; b.other = a`: counts never reach 0.
- **The cyclic garbage collector** periodically scans *container* objects (lists, dicts, class instances) in **3 generations**. New objects start in gen 0, and survivors get promoted. It finds groups that are only reachable from each other and frees them.
- `gc.collect()` forces a collection; `gc.freeze()` (used before forking workers) avoids copy-on-write churn.
- Memory returned to the OS: CPython's small-object allocator (pymalloc) keeps arenas, so RSS doesn't always drop after objects are freed. That surprises people investigating leaks.
- Leaks in long-running services come from:
  - unbounded caches and module-level dicts
  - `lru_cache` on methods (it holds `self`)
  - listeners/callbacks never removed
  - cycles involving objects with `__del__` in older code
  - C extension leaks

**Picture it.** Refcounting is everyone returning their own tray immediately; the cyclic GC is the cleaner who comes round now and then for trays people stacked on each other.

**Your anchor.** Celery or FastAPI workers whose memory grows overnight (Jio ATS processing 100k resumes a day). The standard mitigations are `max_tasks_per_child` / `--max-requests` (worker recycling), *while* you find the real leak.

**Check.** "Explain refcounting and the cycle collector, and why a FastAPI worker's RSS might keep growing." (R2 Q7, R3 Q10.)

**Traps.** "Python has a GC, so it can't leak" (it can, through references you keep). "`del x` frees the object" (it only removes one reference).

### 3. weakref

**Teach.**
- A **weak reference** points at an object *without* increasing its refcount. When the object dies, the weakref returns `None` (or the entry disappears from a `WeakValueDictionary` / `WeakKeyDictionary` / `WeakSet`).
- Uses:
  - caches that shouldn't keep objects alive
  - observer/listener registries
  - parent pointers in trees (to avoid cycles)
- Not every object supports weakrefs: ints and tuples don't, and classes with `__slots__` need `'__weakref__'` in their slots.

**Your anchor.** Asyncio: `create_task` without keeping a reference. The **event loop only holds a weak reference to tasks**, so a fire-and-forget task can be garbage-collected mid-flight (W3 covers this; it's R3 Q18). Same mechanism.

**Check.** "How does a weakref help a cache?" (R3 Q4.)

### 4. The GIL ⚠️ open miss

**Teach.**
- The **Global Interpreter Lock** lets only one thread execute Python bytecode at a time in a process. It exists because refcounting and much of CPython's internals aren't thread-safe; a single lock keeps them simple and fast for single-threaded code.
- **It's released:**
  - during **blocking I/O** (socket recv/send, file reads, `time.sleep`, DB driver waits)
  - by **C extensions that explicitly drop it** around heavy work (NumPy ops, `hashlib` on large buffers, `zlib`, many image and crypto libraries)
  - every few milliseconds (the switch interval, 5 ms by default), so threads take turns
- **Consequences:**
  - Threads **do** help I/O-bound work.
  - Threads **don't** speed up pure-Python CPU work; they can even slow it down through contention. Your `scripts/async/05` output showed exactly this: threads 4.06 s vs sequential 2.07 s.
  - For CPU work use processes, a native extension, or a separate service.
- **The GIL doesn't make your code thread-safe.** `x += 1` is several bytecodes, so a thread switch can happen between them, and you can still race. You still need locks.
- **Free-threaded Python:**
  - PEP 703: an optional no-GIL build since 3.13, officially supported (no longer experimental) in 3.14.
  - The cost is per-object locking and some single-thread overhead, plus C-extension compatibility work.
  - Sub-interpreters (PEP 734) give per-interpreter GILs.
  - *For a backend service today:* interesting but not a default. Most services are I/O-bound and scale with processes plus asyncio anyway.

**Picture it.** One microphone at a panel. Speakers can be preparing (doing I/O) while someone else talks, but only one speaks at a time.

**Your anchor.** At Jio, you named the GIL as a real bottleneck. Be ready with *how*: the CPU-bound similarity scoring in a threaded server. The fix was separate embedding and similarity services, and scaling with processes and pods.

**Check.** "Name two concrete situations where the GIL genuinely doesn't matter, and one where it bites." (R2 Q1.) "Does the GIL make `counter += 1` thread-safe?"

**Interview angle.** R2 Q1, R3 Q7.

### 5. Attribute lookup and the MRO ⚠️ open miss

**Teach.**
- `obj.x` calls `type(obj).__getattribute__(obj, "x")`, which by default does this:
  1. Look up `x` on the **type's MRO**. If it's a **data descriptor** (defines `__set__` or `__delete__`, e.g. `property`), call its `__get__` and stop.
  2. Otherwise check the **instance `__dict__`**.
  3. Otherwise, if the class attribute found in step 1 is a **non-data descriptor** (a plain function = a method), call `__get__` (this is how methods get bound `self`). If it's a plain value, return it.
  4. Otherwise call `__getattr__` if it's defined (the fallback hook). Otherwise `AttributeError`.
- **MRO (method resolution order):** the linear order of classes Python searches, e.g. `class D(B, C)` gives `D, B, C, A, object` in a diamond. Built with **C3 linearization**, which guarantees:
  - children come before parents
  - the left-to-right order of bases is preserved
  - a consistent order exists, or class creation fails with a `TypeError`
- `super()` means "the **next class in the MRO** of the instance's type", *not* "my parent". That's why cooperative multiple inheritance works: each class calls `super().method()` and the chain visits every class exactly once.

**Picture it.** The MRO is a queue at a help desk: Python asks each class in order "do you have `x`?" and stops at the first yes.

**Your anchor.** Mixins in FastAPI or Django-style code (`class AuditedModel(TimestampMixin, SoftDeleteMixin, Base)`). The order of mixins decides which `save()` runs first. SQLAlchemy declarative models too.

**Check.** "Draw the diamond A → B, C → D, give D's MRO, and explain what `super()` in B calls." (B's `super()` calls **C**, not A. This is the key insight.) "When would `__getattr__` run and `__getattribute__` not, or the reverse?"

**Traps.** Saying `super()` calls the parent class. Overriding `__getattribute__` and recursing infinitely (use `object.__getattribute__(self, name)` inside it).

**Interview angle.** R3 Q1, R3 Q3.

### 6. `__slots__`

**Teach.**
- By default each instance has a `__dict__` (flexible, but memory-heavy). `__slots__ = ("a", "b")` replaces it with fixed slots implemented as descriptors on the class.
- **Gains:** much less memory per instance, slightly faster attribute access.
- **Costs:**
  - no new attributes at runtime
  - no `__weakref__` unless you add it
  - multiple inheritance with slots can conflict
- Use it for **millions of small objects**. `@dataclass(slots=True)` gives it for free.

**Your anchor.** Cellular: millions of generated cell or node objects when converting big rater workbooks. A natural place for slots.

**Check.** "What problem does `__slots__` solve, and what does it cost you?" (R2 Q10.)

---

## TUESDAY

### 7. Descriptors: the mechanism behind property, methods and ORMs ⚠️ open miss

**Teach.**
- A **descriptor** is any object defining `__get__`, `__set__` or `__delete__`, **placed as a class attribute**. Attribute access on instances is then routed through it.
- **Data descriptor** (has `__set__`/`__delete__`): beats the instance `__dict__`. **Non-data descriptor** (only `__get__`): the instance `__dict__` wins.
- What's secretly a descriptor:
  - `property`: a data descriptor
  - **functions**: non-data descriptors whose `__get__` returns a bound method; that's where `self` comes from
  - `classmethod` and `staticmethod`
  - Django/SQLAlchemy model fields
  - Pydantic-style validation in your own code
- `__set_name__(owner, name)` tells the descriptor which attribute name it was assigned to (since 3.6).

```python
class Positive:
    def __set_name__(self, owner, name):
        self.name = "_" + name
    def __get__(self, obj, objtype=None):
        return self if obj is None else getattr(obj, self.name)
    def __set__(self, obj, value):
        if value <= 0:
            raise ValueError(f"{self.name[1:]} must be > 0")
        setattr(obj, self.name, value)

class Quote:
    premium = Positive()
    limit = Positive()
```

**Picture it.** A descriptor is a receptionist sitting in front of an attribute: every read or write goes through them.

**Your anchor.** Quote/rating objects in Aurora/Pulse where limits and premiums must be positive and quantised. A descriptor (or Pydantic) enforces that at assignment.

**Check.** "Explain how `@property` works in terms of descriptors, and why a method call gets `self` automatically."

### 8. Metaclasses and `__init_subclass__` ⚠️ open miss

**Teach.**
- Classes are objects too. Their type is `type`, so `class Foo: ...` is roughly `Foo = type("Foo", bases, namespace)`.
- A **metaclass** is a subclass of `type` that customises **class creation**:
  - `__new__`/`__init__` run when the `class` statement executes
  - `__call__` runs when the class is instantiated
  - `__prepare__` sets up the namespace dict
- **Real uses:**
  - ORMs: SQLAlchemy declarative collects `Column`s into a table definition at class-creation time
  - the Pydantic v1 `ModelMetaclass` collected fields; v2 still uses a metaclass but the core is in Rust
  - ABCs (`ABCMeta`) enforce abstract methods
  - Enum
  - plugin registries
- **Modern advice:** prefer `__init_subclass__` (a hook on the base class, called whenever a subclass is defined, since 3.6), class decorators or descriptors. They cover about 90% of cases and are far easier to read. Write a metaclass only when you need to control the class object itself or its namespace.

```python
class Rater:
    registry: dict[str, type] = {}
    def __init_subclass__(cls, product: str, **kw):
        super().__init_subclass__(**kw)
        Rater.registry[product] = cls

class MarineRater(Rater, product="marine"): ...
```

**Your anchor.** Cellular: a registry of rater modules per product, built from generated classes. `__init_subclass__` is the right tool. That's your answer to "have you written one, and would you?": "I'd reach for `__init_subclass__` first. Here's the registry I'd build."

**Check.** "What does a metaclass let you do that a class decorator can't?" (Run during class *body* namespace creation via `__prepare__`; affect subclasses automatically, including how they're instantiated via `__call__`.)

**Interview angle.** R3 Q2, R3 Q11.

### 9. Imports: `sys.modules`, cycles and reloading

**Teach.**
- `import x`:
  1. check the **`sys.modules`** cache; if it's there, return it (that's why importing twice is cheap and doesn't re-execute the module)
  2. otherwise find it via `sys.path` finders, create the module, **execute the module body top to bottom**, and store it in `sys.modules`
- **Import-time side effects** (connecting to a DB, reading env vars, starting threads) run on first import. Avoid them; use explicit start-up such as FastAPI lifespan.
- **Circular imports:** A imports B while B (during its execution) imports A, which is *partially initialised*, so names don't exist yet. Three legitimate fixes:
  1. restructure: move the shared code to a third module
  2. import inside the function, where it's needed (a deferred import)
  3. `import module` instead of `from module import name`, plus `TYPE_CHECKING` guards for type-only imports
- `importlib.reload(mod)` re-executes it in the **same module object**. Objects created from the old classes keep the old classes, `from x import y` copies don't update, and module-level state resets. That's why reload is a dev-only tool.

**Your anchor.** Cellular generated modules: loading many generated rater modules dynamically (`importlib.import_module`) and the temptation to hot-reload a rater when its version changes. The safe answer is versioned module names or process restarts, not `reload`.

**Check.** "What are three fixes for circular imports, and which one do you prefer?" (R3 Q5, Q6.)

### 10. Typing that earns its keep

**Teach.**
- Type hints aren't enforced at runtime. **mypy/pyright** check them statically, and Pydantic enforces them at runtime at boundaries.
- Useful pieces:
  - `Protocol`: structural typing ("anything with `.read()`"), great for dependency injection and test fakes without inheritance
  - `TypeVar` and generics (`def first(xs: list[T]) -> T`)
  - `ParamSpec`: type a decorator so the wrapped function keeps its signature
  - `Literal` for fixed string options
  - `TypedDict` for JSON shapes
  - `@overload`; `Self`; `TypeGuard`/`TypeIs` for narrowing
- **What `mypy --strict` catches that tests don't:** `None` paths you never tested (`Optional` misuse), wrong argument types in rarely run branches, missing returns, and refactor fallout across modules. Run it in CI on new code at least.

**Your anchor.** Typing a `retry` decorator with `ParamSpec` so FastAPI dependencies keep their signatures. A `RaterProtocol` so the Cellular-generated code and the agent alternative are interchangeable.

**Check.** "What's `Protocol` for, and how does it differ from an ABC?" (Structural vs nominal: no inheritance needed.) R3 Q11, Q13; R6 J Q84.

### 11. Packaging and reproducible builds

**Teach.**
- `pyproject.toml` is the standard. **Wheels** are prebuilt and install fast; **sdists** are source and may need compilers.
- **Lockfiles** pin the full dependency tree, with hashes: `uv.lock`, `poetry.lock`, or `pip-compile` output.
- `uv` is the fast modern tool for envs, locking and installs.
- **Reproducible Docker build:**
  - copy only the lockfile and pyproject first, then install dependencies (a cached layer), then copy the code
  - multi-stage: build wheels in the builder stage, install with `--no-index` in the runtime stage (exactly what `scripts/k8s_graceful_shutdown/Dockerfile` does)
  - pin the base image digest
- Tooling: `ruff` (lint + format), `pre-commit`, and mypy/pyright in CI.

**Check.** "How do you guarantee the same dependency versions in dev, CI and prod?" (R6 J Q83.)

### 12. Profiling: finding the real bottleneck

**Teach.**

| Tool | What it tells you | When |
| --- | --- | --- |
| `cProfile` + `snakeviz`/`pstats` | Deterministic per-function call counts and time | Local, reproducible slow path; adds overhead |
| **`py-spy`** | A *sampling* profiler. Attaches to a running PID with no code change; `top`, `dump` and flame graphs | **Production.** Also finds *where it's blocked* (the async blocked-loop miss) |
| `yappi` | Profiling across threads and coroutines with wall vs CPU time | Async/threaded services |
| `line_profiler` | Per-line time in a function | After you know which function |
| `tracemalloc` | Allocation snapshots and diffs by line | Memory growth |
| `memray` | Detailed memory profiling, native allocations, flame graphs | Serious leak hunts |

- **"Slow but not CPU-bound"** means waiting: on the DB, the network, locks or the GIL. Use py-spy with `--idle` or wall-clock mode, request tracing (spans show where time goes), and DB query logs or `EXPLAIN`.
- The method: **measure, don't guess.** Reproduce with a load test, profile, fix the top item, re-measure.

**Your anchor.** You quoted p50 100 ms / p95 200 ms at Jio. Be ready for "how did you find what was slow?" with tools named in order.

**Check.** "A FastAPI service is slow but CPU is at 20%. Walk me through your investigation." (R3 Q9, Q10.)

---

## Wednesday lab (60–75 min)

1. **Bytecode:** `dis.dis` a for-loop + append vs a list comprehension. Count the instructions in the loop body. Explain the difference out loud.
2. **GC:** create a reference cycle between two objects with a `__del__` that prints; `del` both names; observe nothing happens; call `gc.collect()` and observe. Then fix it with `weakref.ref` for the back-pointer.
3. **MRO and super:** build the A/B/C/D diamond where each `hello()` prints and calls `super().hello()`. **Predict the output first**, then print `D.__mro__`.
4. **Descriptor:** implement `Positive` from concept 7 and break it on purpose (assign -5). Then make a `__init_subclass__` registry of 3 raters.
5. **Profile:** write a deliberately slow function (string concatenation in a loop + an `O(n²)` membership check on a list). Profile it with cProfile, then run `py-spy top` / `py-spy record` against it running in a loop. Fix it and re-measure.
6. Optional: ask Claude to turn this lab into `scripts/python_internals/` in the async-scripts style.

## Thursday cheat sheet must include

- [ ] Source → AST → bytecode → eval loop; why comprehensions are faster
- [ ] Refcount + 3-generation cyclic GC; the 5 leak sources in services; why RSS doesn't drop
- [ ] GIL: what it protects, the 3 release cases, why `+=` still races, free-threaded status
- [ ] Attribute lookup order (data descriptor → instance dict → non-data/class attr → `__getattr__`)
- [ ] The diamond MRO and what `super()` really means
- [ ] The descriptor protocol; how property and methods use it
- [ ] Metaclass vs `__init_subclass__`, with the registry example
- [ ] The `sys.modules` cache; 3 circular-import fixes; why `reload` is dangerous
- [ ] Protocol vs ABC; ParamSpec for decorators; what `--strict` catches
- [ ] The profiling tool table

## Friday quiz (30–40 min)

- **New:** R3 Q1–11, Q13 (pick 7, **must include Q1, Q2, Q3**); R2 Q7, Q10; R6 J Q83 or Q84.
- **Spaced review:** R2 Q1 (GIL, open miss) + R2 Q4 (from W1; the second hit if it was right last week).
- **Log:** `python_internals` in the knowledge map. If Q1–Q3 are now `covered`, set their misses Hits to `1/2`.

## Infographic brief

Title: **"Inside CPython"**. Panels:
1. Pipeline: `.py` → AST → bytecode (`.pyc`) → eval loop (+ specialising interpreter).
2. Memory: refcount (immediate) vs the generational GC (cycles), with "5 ways services leak".
3. GIL timeline: three threads, showing where the GIL is released (I/O, C extensions, switch interval).
4. Attribute lookup as a flowchart (4 steps).
5. A diamond MRO diagram with the `super()` arrow from B → C.
6. Tool picker: cProfile / py-spy / yappi / tracemalloc / memray.

## Done when

- [ ] R3 Q1, Q2, Q3 answered at least `partial` (ideally `covered`): the three gaps are closed
- [ ] You can draw the attribute-lookup flow and the diamond MRO from memory
- [ ] `python_internals` moves off `weak` in the knowledge map
