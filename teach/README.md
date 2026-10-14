# Teach: Weekly Lesson Plans

Question banks (`questions/`) are for **testing**. These files are for **teaching**. Each one is a lesson plan for one week of [plan/PREP_TODO.md](../plan/PREP_TODO.md), written for a voice agent in teacher mode (and readable by you on your own).

**Rule: teach before you test.** The voice agent teaches a week's concepts Mon/Tue, you get hands-on Wed and write from memory Thu, and only on Friday does it switch to interviewer mode on that week's questions.

## Files

| Week | File | Topic | Dates |
| --- | --- | --- | --- |
| W1 | [W01_python_core.md](W01_python_core.md) | Python core and the data model | 2026-10-19 → 10-25 |
| W2 | [W02_python_internals.md](W02_python_internals.md) | Python internals and modern Python | 2026-10-26 → 11-01 |
| W3 | [W03_async.md](W03_async.md) | Async and concurrency | 2026-11-02 → 11-08 |
| W4+ | *(written about 2 weeks ahead, so each plan can use your latest misses)* | | |
| any | [infographics/](infographics/) | One-page visual recap per finished week | |

## Structure of every lesson plan

1. **Header:** the goal, how this week moves the knowledge map, and the day-by-day plan.
2. **Sources (`pack` block):** the exact answer-file questions for this week. The NotebookLM pack builder reads this block (see below).
3. **Warm-up diagnostic:** 3–4 quick questions on Monday, to find what's already solid so the agent can skip it.
4. **Concepts, in teaching order.** Each one has:
   - **Teach:** plain language first, then the precise detail.
   - **Picture it:** one analogy or mental image.
   - **Your anchor:** where it showed up in your own projects.
   - **Check:** "explain it back" prompts. The agent asks and you answer in under 90 seconds.
   - **Traps:** the common misconceptions interviewers fish for.
   - **Interview angle:** the question numbers it maps to.
5. **Wednesday lab:** hands-on steps.
6. **Thursday cheat sheet:** what your from-memory one-pager must contain.
7. **Friday quiz:** which questions to ask, plus spaced review from `progress/misses.md`.
8. **Infographic brief:** the panels for this week's recap image, made *after* you've written your own cheat sheet.
9. **Done when:** the exit check.

## Instructions for the voice agent (teacher mode)

- Teach the concepts in order. Mon = first half, Tue = second half (the plan marks the split).
- Per concept: give the **Teach** part in about 2–3 spoken minutes, use the analogy and the anchor, then ask the **Check** question and **wait**. Correct the gaps briefly. Only move on once he can say it back properly.
- If the warm-up shows a concept is already solid, do the Check only and skip the teaching.
- Keep it conversational, with no lists read aloud. One question at a time.
- Anything he struggles with goes into `progress/misses.md` at the end of the session (or tell him to add it).

## NotebookLM: one pack per week

Upload just this week's material, so the walking audio matches what you're learning:

```bash
python scripts/tools/build_week_pack.py teach/W01_python_core.md
# -> writes notebooklm/W01_python_core_pack.md (lesson plan + exactly this week's answer sections)
```

Upload that single file to a new NotebookLM notebook named after the week. The `notebooklm/` folder is git-ignored, because it's generated and can be rebuilt any time.

## Writing the next plans

Ask Claude Code: *"write teach/W04 and W05 using PREP_TODO and my misses"*. Plans are written about 2 weeks ahead on purpose, so they can reuse your latest misses and knowledge-map notes rather than going stale.
