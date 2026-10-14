# Infographics: One-Page Visual Recaps

There's one image per finished week, for 5-minute weekly or monthly brush-ups. Each week has an **SVG** (the source: text-based, diffable in git, and rendered by GitHub and VS Code) and a **PNG** (for your phone's gallery or printing).

| Week | Image |
| --- | --- |
| W03 Async and concurrency | [W03_async.svg](W03_async.svg) · [PNG](W03_async.png) |

## How they get made

1. **You write your own cheat sheet first** (Thursday of that week). The infographic is a *check* on your recall, not a replacement for it.
2. Ask Claude Code: *"make the W0x infographic from teach/W0x_... and my cheat sheet"*. It uses the lesson plan's **Infographic brief**, plus whatever you got wrong that week.
3. Claude writes the SVG, renders it to PNG with headless Edge, looks at the render to check the layout, and fixes anything that overlaps.

To re-render a PNG yourself (Windows, from the repo root, in Git Bash):

```bash
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu \
  --hide-scrollbars --window-size=1200,1680 \
  --screenshot="$(pwd -W)\\teach\\infographics\\W03_async.png" \
  "file:///$(pwd -W)/teach/infographics/W03_async.svg"
```

Match `--window-size` to the SVG's `width`/`height`.

## Style rules (so they stay consistent)

- 1200 px wide, one page, light background, the same navy header and footer strip.
- 5–7 numbered panels, each answering one interview question.
- Tables over prose; **bold the trap**: the thing interviewers fish for.
- Always end with "N rules to say out loud".
