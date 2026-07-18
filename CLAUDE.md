# Flow / Money Trail — Project Rules

An interactive educational website teaching **institutional money flow**: how big
capital leaves a readable trail on the chart (impulse vs balance candles, demand
and supply zones, trend structure, timeframe hierarchy), taught through a live
**NVDA case study** with a trade autopsy.

Single static page, no build step. Deployed to GitHub Pages from `main`.

## DATA ACCURACY — NON-NEGOTIABLE

This is educational content, but the NVDA numbers must stay honest.

1. **Every price level, EMA, Bollinger value and trade-ticket number comes from a
   real, cited source** — the user's marked-up Yahoo Finance / TradingView charts
   (close of 2026-07-17). Never invent, round, or "approximate" a market number.
2. If you don't have a real value for something, **omit it or label it clearly**
   (e.g. `low-TF` for levels only visible on a timeframe we don't have a shot of).
   Do not fill a gap with a guess.
3. **Candle geometry in the schematic charts is illustrative** and is labelled as
   such. The *horizontal levels* drawn over it are real. Keep that distinction
   visible to the reader — never present a schematic as real OHLC.
4. This is **not investment advice**. The footer disclaimer must stay on the page.

## Project structure

```
index.html          — the entire site (HTML + CSS + vanilla JS, self-contained)
CLAUDE.md           — this file
README.md           — project overview
.github/workflows/
  deploy.yml        — GitHub Pages deploy (push to main). Do not modify casually.
.nojekyll           — serve files verbatim (no Jekyll processing)
```

No external JS/CSS libraries. Google Fonts is the only external request; the page
degrades gracefully to system fonts if it's blocked.

## Editing the NVDA data — read the DATA block only

All case-study data lives in one place: the `const NVDA = {...}` object and the
`CLOSES` array inside the `<script>` block near the bottom of `index.html`
(look for the `══ DATA ══` banner). Prices, zones, levels, Bollinger values and
the schematic candle series are all there. The render functions below don't need
touching for a data update.

- `NVDA.levels[]` — each marked level: `px`, `disp` (label), `kind`
  (`sup`/`dem`/`neu`/`now`), `conf` (`true` = confirmed on a chart we have,
  `false` = lower-timeframe, shown with a `low-TF` badge), `name`, `detail`.
- `NVDA.zones[]` — the demand/supply bands.
- `NVDA.bb` — weekly Bollinger (21,2).
- `CLOSES[]` — schematic weekly closes (illustrative geometry, not real OHLC);
  the last candle is overridden with the real O/H/L/C.

## Design system (keep consistent)

Dark theme. CSS variables at `:root` — do not hardcode colors:
`--demand` green (#3DDC97) = buyers/support, `--supply` red (#FF5C6A) =
sellers/resistance, `--amber` (#F2B441) = balance/neutral/wait, `--violet`
(#8B5CF6) = accent/UI. Fonts: Unbounded (display), Inter (body),
JetBrains Mono (numbers/labels). Respect `prefers-reduced-motion`.

## Verifying changes

Render locally in headless Chromium before committing anything non-trivial:
check the console is clean (a blocked Google-Fonts request is expected offline),
the ladder / chart / EV calculator / toggles all respond, and the layout holds
at mobile width (≤900px collapses to a single column). Chromium is at
`/opt/pw-browsers/chromium-*/chrome-linux/chrome` with Playwright globally
installed.
