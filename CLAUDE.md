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

## Project structure

```
index.html                  — main dashboard (single file, no build step)
market-vitals-guide.html    — educational PDF-ready guide
scripts/
  update_vitals.py          — auto-updater script
  requirements.txt          — Python dependencies
.github/workflows/
  deploy.yml                — existing deploy workflow (do not modify)
  update_vitals.yml         — scheduled data-update workflow (Mon-Fri)
```

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
