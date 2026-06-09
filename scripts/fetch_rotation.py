#!/usr/bin/env python3
"""
fetch_rotation.py — self-sourced Rotation Radar bot.

Pulls daily ETF prices (Yahoo) for the fixed universe, derives net flows from
day-over-day shares-outstanding deltas, classifies signals/regime, and writes a
snapshot that conforms to schema/rotation_snapshot.schema.json — the SAME shape
parse_rotation.py emits and the dashboard renders.

IMPORTANT — provenance & accuracy (per project CLAUDE.md):
  * These are OUR computed numbers, not the Trading Apologist feed's. The
    methodology is documented below; nothing is invented.
  * Prices/perf are sourced live. NET FLOWS are derived from shares-outstanding
    deltas and BOOTSTRAP over time: f1 needs yesterday's reading, f5 needs five.
    Until the flow-state cache has history, f1/f5 (and signals/conviction) are
    omitted rather than guessed.
  * If fewer than MIN_COVERAGE tickers return live prices, the run ABORTS and
    writes nothing — a missing day beats a misleading one.

Runs in CI (open network); this repo's sandbox is network-locked, so use --mock
to exercise the full pipeline offline.

USAGE
  python3 scripts/fetch_rotation.py --dry-run            # fetch + print snapshot
  python3 scripts/fetch_rotation.py --append data/rotation_history.json
  python3 scripts/fetch_rotation.py --mock --dry-run     # offline, synthetic data
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_rotation import UNIVERSE, REGISTRY, validate, append_to_history  # reuse

YH_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2mo&interval=1d"
YH_QS = ("https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
         "?modules=defaultKeyStatistics")
UA = {"User-Agent": "Mozilla/5.0 (Market-Vitals rotation bot)"}
MIN_COVERAGE = 30          # of 41 tickers; abort below this
SELLOFF, RALLY = 0.66, 0.34  # breadth thresholds for the regime label
SHARES_CACHE = "data/rotation_shares.json"

MOCK = False


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode())


def _chart(sym):
    if MOCK:
        return _mock_chart(sym)
    try:
        return _get(YH_CHART.format(sym=sym))["chart"]["result"][0]
    except Exception:
        return None


def fetch_closes(sym):
    """(closes oldest→newest, last_trading_date) or (None, None) on failure."""
    res = _chart(sym)
    if not res:
        return None, None
    q = res["indicators"]["quote"][0]["close"]
    ts = res.get("timestamp", [])
    pairs = [(t, c) for t, c in zip(ts, q) if c is not None]
    if not pairs:
        return None, None
    closes = [c for _, c in pairs]
    last_date = datetime.fromtimestamp(pairs[-1][0], timezone.utc).strftime("%Y-%m-%d")
    return closes, last_date


def fetch_shares(sym):
    """Current shares outstanding (snapshot), or None. Best-effort — Yahoo's ETF
    coverage is spotty; flows degrade gracefully to omitted when missing."""
    if MOCK:
        return _mock_shares(sym)
    try:
        s = _get(YH_QS.format(sym=sym))["quoteSummary"]["result"][0]["defaultKeyStatistics"]
        return s.get("sharesOutstanding", {}).get("raw")
    except Exception:
        return None


# ── derivation ────────────────────────────────────────────────────────────────
def _pct(a, b):
    return round((a / b - 1.0) * 100.0, 2) if b else None


def perf(closes):
    last = closes[-1]
    nth = lambda n: closes[-1 - n] if len(closes) > n else None
    return {"d1": _pct(last, nth(1)), "d5": _pct(last, nth(5)), "d20": _pct(last, nth(20))}, last


def load_cache(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}


def derive_flows(sym, price, shares, cache):
    """Net flow (USD millions) from shares-outstanding deltas, using our own
    rolling cache. f1 = Δshares(1d)·price ; f5 = Δshares(5d)·price. Returns
    (f1, f5) with None where insufficient history."""
    hist = cache.get(sym, [])  # list of [date, shares, price], oldest→newest
    f1 = f5 = None
    if shares is not None and hist:
        if hist[-1][1]:
            f1 = round((shares - hist[-1][1]) * price / 1e6, 1)
        if len(hist) >= 5 and hist[-5][1]:
            f5 = round((shares - hist[-5][1]) * price / 1e6, 1)
    return f1, f5


def update_cache(cache, sym, date, shares, price):
    if shares is None:
        return
    h = cache.setdefault(sym, [])
    if h and h[-1][0] == date:
        h[-1] = [date, shares, price]
    else:
        h.append([date, shares, price])
    cache[sym] = h[-21:]  # keep ~a month


def classify(dir_, f5):
    if f5 is None:
        return None
    if dir_ == "out" and f5 > 0:
        return "BUYING THE DIP"      # price down, money in
    if dir_ == "in" and f5 < 0:
        return "SELLING INTO STRENGTH"  # price up, money out
    return None


def prev_snapshot(history_path):
    try:
        hist = json.load(open(history_path)).get("history", [])
        return hist[-1] if hist else None
    except Exception:
        return None


def conviction_from_history(history_path, today_flows):
    """14-day streaks: consecutive days each sym carried the same signal,
    cumulative |f5| over the streak. Uses our stored history + today."""
    try:
        hist = json.load(open(history_path)).get("history", [])
    except Exception:
        hist = []
    days = ([{f["sym"]: f for f in s.get("flows", [])} for s in hist[-13:]]
            + [{f["sym"]: f for f in today_flows}])
    acc, dist = [], []
    for sym, name, _ in UNIVERSE:
        for sig, bucket in (("BUYING THE DIP", acc), ("SELLING INTO STRENGTH", dist)):
            streak, flow = 0, 0.0
            for day in reversed(days):
                f = day.get(sym)
                if f and f.get("signal") == sig:
                    streak += 1
                    flow += abs(f.get("f5") or 0)
                else:
                    break
            if streak >= 5:
                bucket.append({"sym": sym, "name": name, "days": min(streak, 14), "flow": round(flow, 1)})
    acc.sort(key=lambda c: -c["days"]); dist.sort(key=lambda c: -c["days"])
    return {"accumulation": acc, "distribution": dist}


# ── assembly ──────────────────────────────────────────────────────────────────
def build(history_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache = load_cache(SHARES_CACHE)
    prev = prev_snapshot(history_path)
    prev_dir = {f["sym"]: f.get("dir") for f in (prev or {}).get("flows", [])} if prev else {}

    bench_closes, data_date = fetch_closes("SPY")
    if not bench_closes:
        sys.exit("ABORT: benchmark (SPY) unavailable — writing nothing.")
    # Date the snapshot by the latest TRADING day, not the calendar day, so a
    # weekend/holiday run doesn't mislabel Friday's close as "today".
    date = data_date
    if data_date != today:
        print(f"# NOTE: latest close is {data_date}, not {today} (market closed today?) — "
              f"snapshot dated {data_date}.", file=sys.stderr)
    bperf, _ = perf(bench_closes)

    flows, fetched = [], 0
    for sym, name, tier in UNIVERSE:
        closes, _ = fetch_closes(sym)
        if not closes:
            continue
        fetched += 1
        p, last = perf(closes)
        shares = fetch_shares(sym)
        f1, f5 = derive_flows(sym, last, shares, cache)
        update_cache(cache, sym, date, shares, last)
        direction = "in" if (p["d1"] or 0) >= 0 else "out"
        row = {"sym": sym, "name": name, "tier": tier, "dir": direction,
               "d1": p["d1"], "d5": p["d5"], "d20": p["d20"]}
        if f1 is not None:
            row["f1"] = f1
        if f5 is not None:
            row["f5"] = f5
        row["signal"] = classify(direction, f5)
        if prev_dir.get(sym) == "out" and direction == "in":
            row["new"] = True
        flows.append(row)

    if fetched < MIN_COVERAGE:
        sys.exit(f"ABORT: only {fetched}/{len(UNIVERSE)} tickers fetched (< {MIN_COVERAGE}). Writing nothing.")

    selling = sum(1 for f in flows if f["dir"] == "out")
    ratio = selling / len(flows)
    regime = ("BROAD MARKET SELL-OFF" if ratio >= SELLOFF
              else "BROAD MARKET RALLY" if ratio <= RALLY
              else "TWO-WAY SECTOR ROTATION")
    snap = {
        "date": date,
        "ts": f"{date}T20:00:00Z",   # session close stamp, not the run clock
        "regime": regime,
        "selling": selling,
        "total": len(flows),
        "benchmark": {"sym": "SPY", **bperf},
        "flows": flows,
    }
    conv = conviction_from_history(history_path, flows)
    if conv["accumulation"] or conv["distribution"]:
        snap["conviction"] = conv
    if regime == "BROAD MARKET SELL-OFF":
        up = sorted((f for f in flows if (f["d1"] or 0) > 0), key=lambda f: -(f["d1"] or 0))[:5]
        if up:
            snap["holding_up"] = [{"sym": f["sym"], "name": f["name"], "chg": f["d1"]} for f in up]
    return snap, cache


def main():
    global MOCK
    ap = argparse.ArgumentParser(description="Self-sourced Rotation Radar snapshot bot.")
    ap.add_argument("--append", metavar="JSON", help="append snapshot to this history file (deduped by date)")
    ap.add_argument("--dry-run", action="store_true", help="print the snapshot, don't write")
    ap.add_argument("--mock", action="store_true", help="use synthetic data (offline pipeline test)")
    ap.add_argument("--force", action="store_true", help="allow overwriting an existing date in history")
    args = ap.parse_args()
    MOCK = args.mock

    history_path = args.append or "data/rotation_history.json"
    snap, cache = build(history_path)

    errs, warns = validate(snap, require_complete=True)
    for w in warns:
        print(f"# warn: {w}", file=sys.stderr)
    if errs:
        for e in errs:
            print(f"# ERROR: {e}", file=sys.stderr)
        sys.exit("ABORT: snapshot failed schema validation — writing nothing.")

    flow_n = sum(1 for f in snap["flows"] if "f5" in f)
    print(f"# {snap['date']} {snap['regime']} · {len(snap['flows'])} sectors · "
          f"{flow_n} with flow · {snap['selling']}/{snap['total']} selling", file=sys.stderr)

    if args.dry_run or not args.append:
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        return

    # Market-closed guard: if the latest close is NOT today (weekend/holiday, or
    # a run before today's session has closed), the snapshot belongs to an
    # earlier day that's already on record — never re-derive or overwrite it.
    # This is what actually prevents stale clobber, so it holds even with --force.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if snap["date"] != today:
        print(f"# market closed {today} (latest close is {snap['date']}, already recorded) — "
              f"nothing to write.", file=sys.stderr)
        return

    try:
        existing = {s["date"] for s in json.load(open(args.append)).get("history", [])}
    except Exception:
        existing = set()
    # Same-day entry already present (an intraday reading, or a re-run). The
    # scheduled CLOSE run is authoritative and passes --force to REPLACE it
    # (append_to_history dedupes by date). A plain manual --append stays guarded.
    if snap["date"] in existing and not args.force:
        sys.exit(f"ABORT: {snap['date']} already in {args.append} — use --force to replace it "
                 f"(the scheduled close run does; this guards ad-hoc manual runs).")
    append_to_history(snap, args.append)
    if not MOCK:
        json.dump(cache, open(SHARES_CACHE, "w"), indent=2)
    verb = "replaced" if snap["date"] in existing else "appended"
    print(f"# {verb} {snap['date']} in {args.append}", file=sys.stderr)


# ── offline mock data (deterministic) ─────────────────────────────────────────
def _seed(sym):
    return sum(ord(c) for c in sym)


def _mock_closes(sym):
    s = _seed(sym)
    base = 50 + s % 200
    return [round(base * (1 + ((s * (i + 3)) % 17 - 8) / 200.0), 2) for i in range(22)]


def _mock_chart(sym):
    closes = _mock_closes(sym)
    base = int(datetime(2026, 5, 8, 20, 0, tzinfo=timezone.utc).timestamp())
    ts = [base + i * 86400 for i in range(len(closes))]   # ends 2026-05-29 (a weekday)
    return {"timestamp": ts, "indicators": {"quote": [{"close": closes}]}}


def _mock_shares(sym):
    return float((_seed(sym) % 50 + 10) * 1_000_000)


if __name__ == "__main__":
    main()
