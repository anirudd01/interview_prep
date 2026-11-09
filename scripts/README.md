# Scripts

This folder only holds this repo's own helper tools. The runnable refresher scripts
(asyncio series, Kubernetes graceful-shutdown demo, FastAPI, gRPC, SSE, WebSockets...)
moved to the sibling **PyPractice** repo (`../PyPractice`, GitHub `anirudd01/PyPractice`).

| Folder | Topic | Needs |
| --- | --- | --- |
| [tools/](tools/) | `build_drill.py` rebuilds `drill/drill.html`, `build_kit.py` builds a system-design kit page, `build_week_pack.py` turns a `teach/` lesson plan into one NotebookLM source file | Python 3.10+ |

| Moved to | Was |
| --- | --- |
| `PyPractice/py_async/` (01–08 plus README) | `scripts/async/` |
| `PyPractice/pp_k8s/graceful_shutdown/` | `scripts/k8s_graceful_shutdown/` |
