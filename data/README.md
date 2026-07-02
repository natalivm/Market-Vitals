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
| `gex`               | Options dealer gamma-exposure regime (`accelerant`/`suppressant`/blank if not in feed) | `accelerant` |

> `power_hour` was added when the feed introduced it (2026-06-05 20:11 UTC).
> Earlier rows leave it blank — never back-fill a guess.

> `gex` was added when the feed introduced it (2026-07-02 13:02 UTC). It records
> the options dealers' net gamma regime: `accelerant` (dealers short gamma —
> hedging amplifies moves) or `suppressant` (dealers long gamma — hedging
> dampens moves). Contextual only, like `power_hour` — NOT a core gauge
> indicator and not in the "X of 8 green" count. Earlier rows leave it blank —
> never back-fill a guess.

Sector rotation has its own store: **`rotation_history.json`** (see its
`_schema`/`_rules` keys). Same discipline — confirmed feed numbers only,
append-only.

> **Ingestion helper:** paste a day's Rotation Radar feed text and let
> `scripts/parse_rotation.py` build the snapshot (stdlib only, no deps). It
> groups posts into scans by time, selects the ~20:00 UTC **close** by default,
> **never mixes scans** (reports missing sections instead of back-filling),
> normalizes `$K/$M/$B` → millions, and validates before writing:
> ```
> python3 scripts/parse_rotation.py feed.txt --list            # see the scans found
> python3 scripts/parse_rotation.py feed.txt --scan close       # preview the snapshot
> python3 scripts/parse_rotation.py feed.txt --append data/rotation_history.json
> ```
> The editorial `read` field is not generated — add it by hand.

> **Self-sourced auto-bot:** `scripts/fetch_rotation.py` (stdlib only) pulls ETF
> prices from Yahoo, derives net flows from day-over-day shares-outstanding
> deltas, classifies signals/regime, and appends a schema-valid snapshot —
> scheduled by `.github/workflows/fetch_rotation.yml` (~20:10 UTC). These are
> **our own computed numbers** (not the Trading Apologist feed); flows bootstrap
> over a few days as the `rotation_shares.json` cache fills, and the run **aborts
> without committing** on low coverage or schema failure. See
> `docs/rotation_feed_spec.md`. Use `parse_rotation.py` instead when capturing
> the original bot's feed by hand.

## Schema — `sector_heatmap_history.json`

A **heat-map format** reporting each sector's *cap-weighted % move* (the feed's
"sector score") plus a whole-universe cap-weighted move. **Two feed variants
share this store:** the **Rotation Radar Bot**'s "SECTOR HEAT MAP" (universe =
all stocks, R3000 + S&P 500; introduced 2026-06-10) and, from **2026-06-11**,
the **Market Vitals Bot**'s "S&P 500 HEAT MAP" (universe = S&P 500). This is a
separate, additional store — the ETF net-flow feed (`rotation_history.json`)
continues in parallel and is unchanged.

| Field            | Meaning                                                        | Example      |
|------------------|----------------------------------------------------------------|--------------|
| `date`           | Trading session the map covers, ISO date                       | `2026-06-11` |
| `scan`           | Feed's scan label                                              | `EOD`        |
| `source`         | Feed variant (`Rotation Radar` \| `Market Vitals`), from 2026-06-11 | `Market Vitals` |
| `universe`       | Stock universe the map covers, from 2026-06-11                 | `S&P 500`    |
| `market`         | Whole-universe cap-weighted move, percent                     | `1.70`       |
| `sectors[]`      | Per-sector cap-weighted move, ordered best→worst as the feed lists them | — |
| `sectors[].name` | Sector label **as the feed displays it** (labels differ slightly between variants — keep verbatim) | `Basic Materials` |
| `sectors[].move` | That sector's cap-weighted move, percent                       | `3.40`       |

> Confirmed feed numbers only; append-only; copy percentages exactly. The
> per-stock heat-map *tiles* are an image only — not transcribed.

## Schema — `sector_relative_strength_history.json`

**SECTOR RELATIVE STRENGTH** from the **Rotation Radar Bot** — comes in a
**DAILY** variant (% change vs the prior day's close, an intraday tape) and a
**WEEKLY** variant (% change vs the prior *week's* close, `scan: "WEEKLY · Week
of <Mon>"`, dated to the week-ending Friday). Distinct from the cap-weighted
"sector score" in `sector_heatmap_history.json`. The list mixes GICS sectors
with breadth/style proxies (IWM, SMH, XLK) and is ordered best→worst as the feed
lists them. From the **2026-06-22 weekly** the feed widened the set to include
sub-sector leads outside the 11 GICS — **XBI** (Biotech), **KRE** (Regional
Banking), **XHB** (Homebuilders), **XOP** (Oil & Gas Exploration) — and added an
**equal-weight RSP** benchmark alongside SPY.

| Field             | Meaning                                                       | Example      |
|-------------------|---------------------------------------------------------------|--------------|
| `date`            | Session (daily) or week-ending Friday (weekly), ISO date      | `2026-06-16` |
| `scan`            | Feed's scan label                                             | `DAILY` / `WEEKLY · Week of Jun 22` |
| `ts`              | Post time (ISO-8601 UTC) if shown, else `null` — never guess  | `null`       |
| `source`          | Feed variant                                                  | `Rotation Radar` |
| `benchmark`       | The SPY reference line `{sym, move}`                          | `{"sym":"SPY","move":-0.66}` |
| `benchmark_ew`    | Equal-weight reference line `{sym, move}` (RSP), weekly variant; omit if not shown | `{"sym":"RSP","move":1.0}` |
| `sectors[]`       | Per-line readings, ordered best→worst as the feed lists them  | —            |
| `sectors[].name`  | Group label as the feed displays it                           | `Financials` |
| `sectors[].sym`   | ETF/proxy ticker                                              | `XLF`        |
| `sectors[].move`  | % change vs prior close                                       | `1.51`       |
| `sectors[].s`     | Feed dot color: `green` (leading) / `gray` (mid-pack) / `red` (lagging) | `green` |
| `sectors[].src`   | `"chart"` when the value came from a chart end-label, not the text list (rounded ~0.1%); omit when from the text list | `chart` |

> Confirmed feed numbers only; append-only; copy percentages exactly. Record
> `ts: null` when the post shows no UTC timestamp. The chart image itself is not
> transcribed beyond labelled values — a line shown only as a **gray, unlabelled**
> series (e.g. XHB/XOP in the Jun-22 weekly) carries **no number, so omit it**
> rather than reading a value off the curve. When a value is taken from a chart
> **end-label** because the text list didn't include that name, tag the row
> `src: "chart"` so the mixed precision is visible.

## Schema — `moc_imbalance_history.json`

**Market-On-Close (closing-auction) order imbalances** from the `#MACRO` feed.
One row per close. Magnitudes are notional **USD millions** (`809.2` = $809.2M).
A **BUY** imbalance pressures prices up into the bell; **SELL** pressures down —
magnitude alone is not directional. Contextual only; not a core board indicator.

| Field    | Meaning                                                  | Example      |
|----------|----------------------------------------------------------|--------------|
| `date`   | Trading session the close imbalance refers to            | `2026-06-11` |
| `ts`     | Post time (ISO-8601 UTC) if the feed gave one, else null | `null`       |
| `side`   | `BUY` / `SELL` / `null` when the feed posted magnitude only | `null`    |
| `sp500`  | S&P 500 imbalance, USD millions                          | `809.2`      |
| `ndx100` | Nasdaq 100 imbalance, USD millions                       | `428.6`      |
| `dow30`  | Dow 30 imbalance, USD millions                           | `892.1`      |
| `mag7`   | Mag 7 imbalance, USD millions                            | `581.8`      |

> Append-only; confirmed numbers only. **Never guess the buy/sell side** — if
> the feed showed magnitude without direction, record `side: null`. Omit a
> basket the feed didn't show.

Notes:
- `market_tide_musd` is in **millions** (`-1524` means −$1,524M). Negative = bearish flow.
- Label text uses `STRONG_BULLISH` (underscore) so it stays single-token in CSV.

## Schema — `cycle_peak_history.csv`

The **Cycle Peak Doom Clock** is a *separate, slow weekly feed* — not the
intraday Market Vitals board. It measures *how late in the cycle we are* from
conditions that cluster near major tops. **One row per weekly Doom Clock post.**
It is contextual only and does **not** feed the Fear & Greed needle.

| Column                  | Meaning                                                  | Example   |
|-------------------------|----------------------------------------------------------|-----------|
| `timestamp_utc`         | Post time, ISO-8601 UTC                                   | `2026-06-05T22:30:00Z` |
| `clock`                 | Doom-clock dial position (midnight = cycle peak)         | `9:17`    |
| `phase`                 | Headline phase text                                      | `MATURING`|
| `cycle_peak_risk_pct`   | Cycle Peak Risk, %                                       | `32`      |
| `risk_change_wk`        | Week-over-week change in risk pts (▼ negative = easing)  | `-3`      |
| `weeks_logged`          | Feed's "N/M wks logged" trend-confidence note            | `3/4`     |
| `rotation`              | Rotation category — triggers fired / total (verbatim)   | `2/6`     |
| `breadth`               | Breadth category                                         | `0/4`     |
| `volatility`            | Volatility category                                      | `2/4`     |
| `rates_credit`          | Rates & Credit category                                  | `0/4`     |
| `macro`                 | Macro category                                           | `2/8`     |
| `sentiment`             | Sentiment category                                       | `1/6`     |
| `valuation`             | Valuation category                                       | `4/4`     |
| `shiller_cape`          | Shiller CAPE                                             | `41.6`    |
| `buffett_ratio_pct`     | Buffett ratio (equities/GDP), %                         | `230`     |
| `vix`                   | VIX (weekly read)                                       | `21.5`    |
| `vix3m`                 | VIX3M                                                   | `21.8`    |
| `vix_ts_ratio`          | VIX / VIX3M term-structure ratio                        | `0.99`    |
| `vvix`                  | VVIX (vol-of-vol)                                       | `102`     |
| `yield_curve_10y2y`     | 10Y-2Y spread, pts                                      | `0.38`    |
| `hy_spread_pct`         | High-yield spread, %                                    | `2.74`    |
| `pct_above_200dma`      | % of stocks above 200DMA                                | `58`      |
| `spy_pct_off_high`      | SPY % from its high                                     | `-2.9`    |
| `iwm_vs_spy_3mo`        | IWM vs SPY, 3mo %                                       | `2.6`     |
| `naaim`                 | NAAIM exposure index                                    | `87`      |
| `margin_debt_pct`       | Margin debt as % of market value                       | `1.78`    |
| `ipo_s1_30d`            | S-1 filings, trailing 30d                              | `255`     |
| `ipo_etf_vs_spy`        | IPO ETF vs SPY, %                                      | `15.7`    |
| `unemployment_pct`      | Unemployment rate, %                                    | `4.3`     |
| `sahm_rule`             | Sahm rule value                                        | `0.10`    |
| `jobless_claims_4wk`    | Jobless claims, 4-week MA                              | `214750`  |
| `housing_months_supply` | Housing months-supply                                 | `9.4`     |
| `xlf_vs_spy_lag`        | Financials (XLF) lag vs SPY, pts                      | `6.3`     |
| `copper_gold_3mo`       | Copper/Gold ratio, 3mo %                              | `28.8`    |

> The Doom Clock screenshot is often cropped, so some sub-indicators within a
> category may not be visible even though the category's `n/d` count is shown.
> Record the category count verbatim and **leave any unseen sub-value blank —
> never back-fill a guess.** Category colors map to `green`/`amber`/`red` in the
> dashboard's `SCAN.doomClock.cats`.

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
