#!/usr/bin/env python3
"""
parse_rotation.py — turn pasted Rotation Radar Bot feed text into a
schema-valid snapshot for data/rotation_history.json.

WHY THIS EXISTS
---------------
The Rotation Radar Bot posts each scan as 5-6 separate messages (CORE/SUB
INFLOWS + OUTFLOWS, BROAD MARKET, HIGH CONVICTION) and posts MULTIPLE scans a
day (pre-market / midday / close) with DIFFERENT numbers. Hand-transcribing
screenshots is where errors and scan-mixing creep in. This helper:

  * parses the pasted text of a whole day's thread,
  * groups posts by their footer timestamp into distinct scans,
  * selects ONE scan (default: the ~20:00 UTC close — the schema's record),
  * NEVER mixes sections from different scans (the Jun-1 footgun),
  * normalizes $K/$M/$B -> USD millions, distinguishes 0 from missing,
  * validates, and prints a ready-to-insert snapshot object.

USAGE
-----
  # paste/redirect the copied feed text, review the snapshot:
  python3 scripts/parse_rotation.py feed.txt
  cat feed.txt | python3 scripts/parse_rotation.py

  # see which scans the text contains:
  python3 scripts/parse_rotation.py feed.txt --list

  # pick a specific scan and append it to the history (chronological, deduped):
  python3 scripts/parse_rotation.py feed.txt --scan close --append data/rotation_history.json

ACCURACY RULES (per project CLAUDE.md)
  - Only confirmed feed numbers. A field the feed didn't show is omitted (not 0).
  - One scan only; if a section is missing for the chosen scan it is reported,
    never back-filled from another scan.
  - The editorial `read` field is NOT generated here — add it by hand.
"""
import argparse
import json
import re
import sys
from datetime import datetime

# ── text normalization ──────────────────────────────────────────────────────
def normalize(text: str) -> str:
    """Unicode minus/quotes/spaces -> ASCII so the regexes are simple."""
    return (text.replace("−", "-")      # − minus sign
                .replace("–", "-").replace("—", "-")  # – —
                .replace("“", '"').replace("”", '"')  # “ ”
                .replace("’", "'").replace(" ", " "))  # ’ nbsp


def parse_money(s):
    """'+$1.2B' -> 1200.0 ; '-$129.8M' -> -129.8 ; '$13.3K' -> 0.0133 ;
    '$0' -> 0.0 ; anything unparseable -> None (millions, matching the schema)."""
    if s is None:
        return None
    m = re.search(r"([+-]?)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([BMK]?)", s, re.I)
    if not m:
        return None
    sign = -1.0 if m.group(1) == "-" else 1.0
    val = float(m.group(2).replace(",", ""))
    mult = {"B": 1000.0, "M": 1.0, "K": 0.001, "": 1.0}[m.group(3).upper()]
    return round(sign * val * mult, 4)


def parse_pct(s):
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", s)
    return float(m.group(1)) if m else None


# ── feed structure ───────────────────────────────────────────────────────────
HEADER_RE = re.compile(r"ROTATION RADAR:\s*(.+)", re.I)
FOOTER_RE = re.compile(r"Rotation Radar\s*\|\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*UTC", re.I)
TICKER_RE = re.compile(r"^([A-Z]{2,6})\s*\(([^)]+)\)")
DAILY_RE = re.compile(r"1D:\s*([+-]?\d[\d.]*)%\s*\|\s*5D:\s*([+-]?\d[\d.]*)%\s*\|\s*20D:\s*([+-]?\d[\d.]*)%", re.I)
FLOW1_RE = re.compile(r"1D:\s*([+-]?\$?[\d,.]+\s*[BMK]?)", re.I)
FLOW5_RE = re.compile(r"5D:\s*([+-]?\$?[\d,.]+\s*[BMK]?)", re.I)
BENCH_RE = re.compile(r"Benchmark:\s*([A-Z]{2,6})", re.I)
SELLING_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*sectors? are selling", re.I)
CONV_RE = re.compile(r"^([A-Z]{2,6})\s*\(([^)]+)\)\s*\|\s*(\d+)/14 days .*?\|\s*([+-]?\$?[\d,.]+\s*[BMK]?)", re.I)


def section_of(header: str):
    """Map a header to (kind, tier, dir)."""
    h = header.upper()
    if "BROAD MARKET" in h or "NORMAL ROTATION" in h or "TWO-WAY" in h:
        return ("broad", None, None)
    if "HIGH CONVICTION" in h:
        return ("conviction", None, None)
    tier = "core" if "CORE" in h else "sub" if "SUB" in h else None
    direction = "in" if "INFLOW" in h else "out" if "OUTFLOW" in h else None
    if tier and direction:
        return ("flows", tier, direction)
    return ("other", None, None)


def parse_posts(text):
    """Split the pasted thread into posts. A post = a header, its body lines,
    and the footer timestamp that closes it."""
    posts, cur = [], None
    for raw in normalize(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith(("app", "rotation radar bot")) and not HEADER_RE.search(line):
            continue  # client chrome
        hm = HEADER_RE.search(line)
        if hm:
            cur = {"header": hm.group(1).strip(), "ts": None, "body": []}
            posts.append(cur)
            continue
        fm = FOOTER_RE.search(line)
        if fm:
            if cur is not None:
                cur["date"], cur["time"] = fm.group(1), fm.group(2)
                cur["ts"] = f"{fm.group(1)}T{fm.group(2)}:00Z"
            continue
        if cur is not None:
            cur["body"].append(line)
    return [p for p in posts if p["ts"]]


def parse_flow_post(post):
    """Yield flow dicts from a CORE/SUB INFLOWS/OUTFLOWS post."""
    _, tier, direction = section_of(post["header"])
    entries, cur = [], None
    for line in post["body"]:
        bm = BENCH_RE.search(line)
        if bm and "benchmark" in line.lower():
            d = DAILY_RE.search(line)
            cur = None
            yield ("benchmark", {"sym": bm.group(1), "d1": parse_pct(line.split("1D:")[1]) if "1D:" in line else None,
                                  **({"d1": float(d.group(1)), "d5": float(d.group(2)), "d20": float(d.group(3))} if d else {})})
            continue
        tk = TICKER_RE.match(line)
        if tk:
            cur = {"sym": tk.group(1), "name": tk.group(2).strip(), "tier": tier, "dir": direction}
            if re.search(r"NEW (IN|OUT)FLOW", line, re.I):
                cur["new"] = True
            cur["signal"] = None
            entries.append(cur)
            continue
        if cur is None:
            continue
        d = DAILY_RE.search(line)
        if d:
            cur["d1"], cur["d5"], cur["d20"] = float(d.group(1)), float(d.group(2)), float(d.group(3))
            if re.search(r"NEW (IN|OUT)FLOW", line, re.I):
                cur["new"] = True
            continue
        if line.lower().startswith("flow"):
            f1 = FLOW1_RE.search(line)
            f5 = FLOW5_RE.search(line)
            if f1:
                cur["f1"] = parse_money(f1.group(1))
            if f5:
                cur["f5"] = parse_money(f5.group(1))
            continue
        if "BUYING THE DIP" in line.upper():
            cur["signal"] = "BUYING THE DIP"
        elif "SELLING INTO STRENGTH" in line.upper():
            cur["signal"] = "SELLING INTO STRENGTH"
    for e in entries:
        # reorder keys to match the schema's house style
        o = {k: e[k] for k in ("sym", "name", "tier", "dir", "d1", "d5", "d20") if k in e}
        if "f1" in e:
            o["f1"] = e["f1"]
        if "f5" in e:
            o["f5"] = e["f5"]
        o["signal"] = e.get("signal")
        if e.get("new"):
            o["new"] = True
        yield ("flow", o)


def parse_broad_post(post):
    out = {"regime": post["header"].strip().upper(), "holding_up": []}
    sm = None
    collecting = False
    for line in post["body"]:
        s = SELLING_RE.search(line)
        if s:
            out["selling"], out["total"] = int(s.group(1)), int(s.group(2))
        if "holding up" in line.lower():
            collecting = True
            continue
        if collecting:
            tk = TICKER_RE.match(line)
            pct = parse_pct(line)
            if tk and pct is not None:
                out["holding_up"].append({"sym": tk.group(1), "name": tk.group(2).strip(), "chg": pct})
    return out


def parse_conviction_post(post):
    acc, dist, bucket = [], [], None
    for line in post["body"]:
        u = line.upper()
        if "ACCUMULATION" in u:
            bucket = acc; continue
        if "DISTRIBUTION" in u:
            bucket = dist; continue
        m = CONV_RE.match(line)
        if m and bucket is not None:
            bucket.append({"sym": m.group(1), "name": m.group(2).strip(),
                           "days": int(m.group(3)), "flow": parse_money(m.group(4))})
    return {"accumulation": acc, "distribution": dist}


# ── scan assembly ─────────────────────────────────────────────────────────────
def group_scans(posts, gap_min=45):
    """Cluster posts into scans by single-linkage on time: one scan's 5-6
    messages span a few minutes (e.g. 13:30 broad -> 14:01 flows), but the
    midday and close runs are hours apart. Posts within `gap_min` of the
    previous one belong to the same scan; the cluster is keyed by its latest
    post (so a close run posted 20:00 + 20:01 stays a single scan)."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    posts = sorted(posts, key=lambda p: p["ts"])
    clusters = []
    for p in posts:
        if clusters:
            prev = clusters[-1][-1]["ts"]
            if (datetime.strptime(p["ts"], fmt) - datetime.strptime(prev, fmt)).total_seconds() <= gap_min * 60:
                clusters[-1].append(p)
                continue
        clusters.append([p])
    scans = {}
    for cl in clusters:
        rep = cl[-1]  # latest post in the cluster represents the scan
        scans[rep["ts"]] = {"ts": rep["ts"], "date": rep["date"], "time": rep["time"], "posts": cl}
    return scans


def pick_scan(scans, want):
    """want: 'close' (default, latest / ~20:00 UTC), 'midday', 'premarket', or 'HH:MM'."""
    keys = sorted(scans)
    if re.fullmatch(r"\d{2}:\d{2}", want):
        match = [k for k in keys if scans[k]["time"].startswith(want[:2])]
        return scans[match[-1]] if match else None
    if want == "premarket":
        return scans[keys[0]]
    if want == "midday":
        mids = [k for k in keys if 11 <= int(scans[k]["time"][:2]) < 19]
        return scans[mids[-1]] if mids else scans[keys[len(keys) // 2]]
    # close: prefer an evening scan, else the last one of the day
    close = [k for k in keys if int(scans[k]["time"][:2]) >= 19]
    return scans[close[-1] if close else keys[-1]]


def build_snapshot(scan):
    snap = {"date": scan["date"], "ts": scan["ts"]}
    flows, missing = [], set(["CORE INFLOWS", "CORE OUTFLOWS", "SUB INFLOWS", "SUB OUTFLOWS", "BROAD", "CONVICTION"])
    seen = set()
    for post in scan["posts"]:
        kind, tier, direction = section_of(post["header"])
        if kind == "flows":
            seen.add(f"{tier.upper()} {'INFLOWS' if direction=='in' else 'OUTFLOWS'}".replace("CORE INFLOWS", "CORE INFLOWS"))
            seen.add(f"{tier.upper()} {'INFLOWS' if direction=='in' else 'OUTFLOWS'}")
            for typ, obj in parse_flow_post(post):
                if typ == "benchmark":
                    snap["benchmark"] = {k: v for k, v in obj.items() if v is not None}
                elif typ == "flow":
                    flows.append(obj)
        elif kind == "broad":
            seen.add("BROAD")
            snap.update(parse_broad_post(post))
        elif kind == "conviction":
            seen.add("CONVICTION")
            snap["conviction"] = parse_conviction_post(post)
    snap["flows"] = flows
    return snap, sorted(missing - seen)


# ── validation ────────────────────────────────────────────────────────────────
def validate(snap):
    errs, warns = [], []
    syms = [f["sym"] for f in snap["flows"]]
    dups = sorted({s for s in syms if syms.count(s) > 1})
    if dups:
        errs.append(f"duplicate tickers within one scan: {dups} (scan-mixing?)")
    for f in snap["flows"]:
        if any(k not in f for k in ("d1", "d5", "d20")):
            warns.append(f"{f['sym']}: missing a 1D/5D/20D value")
        if f.get("signal") not in (None, "BUYING THE DIP", "SELLING INTO STRENGTH"):
            errs.append(f"{f['sym']}: bad signal {f.get('signal')!r}")
    if "selling" in snap and "total" in snap and snap["selling"] > snap["total"]:
        errs.append(f"selling {snap['selling']} > total {snap['total']}")
    if not snap["flows"]:
        errs.append("no flows parsed — check the input format")
    return errs, warns


def append_to_history(snap, path):
    with open(path) as fh:
        doc = json.load(fh)
    hist = [s for s in doc.get("history", []) if s.get("date") != snap["date"]]
    hist.append(snap)
    hist.sort(key=lambda s: s["date"])
    doc["history"] = hist
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser(description="Parse Rotation Radar feed text into a snapshot.")
    ap.add_argument("input", nargs="?", help="feed text file (default: stdin)")
    ap.add_argument("--scan", default="close", help="which scan: close (default) | midday | premarket | HH:MM")
    ap.add_argument("--list", action="store_true", help="list the scans/sections found, then exit")
    ap.add_argument("--append", metavar="JSON", help="append the snapshot to this history file (deduped by date)")
    args = ap.parse_args()

    text = open(args.input).read() if args.input else sys.stdin.read()
    posts = parse_posts(text)
    if not posts:
        sys.exit("No Rotation Radar posts found (need header lines + 'Rotation Radar | <date> <time> UTC' footers).")
    scans = group_scans(posts)

    if args.list:
        for ts in sorted(scans):
            secs = [section_of(p["header"])[0] + (f"/{section_of(p['header'])[1]}/{section_of(p['header'])[2]}"
                    if section_of(p["header"])[0] == "flows" else "") for p in scans[ts]["posts"]]
            print(f"{ts}  ({len(scans[ts]['posts'])} posts): {', '.join(secs)}")
        return

    scan = pick_scan(scans, args.scan)
    if scan is None:
        sys.exit(f"No scan matched --scan {args.scan!r}. Available: {', '.join(sorted(scans))}")
    snap, missing = build_snapshot(scan)
    errs, warns = validate(snap)

    print(f"# scan {scan['ts']}  ({len(scan['posts'])} posts, {len(snap['flows'])} flows)", file=sys.stderr)
    if missing:
        print(f"# MISSING sections (NOT back-filled): {', '.join(missing)}", file=sys.stderr)
    for w in warns:
        print(f"# warn: {w}", file=sys.stderr)
    for e in errs:
        print(f"# ERROR: {e}", file=sys.stderr)
    if errs:
        sys.exit("Refusing to emit a broken snapshot — fix the input and retry.")

    if args.append:
        append_to_history(snap, args.append)
        print(f"# appended {snap['date']} to {args.append}", file=sys.stderr)
    else:
        print(json.dumps(snap, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
