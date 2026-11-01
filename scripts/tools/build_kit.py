"""Build a system design kit page: inject <kit>/kit.json into system_design/kit.template.html.

Usage (repo root):  python scripts/tools/build_kit.py system_design/01_news_feed
Writes <kit>/page.html, which is published as that kit's artifact (republish to the same URL).
See system_design/README.md for the kit spec and kit 01's kit.json for the data shape.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
kit_dir = (ROOT / sys.argv[1]).resolve() if len(sys.argv) > 1 else sys.exit(__doc__)
kit = json.loads((kit_dir / "kit.json").read_text(encoding="utf-8"))

# Catch broken references early: the page would silently draw nothing for them.
ids = {c["id"] for c in kit["components"]}
lanes = {lane["id"] for lane in kit["lanes"]}
problems = [f"component {c['id']}: unknown lane {c['lane']}" for c in kit["components"] if c["lane"] not in lanes]
problems += [f"edge {e['from']}->{e['to']}: unknown end" for e in kit["edges"] if not {e["from"], e["to"]} <= ids]
edge_set = {(e["from"], e["to"]) for e in kit["edges"]}
for f in kit["flows"]:
    for i, s in enumerate(f["steps"], 1):
        problems += [f"flow {f['id']} step {i}: unknown node {n}" for n in s["nodes"] if n not in ids]
        problems += [f"flow {f['id']} step {i}: no edge {a}->{b}" for a, b in s.get("edges", []) if (a, b) not in edge_set]
# Box labels are drawn at fixed size: longer text spills past the box edge.
problems += [f"component {c['id']}: short name over 18 chars" for c in kit["components"] if len(c.get("short", c["name"])) > 18]
problems += [f"component {c['id']}: tech over 19 chars" for c in kit["components"] if len(c.get("tech", "")) > 19]
cells = [(c["col"], c["row"]) for c in kit["components"]]
problems += [f"two components share cell {cell}" for cell in {x for x in cells if cells.count(x) > 1}]
if problems:
    sys.exit("kit.json problems:\n  " + "\n  ".join(problems))

template = (ROOT / "system_design" / "kit.template.html").read_text(encoding="utf-8")
payload = json.dumps(kit, ensure_ascii=False).replace("</", "<\\/")
page = template.replace("/*TITLE*/", kit["page_title"], 1).replace("/*KIT*/{}", payload, 1)
(kit_dir / "page.html").write_text(page, encoding="utf-8")
print(f"{kit_dir.name}/page.html: {len(kit['components'])} components, {len(kit['edges'])} edges, {len(kit['flows'])} flows")
