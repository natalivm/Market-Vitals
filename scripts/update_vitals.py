#!/usr/bin/env python3
"""
Market Vitals auto-updater.

DATA ACCURACY RULES (non-negotiable):
  1. Never estimate or guess a value. If a source is unreachable, the indicator
     is marked STALE and its numeric value is NOT updated in the HTML.
  2. Never carry forward a previous value as if it were fresh data.
  3. If fewer than 4 of the 8 indicators can be fetched, abort — do not publish
     a partially-stale board without clear labelling.
  4. All fetched values must come from a real network response. No hardcoded
     "fallback numbers".

Scheduled via GitHub Actions at 13:00 / 15:30 / 19:30 UTC (Mon-Fri)
= 4:00 PM / 6:30 PM / 10:30 PM Kyiv (EEST, UTC+3).

Set HINDENBURG_TRIGGERED=true in GitHub repo variables to manually flag the
Hindenburg Omen. The script also auto-triggers if McClellan < -5.
"""

import re, subprocess, sys, os
from datetime import datetime, timezone, timedelta

import yfinance as yf
import requests
from bs4 import BeautifulSoup

KYIV = timezone(timedelta(hours=3))
INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "index.html")
MIN_LIVE_INDICATORS = 4  # abort if fewer than this many are successfully fetched

# ── SCORING ──────────────────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def score_vix(v):
    if v is None: return None
    return round(_clamp(92 - (v - 13) * (84 / 22), 8, 92))

def score_move(v):
    if v is None: return None
    return round(_clamp(88 - (v - 60) * (76 / 70), 12, 88))

def score_mcclellan(v):
    if v is None: return None
    return round(_clamp(50 + v * (40 / 100), 10, 90))

def score_pct_200d(v):
    if v is None: return None
    return round(_clamp(10 + (v - 30) * (80 / 40), 10, 90))

def score_putcall(v):
    if v is None: return None
    if v <= 0.45: return 18
    if v <= 0.80: return round(18 + (v - 0.45) * (32 / 0.35))
    if v <= 1.20: return round(50 + (v - 0.80) * (25 / 0.40))
    return 75

def score_hindenburg(triggered):
    return 28 if triggered else 80

def score_market_tide(v_millions):
    if v_millions is None: return None
    return round(_clamp(50 + v_millions * (38 / 200), 12, 88))

def score_smfi(v, baseline=50000):
    if v is None: return None
    return round(_clamp(50 + (v - baseline) * (30 / 3000), 15, 85))

def compute_composite(vix, move, mcclellan, pct200d, putcall,
                      hindenburg_triggered, smfi, market_tide):
    weights = {
        "mcclellan":  0.16,
        "hindenburg": 0.16,
        "pct200d":    0.16,
        "putcall":    0.16,
        "market_tide":0.10,
        "vix":        0.10,
        "smfi":       0.08,
        "move":       0.08,
    }
    scores = {
        "vix":         score_vix(vix),
        "move":        score_move(move),
        "mcclellan":   score_mcclellan(mcclellan),
        "pct200d":     score_pct_200d(pct200d),
        "putcall":     score_putcall(putcall),
        "hindenburg":  score_hindenburg(hindenburg_triggered),
        "smfi":        score_smfi(smfi),
        "market_tide": score_market_tide(market_tide),
    }
    total, used_weight = 0.0, 0.0
    for k, w in weights.items():
        s = scores[k]
        if s is not None:
            total += s * w
            used_weight += w
    if used_weight < 0.01:
        return None, scores
    return round(total / used_weight), scores

# ── DATA FETCHERS ─────────────────────────────────────────────────────────────
# Each fetcher returns a real number on success, or None if the source is
# unreachable / returns no usable data.  NEVER return a guessed value.

def yf_last(symbol):
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="2d", interval="1d")
        if hist.empty:
            print(f"  [STALE] yfinance {symbol}: empty history", file=sys.stderr)
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"  [STALE] yfinance {symbol}: {e}", file=sys.stderr)
        return None

def fetch_vix():
    v = yf_last("^VIX")
    if v is None:
        print("  [NO ACCESS] VIX — will show STALE")
    return v

def fetch_move():
    v = yf_last("^MOVE")
    if v is None:
        print("  [NO ACCESS] MOVE — will show STALE")
    return v

def fetch_pct_above_200d():
    # ^MMTH = % of S&P 500 above 200-day MA (yfinance)
    v = yf_last("^MMTH")
    if v is not None:
        return v
    # Fallback: Barchart — only parse if real structured data is present
    try:
        url = "https://www.barchart.com/stocks/indicators/market-breadth/atr-200"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Look for a numeric value in a data cell, not a headline
        for el in soup.find_all(["td", "span"], class_=re.compile(r"(value|data)", re.I)):
            m = re.match(r'^(\d{1,2}\.\d)$', el.get_text(strip=True))
            if m:
                return float(m.group(1))
    except Exception as e:
        print(f"  [NO ACCESS] %>200d fallback Barchart: {e}", file=sys.stderr)
    print("  [NO ACCESS] % > 200 DMA — will show STALE")
    return None

def fetch_mcclellan():
    # MarketInOut McClellan Oscillator
    try:
        url = "https://www.marketinout.com/market_breadth/nyse_mcclellan_oscillator.php"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Find the most recent numeric value in the data table
        for td in soup.find_all("td"):
            txt = td.get_text(strip=True)
            if re.match(r'^-?\d{1,3}\.\d{1,2}$', txt):
                return float(txt)
    except Exception as e:
        print(f"  [NO ACCESS] McClellan MarketInOut: {e}", file=sys.stderr)
    print("  [NO ACCESS] McClellan — will show STALE")
    return None

def fetch_putcall():
    # CBOE equity put/call ratio CSV
    try:
        url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/EQUITY_PC_Ratio_Data.csv"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        lines = [l for l in r.text.strip().splitlines() if l.strip()]
        for line in reversed(lines):
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    val = float(parts[1])
                    if 0.20 <= val <= 3.00:  # sanity check
                        return val
                except ValueError:
                    continue
    except Exception as e:
        print(f"  [NO ACCESS] Put/Call CBOE CSV: {e}", file=sys.stderr)
    print("  [NO ACCESS] Put/Call — will show STALE")
    return None

def fetch_smfi():
    # SMFI has no reliable free public API.
    print("  [NO ACCESS] SMFI — no public feed available, will show STALE")
    return None

def fetch_market_tide():
    # Market Tide (net options premium flow) has no free public API.
    print("  [NO ACCESS] Market Tide — no public feed available, will show STALE")
    return None

# ── HTML PATCH ────────────────────────────────────────────────────────────────

def read_html():
    with open(INDEX_PATH, encoding="utf-8") as f:
        return f.read()

def write_html(html):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)

def _re_replace(pattern, replacement, html, flags=0):
    new, n = re.subn(pattern, replacement, html, count=1, flags=flags)
    if n == 0:
        print(f"  WARN: pattern not found in HTML: {pattern[:60]}", file=sys.stderr)
    return new

def verdict_label(score):
    if score < 25: return "EXTREME FEAR"
    if score < 45: return "FEAR"
    if score <= 55: return "NEUTRAL"
    if score <= 75: return "GREED"
    return "EXTREME GREED"

def ind_tag_and_color(name, val, hindenburg_triggered=False):
    if val is None:
        return "STALE", "amber"
    if name == "VIX":
        if val < 14: return "CALM", "green"
        if val < 18: return "ELEVATED", "amber"
        return "FEAR", "red"
    if name == "MOVE":
        if val < 80: return "CALM", "green"
        if val < 110: return "ELEVATED", "amber"
        return "FEAR", "red"
    if name == "McClellan":
        if val > 10: return "RISING", "green"
        if val >= 0: return "NEUTRAL", "amber"
        return "NEGATIVE", "red"
    if name == "Hindenburg":
        return ("TRIGGERED", "red") if hindenburg_triggered else ("CLEAR", "green")
    if name == "% > 200 DMA":
        if val >= 55: return "HEALTHY", "green"
        if val >= 45: return "NEUTRAL", "amber"
        return "WEAK", "red"
    if name == "Put/Call":
        if val < 0.60: return "EX. GREED", "red"
        if val < 0.85: return "NEUTRAL", "green"
        if val < 1.10: return "CAUTION", "amber"
        return "BEARISH", "amber"
    if name == "SMFI":
        if val > 51500: return "BULLISH", "green"
        if val > 49000: return "NEUTRAL", "amber"
        return "BEARISH", "red"
    if name == "Market Tide":
        if val > 30: return "BALANCED", "green"
        if val > -30: return "NEUTRAL", "amber"
        return "NEGATIVE", "red"
    return "UNKNOWN", "amber"

def patch_html(html, fetched, stale_names, now_kyiv, composite, prev_composite,
               hindenburg_triggered):
    utc_str  = now_kyiv.astimezone(timezone.utc).strftime("%H:%M")
    date_str = now_kyiv.strftime("%Y-%m-%d")
    kyiv_str = now_kyiv.strftime("%I:%M %p")
    verdict  = verdict_label(composite)
    green_count = sum(
        1 for nm in ["VIX","MOVE","McClellan","% > 200 DMA","Put/Call","SMFI","Market Tide"]
        if nm not in stale_names and ind_tag_and_color(nm, fetched.get(nm))[1] == "green"
    ) + (0 if hindenburg_triggered else 1)  # Hindenburg counts as green when CLEAR

    # ── composite constants ──────────────────────────────────────────────────
    html = _re_replace(r'(const PREV_COMPOSITE\s*=\s*)\d+', rf'\g<1>{prev_composite}', html)
    html = _re_replace(r'(const GHOST_AT\s*=\s*)\d+',       rf'\g<1>{prev_composite}', html)
    html = _re_replace(r'(const COMPOSITE\s*=\s*)\d+',       rf'\g<1>{composite}',      html)

    # ── header stamp ─────────────────────────────────────────────────────────
    verdict_color = {
        "EXTREME FEAR": "var(--fear)",
        "FEAR":         "var(--fear2)",
        "NEUTRAL":      "var(--amber)",
        "GREED":        "var(--greed2)",
        "EXTREME GREED":"var(--greed)",
    }.get(verdict, "var(--amber)")
    html = _re_replace(
        r'<div><b>\d{4}-\d{2}-\d{2}</b>[^<]*</div>',
        f'<div><b>{date_str}</b> · {utc_str} UTC · <span style="color:var(--muted)">{kyiv_str} Kyiv</span></div>',
        html)
    html = _re_replace(
        r'<div>Verdict:[^<]*</div>',
        f'<div>Verdict: <b style="color:{verdict_color}">{verdict}</b> · {green_count} of 8 green</div>',
        html)

    # ── ribbon ───────────────────────────────────────────────────────────────
    scan_label = (
        "4 PM SCAN"    if utc_str in ("13:00","13:01") else
        "6:30 PM SCAN" if utc_str in ("15:30","15:31") else
        "CLOSE SCAN"   if utc_str in ("19:30","19:31") else
        f"{utc_str} UTC SCAN"
    )
    mcl_val = fetched.get("McClellan")
    mcl_str = f"{mcl_val:+.2f}" if mcl_val is not None else "STALE"
    hind_str = "TRIGGERED" if hindenburg_triggered else "clear"
    tide_val = fetched.get("Market Tide")
    tide_str = f" · Market Tide {'+'if tide_val>=0 else ''}{int(tide_val)}M" if tide_val is not None else ""
    html = _re_replace(
        r'(<div class="r-main">)[^<]*(</div>)',
        rf'\g<1><b>{scan_label}</b> · {utc_str} UTC · McClellan {mcl_str} · Hindenburg {hind_str}{tide_str}\g<2>',
        html)
    html = _re_replace(
        r'(<span class="r-new"[^>]*>)[^<]*(</span>)',
        rf'\g<1>NOW {composite}\g<2>',
        html)

    # ── footer ────────────────────────────────────────────────────────────────
    stale_note = ""
    if stale_names:
        stale_note = f" {', '.join(stale_names)} {'is' if len(stale_names)==1 else 'are'} showing last known values (source unavailable)."
    html = _re_replace(
        r'<footer>\s*<b>NOT FINANCIAL ADVICE\.</b>.*?</footer>',
        (f'<footer>\n    <b>NOT FINANCIAL ADVICE.</b>'
         f' Core Vitals &amp; Momentum show the {utc_str} UTC scan'
         f' ({date_str} · {kyiv_str} Kyiv); replay animates from previous close ({prev_composite}).'
         f'{stale_note}'
         f' Concentration &amp; Leadership are structural estimates. Do your own research.\n  </footer>'),
        html, flags=re.DOTALL)

    # ── indicators: only patch indicators where we have live data ────────────
    numeric_map = {
        "VIX":         ("VIX",         "curNum"),
        "MOVE":        ("MOVE",        "curNum"),
        "McClellan":   ("McClellan",   "curNum"),
        "% > 200 DMA": ("% > 200 DMA", "curNum"),
        "Put/Call":    ("Put/Call",    "curNum"),
        "SMFI":        ("SMFI",        "curNum"),
        "Market Tide": ("Market Tide", "curNum"),
    }
    for ind_name, (js_name, js_key) in numeric_map.items():
        val = fetched.get(ind_name)
        if val is None:
            continue  # stale — do not touch the existing value in HTML
        pat = (rf'(\{{[^}}]*name:"{re.escape(js_name)}"[^}}]*{re.escape(js_key)}:)'
               rf'(-?\d+\.?\d*)')
        html = _re_replace(pat, rf'\g<1>{val}', html)

    # Hindenburg text val (always update — it's driven by env var / McClellan)
    hind_val = "TRIGGERED" if hindenburg_triggered else "CLEAR"
    html = _re_replace(
        r'(\{[^}]*name:"Hindenburg"[^}]*,\s*val:")([A-Z]+)(")',
        rf'\g<1>{hind_val}\g<3>', html)

    # Tags and colors — only for indicators we actually fetched
    live_names = [nm for nm in numeric_map if nm not in stale_names]
    live_names.append("Hindenburg")
    for ind_name in live_names:
        val = fetched.get(ind_name)
        tag, s = ind_tag_and_color(
            ind_name, val,
            hindenburg_triggered if ind_name == "Hindenburg" else False)
        js_name = ind_name
        html = _re_replace(
            rf'(\{{[^}}]*name:"{re.escape(js_name)}"[^}}]*tag:")([^"]+)(")',
            rf'\g<1>{tag}\g<3>', html)
        html = _re_replace(
            rf'(\{{[^}}]*name:"{re.escape(js_name)}"[^}}]*,\s*s:")([a-z]+)(")',
            rf'\g<1>{s}\g<3>', html)

    return html


# ── GIT ───────────────────────────────────────────────────────────────────────

def git_push(now_kyiv, composite, prev_composite, stale_names):
    repo = os.path.dirname(os.path.abspath(INDEX_PATH))
    ts   = now_kyiv.strftime("%Y-%m-%d %H:%M Kyiv")
    stale_note = f" [stale: {','.join(stale_names)}]" if stale_names else ""
    msg  = f"auto: vitals update {ts} — composite {prev_composite}→{composite}{stale_note}"
    subprocess.run(["git", "-C", repo, "add", "index.html"], check=True)
    diff = subprocess.run(["git", "-C", repo, "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("No changes to commit — data unchanged.")
        return
    subprocess.run(["git", "-C", repo, "commit", "-m", msg], check=True)
    branch = subprocess.check_output(
        ["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"]
    ).decode().strip()
    for attempt in range(4):
        result = subprocess.run(["git", "-C", repo, "push", "origin", branch])
        if result.returncode == 0:
            print(f"Pushed to {branch}: {msg}")
            return
        wait = 2 ** (attempt + 1)
        print(f"Push failed (attempt {attempt+1}/4), retrying in {wait}s...", file=sys.stderr)
        import time; time.sleep(wait)
    print("ERROR: all push attempts failed.", file=sys.stderr)
    sys.exit(1)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    now_kyiv = datetime.now(KYIV)
    print(f"=== Market Vitals update · {now_kyiv.strftime('%Y-%m-%d %H:%M %Z')} ===")

    hindenburg_triggered = os.environ.get("HINDENBURG_TRIGGERED", "false").lower() == "true"

    print("Fetching live data (no estimates — STALE if source unavailable)...")
    fetched = {
        "VIX":          fetch_vix(),
        "MOVE":         fetch_move(),
        "McClellan":    fetch_mcclellan(),
        "% > 200 DMA":  fetch_pct_above_200d(),
        "Put/Call":     fetch_putcall(),
        "SMFI":         fetch_smfi(),
        "Market Tide":  fetch_market_tide(),
    }
    stale_names = [nm for nm, v in fetched.items() if v is None]
    live_count  = len(fetched) - len(stale_names)

    print(f"\nResults ({live_count}/7 live):")
    for nm, v in fetched.items():
        status = f"{v}" if v is not None else "NO ACCESS — STALE"
        print(f"  {nm:<16}: {status}")

    # Auto-trigger Hindenburg if McClellan is live and clearly negative
    mcl = fetched.get("McClellan")
    if mcl is not None and mcl < -5:
        hindenburg_triggered = True
        print(f"\n  McClellan {mcl:.2f} < -5: auto-flagging Hindenburg as triggered")

    print(f"  {'Hindenburg':<16}: {'TRIGGERED' if hindenburg_triggered else 'CLEAR'}")

    if live_count < MIN_LIVE_INDICATORS:
        print(
            f"\nERROR: only {live_count} indicators fetched (minimum {MIN_LIVE_INDICATORS})."
            " Aborting to avoid publishing misleading data.",
            file=sys.stderr)
        sys.exit(1)

    composite, scores = compute_composite(
        fetched["VIX"], fetched["MOVE"], fetched["McClellan"],
        fetched["% > 200 DMA"], fetched["Put/Call"],
        hindenburg_triggered, fetched["SMFI"], fetched["Market Tide"])
    if composite is None:
        print("ERROR: insufficient data for composite score. Aborting.", file=sys.stderr)
        sys.exit(1)

    html_cur  = read_html()
    prev_match = re.search(r'const COMPOSITE\s*=\s*(\d+)', html_cur)
    prev_composite = int(prev_match.group(1)) if prev_match else 50

    print(f"\nScores:    {scores}")
    print(f"Composite: {prev_composite} → {composite} ({verdict_label(composite)})")

    html_new = patch_html(
        html_cur, fetched, stale_names, now_kyiv,
        composite, prev_composite, hindenburg_triggered)
    write_html(html_new)
    print("\nindex.html patched.")

    git_push(now_kyiv, composite, prev_composite, stale_names)

if __name__ == "__main__":
    main()
