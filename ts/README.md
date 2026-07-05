# wma200-scanner (TypeScript)

A verified, standalone TypeScript port of the pure core of `python/wma200_scanner.py` (the frozen source of truth): `analyse()` — 200-week moving-average status for a single weekly-close series — and `runScan()` — the aggregation + market-breadth pass over an already-fetched `Map<ticker, series>` (the yfinance fetcher is intentionally *not* ported). It reproduces the Python output exactly, including Python's round-half-to-even (`round()`) behaviour, and is checked against the shared golden vectors in `../shared/test_vectors.json` (7 cases: crossed up/down, near above/below, breadth-only, too-short→null, below-min-price→null).

## Run

```bash
npm install
npm test        # vitest — validates against the golden vectors
npm run typecheck
npm run build
```
