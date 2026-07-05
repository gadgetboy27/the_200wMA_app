/**
 * Scan aggregation + market breadth.
 *
 * Verified port of the pure part of `run_scan()` in `python/wma200_scanner.py`.
 * The fetcher (yfinance) is NOT ported — callers pass an already-fetched
 * `Map<ticker, series>`. The non-deterministic `date` field is omitted from
 * breadth; pass it in at the call site if needed.
 */

import { analyse, roundHalfEven } from "./wma200.js";
import { isFullSignal } from "./types.js";
import type {
  Breadth,
  ScanResult,
  Series,
  Signal,
  SignalRow,
} from "./types.js";

/** Sort priority for signals (lower sorts first). */
const ORDER: Record<Signal, number> = {
  "CROSSED UP": 0,
  "CROSSED DOWN": 1,
  "NEAR (below)": 2,
  "NEAR (above)": 3,
};

/**
 * Aggregate analyse() results across a universe and compute breadth.
 *
 * @param seriesMap insertion-ordered `Map<ticker, series>` (already fetched)
 * @param bandPct   near-band, in percent
 * @param minPrice  minimum current price to qualify
 */
export function runScan(
  seriesMap: Map<string, Series>,
  bandPct: number,
  minPrice: number,
): ScanResult {
  const signals: SignalRow[] = [];
  let above = 0;
  let total = 0;

  for (const [ticker, closes] of seriesMap) {
    const res = analyse(closes, bandPct, minPrice);
    if (res === null) {
      continue;
    }
    total += 1;
    above += res.above ? 1 : 0;
    if (isFullSignal(res)) {
      const { above: _drop, ...rest } = res;
      signals.push({ ticker, ...rest });
    }
  }

  const breadth: Breadth = {
    assets_with_full_ma: total,
    pct_above_200wma: total ? roundHalfEven((100 * above) / total, 1) : null,
    crossed_up: signals.filter((s) => s.signal === "CROSSED UP").length,
    crossed_down: signals.filter((s) => s.signal === "CROSSED DOWN").length,
  };

  signals.sort((a, b) => {
    const byOrder = ORDER[a.signal] - ORDER[b.signal];
    if (byOrder !== 0) return byOrder;
    return Math.abs(a.dist_pct) - Math.abs(b.dist_pct);
  });

  return { signals, breadth };
}
