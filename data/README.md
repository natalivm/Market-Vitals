# Market Vitals — Historical Data

Time-series log of the **Market Vitals Bot** feed readings. One row per scan.
This is the raw historical record for weekly analysis (e.g. spotting
divergences that precede a crash or recovery).

## Rules (per project CLAUDE.md)

- **Only confirmed, timestamped feed numbers go in here.** Never estimated,
  carried-forward, or approximated values. If a scan was missed, leave the gap —
  do not back-fill with a guess.
- Each row = one Market Vitals Bot post, identified by its UTC timestamp.
- Append-only. Do not edit historical rows once committed.

## Schema — `vitals_history.csv`

| Column              | Meaning                                              | Example          |
|---------------------|------------------------------------------------------|------------------|
| `timestamp_utc`     | Scan time, ISO-8601 UTC                              | `2026-06-05T19:01:00Z` |
| `vitals_label`      | Composite verdict text from the feed                 | `MIXED`          |
| `vitals_score`      | Composite score (+N)                                 | `1`              |
| `vix`               | VIX                                                  | `19.40`          |
| `move`              | MOVE index                                           | `71.16`          |
| `mcclellan`         | McClellan oscillator                                 | `7.72`           |
| `hindenburg`        | Hindenburg Omen state (`clear` / `triggered`)        | `clear`          |
| `pct_above_200dma`  | % of stocks above 200-day MA                         | `58.3`           |
| `put_call`          | Put/Call ratio                                       | `1.11`           |
| `smfi`              | Smart Money Flow Index                               | `50820`          |
| `market_tide_musd`  | Market Tide net premium flow, **millions USD**       | `-1524` (= −$1,524M) |
| `momentum_label`    | Momentum Pulse verdict text                          | `STRONG_BULLISH` |
| `momentum_score`    | Momentum Pulse score (+N)                            | `3`              |
| `pct_above_12sma`   | % of stocks above 12-day SMA                         | `56.1`           |
| `pct_above_20sma`   | % of stocks above 20-day SMA                         | `60.2`           |
| `pct_above_50sma`   | % of stocks above 50-day SMA                         | `54.6`           |
| `power_hour`        | Final-hour tape read (`distribution`/`accumulation`/blank if not in feed) | `distribution` |

> `power_hour` was added when the feed introduced it (2026-06-05 20:11 UTC).
> Earlier rows leave it blank — never back-fill a guess.

Sector rotation has its own store: **`rotation_history.json`** (see its
`_schema`/`_rules` keys). Same discipline — confirmed feed numbers only,
append-only.

Notes:
- `market_tide_musd` is in **millions** (`-1524` means −$1,524M). Negative = bearish flow.
- Label text uses `STRONG_BULLISH` (underscore) so it stays single-token in CSV.

## Adding a new scan

Append one line per Market Vitals Bot post, copying the numbers exactly as shown.
Keep rows in chronological order.

## Quick analysis starter

```python
import pandas as pd
df = pd.read_csv("data/vitals_history.csv", parse_dates=["timestamp_utc"])
df = df.sort_values("timestamp_utc")
# e.g. flag deteriorating breadth while the index holds up
print(df[["timestamp_utc", "vitals_score", "mcclellan", "market_tide_musd", "vix"]])
```
