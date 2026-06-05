# Market Vitals — Project Rules

## DATA ACCURACY — NON-NEGOTIABLE

**Never estimate. Never make up a number. Skip instead of guessing.**

1. If a data source returns an error, is blocked (403/timeout), or returns no
   parseable value — say "NO ACCESS" and mark the indicator **STALE**.
2. Never carry a previous session's value forward and present it as fresh data.
   If the value didn't come from a live network response in the current run,
   it is STALE.
3. Never invent or "approximate" a value because the source was unavailable.
   Real stale data shown honestly is always better than a confident wrong number.
4. If fewer than 4 of 7 fetchable indicators return live data, the script aborts
   and does NOT commit — a partially stale board is preferable to a misleading one.
5. When updating the dashboard manually (between script runs), only use values
   from a confirmed, timestamped source (e.g. the Market Vitals Bot feed).
   Cite the source and timestamp in the commit message.

## TOKEN-EFFICIENT UPDATES — READ ONLY THE DATA SECTION

`index.html` is ~1,200 lines. The CSS (~5k tokens) and render infrastructure
(~5k tokens) never change for a data update. **Only read the data section:**

```
Read index.html  offset=783  limit=80
```

This covers the `SCAN` config + `indicators` + `bars` + `plays` blocks
(lines 784–860, ending at the `DATA END` marker). That's ~80 lines /
~400 tokens instead of the full ~12,000-token file.

After editing, append to `data/vitals_history.csv` (always in the same commit).

## HISTORICAL LOG — REQUIRED ON EVERY DASHBOARD UPDATE

Whenever the dashboard (`index.html`) is updated with new Market Vitals Bot
feed data, **always append a corresponding row to `data/vitals_history.csv`
in the same commit.** Never let the two drift out of sync.

Rules:
- One row per Bot post (identified by its UTC timestamp).
- Copy the numbers exactly as shown in the screenshot — no rounding, no
  approximation.
- Append-only: never edit or delete historical rows once committed.
- If a value wasn't in the feed (e.g. Hindenburg not shown), leave the
  cell empty rather than guessing.
- Column order and schema are defined in `data/README.md`.

## Project structure

```
index.html                  — main dashboard (single file, no build step)
market-vitals-guide.html    — educational PDF-ready guide
scripts/
  update_vitals.py          — auto-updater script
  requirements.txt          — Python dependencies
.github/workflows/
  deploy.yml                — existing deploy workflow (do not modify)
  update_vitals.yml         — auto-update workflow (SCHEDULE DISABLED, see below)
```

## Auto-updater is DISABLED — manual updates only

`scripts/update_vitals.py` and its scheduled workflow are **off**. The script
patched the old HTML layout with regexes; after `index.html` was refactored to
the single `SCAN` config block (with JS-filled header/ribbon/footer), those
regexes no longer match and a run would produce a half-updated, inconsistent
board. The cron schedule in `update_vitals.yml` is commented out.

**Until the script is rewired to target `SCAN`, update the dashboard manually**
from the Market Vitals Bot feed (and append to `data/vitals_history.csv`).

## Board indicators (8 core + Power Hour)

The 8 **core indicators** (the `indicators` array): VIX, MOVE, McClellan,
Hindenburg, % > 200 DMA, Put/Call, SMFI, Market Tide. The green-count and
gauge verdict derive automatically from this array (e.g. "5 of 8 green").

**Power Hour** (final-hour tape read) is NOT a core indicator card — it renders
as a single indicator card (same flip/TAP popover) **inside the gauge card,
under the Fear/Greed scale legend**, via the `SCAN.powerHour` object:
`{ show, tag, state, detail }`. Set `show:false` (or omit) on days the feed
doesn't post it and the card disappears. The `{{power}}` and `{{power_detail}}`
tokens resolve from `SCAN.powerHour` for the ribbon/plays.

**Power Hour is a contextual readout only — it has ZERO effect on the gauge.**
The needle/score and verdict derive solely from `SCAN.composite.cur` (the Bot's
own composite number, transcribed verbatim); Power Hour is not in the
`indicators` array nor the composite-weights table, so it doesn't move the
needle or the green-count. Do NOT give Power Hour a separate composite weight:
the Bot's composite already reflects its own model (Power Hour likely included),
so adding a weight here would double-count it.

## Rotation Radar

Separate in-page view (🧭 Rotation button, hash `#rotation`). Renders from
**`data/rotation_history.json`** (fetched at runtime, so it needs the live
site / a server — not `file://`). Each weekly update appends one snapshot
object. The view is a **boss-deck layout**: headline regime banner → 3 KPI
cards (largest outflow, biggest dip-buy, net-flow breadth) → the hero
**net-flow diverging bar chart** (`renderRotation` → `#rotFlow`, top 18 by
|f5|, sorted, green-right/red-left) → 14-day conviction → held-up tiles →
weekly timeline heatmap (`renderHeatmap`, **hidden until ≥2 readings exist**).
Same accuracy rules as vitals.

## Schedules (Kyiv timezone = EEST = UTC+3)

| Kyiv time  | UTC   | Label            |
|------------|-------|------------------|
| 4:00 PM    | 13:00 | Pre-market scan  |
| 6:30 PM    | 15:30 | Mid-session      |
| 10:30 PM   | 19:30 | 30 min to close  |

## Hindenburg Omen toggle

Set `HINDENBURG_TRIGGERED=true` in GitHub repo **Variables**
(Settings → Secrets and variables → Variables) to manually flag the Omen.
The script also auto-triggers it when McClellan < -5 (breadth divergence rule).

## Composite score weights

| Indicator        | Weight |
|-----------------|--------|
| McClellan        | 16%    |
| Hindenburg       | 16%    |
| % > 200 DMA      | 16%    |
| Put/Call         | 16%    |
| Market Tide      | 10%    |
| VIX              | 10%    |
| SMFI             |  8%    |
| MOVE             |  8%    |
