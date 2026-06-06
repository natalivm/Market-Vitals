#!/usr/bin/env python3
"""
compare_rotation.py — does the self-sourced bot's data line up with the
hand-transcribed Trading Apologist numbers?

Compares the OBJECTIVE, checkable fields — per-sector price performance
(d1/d5/d20) and the SPY benchmark — between:
  * what fetch_rotation would compute from Yahoo *as of* a past date, and
  * the stored snapshot for that date in data/rotation_history.json.

Flows/signals are intentionally NOT compared: those are our derivation
(shares-outstanding deltas) vs the feed's proprietary flow data — they're
expected to differ. Price is the apples-to-apples check.

USAGE (run locally — needs network for Yahoo; this repo's sandbox is locked)
  python3 scripts/compare_rotation.py --asof 2026-06-05
  python3 scripts/compare_rotation.py --asof 2026-06-05 --tol 0.25
  python3 scripts/compare_rotation.py --asof 2026-06-05 --mock   # offline self-test
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_rotation import REGISTRY  # noqa

YH = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"
UA = {"User-Agent": "Mozilla/5.0 (Market-Vitals compare)"}
MOCK = False


def fetch_series(sym):
    """{ 'YYYY-MM-DD': close } from Yahoo daily closes (or synthetic in --mock)."""
    if MOCK:
        return _mock_series(sym)
    try:
        res = json.loads(urllib.request.urlopen(
            urllib.request.Request(YH.format(sym=sym), headers=UA), timeout=20).read())["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        return {datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"): c
                for t, c in zip(ts, cl) if c is not None}
    except Exception:
        return None


def _pct(a, b):
    return round((a / b - 1.0) * 100.0, 2) if b else None


def asof_perf(series, asof):
    """d1/d5/d20 as of the last trading day <= asof."""
    dates = sorted(d for d in series if d <= asof)
    if not dates:
        return None
    closes = [series[d] for d in dates]
    i = len(closes) - 1
    back = lambda n: closes[i - n] if i - n >= 0 else None
    return {"d1": _pct(closes[i], back(1)), "d5": _pct(closes[i], back(5)), "d20": _pct(closes[i], back(20))}


def main():
    global MOCK
    ap = argparse.ArgumentParser(description="Compare bot-computed price perf vs stored snapshot.")
    ap.add_argument("--asof", required=True, help="date present in the history file, e.g. 2026-06-05")
    ap.add_argument("--history", default="data/rotation_history.json")
    ap.add_argument("--tol", type=float, default=0.30, help="match tolerance in percentage points (default 0.30)")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    MOCK = args.mock

    hist = json.load(open(args.history)).get("history", [])
    snap = next((s for s in hist if s.get("date") == args.asof), None)
    if not snap:
        sys.exit(f"No stored snapshot for {args.asof}. Have: {', '.join(s['date'] for s in hist)}")

    rows = [("SPY", snap["benchmark"])] + [(f["sym"], f) for f in snap["flows"]]
    print(f"Comparing bot (Yahoo, as of {args.asof}) vs stored Trading Apologist numbers")
    print(f"{'sym':5} {'horizon stored→bot (Δ)':<44} match")
    print("-" * 66)
    errs = {"d1": [], "d5": [], "d20": []}
    misses = 0
    fetched = 0
    for sym, stored in rows:
        series = fetch_series(sym)
        if not series:
            print(f"{sym:5} no data")
            continue
        bot = asof_perf(series, args.asof)
        if not bot:
            print(f"{sym:5} no close on/before {args.asof}")
            continue
        fetched += 1
        cells, ok_all = [], True
        for h in ("d1", "d5", "d20"):
            sv, bv = stored.get(h), bot.get(h)
            if sv is None or bv is None:
                cells.append(f"{h}: n/a"); continue
            d = round(bv - sv, 2)
            errs[h].append(abs(d))
            ok = abs(d) <= args.tol
            ok_all = ok_all and ok
            cells.append(f"{h} {sv:+.2f}→{bv:+.2f} ({d:+.2f}){'' if ok else '!'}")
        if not ok_all:
            misses += 1
        print(f"{sym:5} {' '.join(cells):<44} {'✓' if ok_all else '✗'}")

    print("-" * 66)
    for h in ("d1", "d5", "d20"):
        if errs[h]:
            mae = sum(errs[h]) / len(errs[h])
            print(f"{h}: mean abs Δ = {mae:.3f} pp  (n={len(errs[h])})")
    print(f"\n{fetched - misses}/{fetched} sectors match within ±{args.tol} pp on all horizons.")
    print("(Flows & signals are our own derivation — not compared here.)")


def _mock_series(sym):
    s = sum(ord(c) for c in sym)
    base = 50 + s % 200
    out = {}
    for i in range(40):
        day = f"2026-04-{(i % 28) + 1:02d}" if i < 28 else f"2026-05-{(i - 28) + 1:02d}"
        out[day] = round(base * (1 + ((s * (i + 3)) % 17 - 8) / 200.0), 2)
    out["2026-06-05"] = base * 1.01
    out["2026-06-04"] = base
    return out


if __name__ == "__main__":
    main()
