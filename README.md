# Flow / Money Trail

An interactive, single-page educational site that teaches **institutional money
flow** — how large capital leaves a readable trail on the chart — using a live
**NVDA case study**.

**Live topics**

- What institutional money flow is (why big orders can't hide)
- **Impulse vs balance** candles — and why *structure comes before color*
- **Demand & supply zones**: how to draw them, the retested top/bottom, the
  candle signatures that show orders are still unfilled, and why tight
  risk/reward at a level beats prediction
- **Trend** structure (HH/HL/LL/LH) and the moment a trend breaks
- The **timeframe hierarchy** (monthly → weekly → 4h → 15m)
- An **interactive NVDA level map** (click a level on the ladder or the chart)
- A **trade autopsy** of a real losing setup, with a live expected-value
  calculator
- **The fix** — the same trade done right by the theory
- A pre-trade **checklist / readiness scorecard**

All NVDA levels, EMAs, Bollinger values and trade-ticket numbers are transcribed
from marked-up Yahoo Finance / TradingView charts (close of 2026-07-17). Candle
geometry in the schematics is illustrative; the levels drawn over it are real.
See [`CLAUDE.md`](CLAUDE.md) for the data-accuracy and editing rules.

## Tech

One self-contained `index.html` — HTML, CSS and vanilla JS, no build step and no
JS/CSS libraries (Google Fonts is the only external request, with graceful
system-font fallback). Deployed to GitHub Pages from `main` via
`.github/workflows/deploy.yml`.

## Run locally

Open `index.html` in a browser, or serve the folder:

```
python3 -m http.server 8000    # then visit http://localhost:8000
```

> **Not investment advice.** Educational content about reading market structure only.
