# Rotation Radar — Feed Contract (v2)

A spec for rebuilding the Rotation Radar Bot so it emits **structured,
consistent data every day** that captures with the same lines, never drops a
section, and maps 1:1 to what the dashboard renders.

> **Core principle:** the bot's output, our storage (`data/rotation_history.json`),
> and the dashboard's input are the **same shape**. No transformation, nothing
> to lose. The contract is the JSON Schema in
> [`schema/rotation_snapshot.schema.json`](../schema/rotation_snapshot.schema.json).

---

## 1. Deliver two layers from one source

1. **Machine record (source of truth)** — one JSON object per day, conforming to
   the schema. Posted as a file attachment / gist / `GET /rotation/latest.json` /
   webhook. This is what gets stored.
2. **Human summary** — the readable channel message, **generated from that JSON**
   so the two can never drift.

If the bot can only post text, use the [compact text block](#4-compact-text-fallback)
— a single message with a fixed grammar — instead of today's 5-6 prose posts.

## 2. Rules that make it un-missable

- **One record per day = the 20:00 UTC close.** Intraday scans, if posted at all,
  carry `scan=midday`/`premarket` and are **never** written to history.
- **Fixed universe, fixed order, every day.** Emit all 41 tickers
  ([registry below](#5-fixed-universe-registry)) in the same sequence. A missing
  sector becomes impossible to overlook because the line count is constant.
- **Explicit `null` vs `0`.** A flow the model didn't compute is `null`; a real
  zero is `0`. Never an omitted line.
- **One flows table.** Drop the separate INFLOWS/OUTFLOWS posts; `dir` is a field
  on each row. The `BUYING THE DIP` / `SELLING INTO STRENGTH` signal carries the
  price-vs-flow divergence.
- **One unit: USD millions, numeric.** No inline `$K/$M/$B` to parse
  (`1200` = $1.2B, `0.15` = $150K, `-0.0133` = −$13.3K).
- **Breadth on the fixed universe.** `selling`/`total` use the same N you list
  (e.g. `21/41`), not a drifting `/26`.
- **Idempotency.** Header carries `date`, `ts`, `scan`, `schema_version`. Re-posts
  with the same `(date, scan)` replace, never duplicate.

## 3. What to keep, drop, derive

| Today | Verdict | Why |
|---|---|---|
| CORE/SUB × IN/OUT (4 posts) | **merge → 1 flows table** | `dir` becomes a field |
| Benchmark (SPY) | **keep** | dashboard needs it |
| 14-day conviction | **keep** (signed in feed, stored as magnitude + bucket) | conviction panel |
| Broad-market regime + breadth | **keep** (1 header line) | the banner |
| "Sectors Holding Up" | **drop → derive** | = `d1 > 0` while regime is a sell-off |
| Pre-market / midday scans | **drop from the record** | only the close is logged |
| Emoji/prose signal lines | **drop → code** (`BTD`/`SIS`) | machine-stable |

## 4. Compact text fallback

One fenced message per day. Columns are space-separated; `name`/`tier` come from
the [registry](#5-fixed-universe-registry) so rows stay short and fixed-width-ish.

```
ROTATION RADAR | schema=2 | date=2026-06-01 | scan=close | ts=2026-06-01T20:00:00Z
regime=BROAD MARKET SELL-OFF | selling=21 | total=41
SPY | d1=-0.12 | d5=1.33 | d20=4.85
# sym dir d1 d5 d20 f1 f5 signal new      (signal: BTD|SIS|. · new: NEW|. · flow: null if absent)
XLK in +2.44 +8.48 +20.89 152.0 144.3 . .
XHB in +0.63 +3.26 -1.73 15.4 25.2 . NEW
XLY out -2.19 -0.80 -0.34 84.7 695.1 BTD .
GDX in -3.15 +1.94 -0.51 -0.0133 -36.4 . .
DRAM in +7.64 +28.80 +68.35 null null . .
# ... all 41 tickers, same order, every day ...
# conviction14d  (signed: +acc / -dist)
XLC acc 7 +1200
XLK dist 7 -2000
IAI dist 6 -640.8
```

`scripts/parse_rotation.py` ingests this directly (auto-detected by the
`ROTATION RADAR | schema=` header) and writes a schema-valid snapshot.

## 5. Fixed universe registry

41 tickers, fixed order. `name` + `tier` are constant per symbol, so the daily
feed only carries the changing numbers. (Source of truth in
`scripts/parse_rotation.py :: UNIVERSE`.)

### Core sectors (19)
| sym | name | sym | name |
|---|---|---|---|
| XLK | Technology | XLC | Communications |
| XLF | Financials | XBI | Biotech |
| XLE | Energy | XME | Metals & Mining |
| XLV | Healthcare | XAR | Aerospace & Defense |
| XLY | Consumer Discretionary | XHB | Homebuilders |
| XLP | Consumer Staples | XOP | Oil & Gas Exploration |
| XLI | Industrials | XRT | Retail |
| XLU | Utilities | XTN | Transportation |
| XLB | Materials | XHE | Healthcare Equipment |
| XLRE | Real Estate | | |

### Sub-sectors (22)
| sym | name | sym | name |
|---|---|---|---|
| SMH | Semiconductors | BOTZ | Robotics & AI |
| IGV | Software | DRAM | Memory |
| IAI | Broker-Dealers | PBW | Clean Energy |
| KBE | Banking | ICLN | Clean Energy (iShares) |
| KRE | Regional Banking | TAN | Solar |
| OIH | Oil Services | JETS | Airlines |
| COPX | Copper Miners | MSOS | Cannabis |
| GDX | Gold Miners | HACK | Cybersecurity |
| SLX | Steel | WCLD | Cloud Computing |
| REMX | Rare Earth & Crit. Min. | URA | Uranium |
| LIT | Lithium & Battery | BITO | Bitcoin Futures |

## 6. Validation

```
python3 scripts/parse_rotation.py --validate data/rotation_history.json
```
checks every stored snapshot against this contract (unique tickers per scan,
valid signals/tiers/dirs, `selling ≤ total`, required fields). External tooling
can validate the same data against `schema/rotation_snapshot.schema.json` with any
JSON-Schema validator (ajv, python-jsonschema, …).
