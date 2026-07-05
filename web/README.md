# 200WMA Scanner — Web Frontend

A small Next.js (App Router, TypeScript) frontend that **reads and renders** the
pre-computed JSON emitted by the Python 200-week-moving-average scanner
(`../python/wma200_scanner.py`). It does **not** recompute any of the 200WMA
maths — it only visualizes the scanner's output.

The look mirrors the scanner's self-contained HTML report: dark theme
(`#0b0f14` background, `#121924` cards), monospace type, and green/red/amber
accents.

## What it renders

- **Breadth strip** — tiles for % above 200WMA (color-banded), crossed up,
  crossed down, signal count, and assets with a full MA window.
- **Signal cards** — a responsive grid. Each card shows the ticker, a colored
  badge for the signal type, an inline-SVG sparkline of price vs the 200-week MA
  (dashed), and the stats block (price, 200WMA, distance %, 13-week slope %).
- **Slope emphasis** — the 13-week MA slope is highlighted green (positive) or
  red (negative) with a plain-language note, because it's the qualifier that
  separates a healthy cyclical dip (buy) from a falling-knife / structural break
  (trap).

## Run it

```bash
cd web
npm install
npm run dev      # http://localhost:3000
```

Other scripts: `npm run build`, `npm start`, `npm run typecheck`.

## Data source

The skeleton reads a bundled sample at `public/sample-signals.json` (4 signals,
one of each signal type, each with a ~20-point chart series).

To wire in **real** data, edit `loadScan()` in [`app/page.tsx`](./app/page.tsx).
It has clearly-commented seams for:

- reading the real `wma200_signals.json` (have the Python job write it into
  `web/public/`),
- fetching from an HTTP API / object store, or
- fetching from a Supabase table or Storage bucket.

The JSON shape is typed in [`types.ts`](./types.ts) — keep it in sync with the
scanner's output.

## Not included (intentional seams)

No database, auth, or live scanner integration. Those are left as commented
seams in `app/page.tsx`.
