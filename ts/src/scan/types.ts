/**
 * Shared types for the 200-week moving-average scanner.
 *
 * Verified TypeScript port of `python/wma200_scanner.py` (frozen source of truth).
 */

/** One weekly close observation. Series are sorted ascending by date. */
export interface Close {
  date: string;
  close: number;
}

/** A weekly-close series (already sorted ascending; may contain NaN). */
export type Series = Close[];

/** Exact signal strings, in the Python priority order. */
export type Signal =
  | "CROSSED UP"
  | "CROSSED DOWN"
  | "NEAR (above)"
  | "NEAR (below)";

/** Chart tail (last CHART_WEEKS points). `ma` holds null where the MA is NaN. */
export interface ChartData {
  dates: string[];
  price: number[];
  ma: (number | null)[];
}

/** Breadth-only result: asset has a formed MA but no in-band signal. */
export interface BreadthOnly {
  above: boolean;
}

/** Full signal result for an asset that crossed or sits near its 200WMA. */
export interface FullSignal {
  above: boolean;
  signal: Signal;
  price: number;
  wma200: number;
  dist_pct: number;
  ma_slope_13w_pct: number;
  chart: ChartData;
}

/** analyse() return type — discriminated union mirroring the Python `dict | None`. */
export type AnalyseResult = null | BreadthOnly | FullSignal;

/** Type guard: does an analyse result carry a full signal? */
export function isFullSignal(r: AnalyseResult): r is FullSignal {
  return r !== null && "signal" in r;
}

/** A signal row in the scan output: ticker plus every FullSignal field except `above`. */
export type SignalRow = { ticker: string } & Omit<FullSignal, "above">;

/** Market breadth summary (the deterministic part — no `date`). */
export interface Breadth {
  assets_with_full_ma: number;
  pct_above_200wma: number | null;
  crossed_up: number;
  crossed_down: number;
}

/** Result of run_scan's pure aggregation. */
export interface ScanResult {
  signals: SignalRow[];
  breadth: Breadth;
}
