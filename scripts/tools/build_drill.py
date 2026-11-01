"""Build the drill page: inject drill/deck.json into drill/drill.template.html.

Usage (repo root):  python scripts/tools/build_drill.py
Writes drill/drill.html, which is what gets published as the "Say It Out Loud" artifact.
Edit questions in deck.json (keep ids stable: progress is keyed by id), rebuild, republish.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRILL = ROOT / "drill"

deck = json.loads((DRILL / "deck.json").read_text(encoding="utf-8"))
ids = [c["id"] for c in deck]
dupes = {i for i in ids if ids.count(i) > 1}
if dupes:
    raise SystemExit(f"duplicate ids in deck.json: {sorted(dupes)}")
for c in deck:
    missing = {"id", "deck", "title", "source", "q", "a"} - c.keys()
    if missing:
        raise SystemExit(f"{c.get('id')}: missing {sorted(missing)}")

template = (DRILL / "drill.template.html").read_text(encoding="utf-8")
# "</" would end the inline <script> early if it ever appeared in a card.
payload = json.dumps(deck, ensure_ascii=False).replace("</", "<\\/")
out = template.replace("/*DECK*/[]", payload, 1)
(DRILL / "drill.html").write_text(out, encoding="utf-8")
print(f"drill/drill.html: {len(deck)} cards, {len({c['deck'] for c in deck})} decks")
