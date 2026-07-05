/**
 * Core 200-week moving-average analysis.
 *
 * Verified line-by-line port of `analyse()` in `python/wma200_scanner.py`.
 * The Python is FROZEN and is the source of truth; this reproduces its output
 * exactly (including Python's round-half-to-even behaviour).
 */

import type { AnalyseResult, ChartData, Series, Signal } from "./types.js";

export const WEEKS = 200; // MA window
export const CHART_WEEKS = 260; // weeks shown in each report chart

/**
 * Round to `digits` decimal places using round-half-to-even (banker's rounding),
 * matching Python's built-in `round()`. JS `Math.round` is round-half-up, which
 * disagrees with Python on exact halves — so we implement the tie rule explicitly.
 */
export function roundHalfEven(x: number, digits: number): number {
  if (!Number.isFinite(x)) return x;
  const m = Math.pow(10, digits);
  const scaled = x * m;
  const floor = Math.floor(scaled);
  const frac = scaled - floor;
  const EPS = 1e-9;
  let roundedScaled: number;
  if (Math.abs(frac - 0.5) < EPS) {
    // Exact half: round to the even neighbour.
    roundedScaled = floor % 2 === 0 ? floor : floor + 1;
  } else {
    roundedScaled = Math.round(scaled); // ties excluded above
  }
  const result = roundedScaled / m;
  // Normalise -0 to 0 (Python's round(-0.0, n) == -0.0 too, but 0 compares equal).
  return result === 0 ? 0 : result;
}

const round2 = (x: number) => roundHalfEven(x, 2);
const round4 = (x: number) => roundHalfEven(x, 4);

/**
 * Trailing simple moving average over `window` values, computed at each index.
 * Index i uses closes[i-window+1 .. i]; indices with < window prior values are NaN.
 * Mirrors pandas `.rolling(window).mean()`.
 */
function rollingMean(values: number[], window: number): number[] {
  const out: number[] = new Array(values.length);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) {
      sum -= values[i - window];
    }
    out[i] = i >= window - 1 ? sum / window : NaN;
  }
  return out;
}

/**
 * Compute 200WMA status for one weekly close series.
 *
 * @param weeklyClose series of `{ date, close }`, sorted ascending, may contain NaN
 * @param bandPct     "near" band, in percent (e.g. 10 => within ±10%)
 * @param minPrice    minimum current price to qualify
 * @returns null | { above } (breadth only) | full signal object
 */
export function analyse(
  weeklyClose: Series,
  bandPct: number,
  minPrice: number,
): AnalyseResult {
  // pandas .dropna() — drop rows whose close is NaN.
  const s = weeklyClose.filter((row) => !Number.isNaN(row.close));
  if (s.length < WEEKS + 14) {
    // MA + slope lookback
    return null;
  }

  const closes = s.map((row) => row.close);
  const ma = rollingMean(closes, WEEKS);
  const n = s.length;

  const priceNow = closes[n - 1];
  const pricePrev = closes[n - 2];
  const maNow = ma[n - 1];
  const maPrev = ma[n - 2];

  if (priceNow < minPrice || Number.isNaN(maNow)) {
    return null;
  }

  const dist = (priceNow - maNow) / maNow;
  const crossedUp = pricePrev <= maPrev && priceNow > maNow;
  const crossedDown = pricePrev >= maPrev && priceNow < maNow;
  const near = Math.abs(dist) <= bandPct / 100.0;

  if (!(crossedUp || crossedDown || near)) {
    return { above: priceNow > maNow }; // breadth only, no signal
  }

  const signal: Signal = crossedUp
    ? "CROSSED UP"
    : crossedDown
      ? "CROSSED DOWN"
      : dist >= 0
        ? "NEAR (above)"
        : "NEAR (below)";

  const slope13w = (ma[n - 1] / ma[n - 14] - 1) * 100;

  const start = Math.max(0, n - CHART_WEEKS);
  const tailP = s.slice(start);
  const tailM = ma.slice(start);

  const chart: ChartData = {
    dates: tailP.map((row) => row.date),
    price: tailP.map((row) => round4(row.close)),
    ma: tailM.map((v) => (Number.isNaN(v) ? null : round4(v))),
  };

  return {
    above: priceNow > maNow,
    signal,
    price: round4(priceNow),
    wma200: round4(maNow),
    dist_pct: round2(dist * 100),
    ma_slope_13w_pct: round2(slope13w),
    chart,
  };
}
