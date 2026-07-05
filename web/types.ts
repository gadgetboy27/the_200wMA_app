// Type definitions mirroring the JSON emitted by the Python scanner
// (python/wma200_scanner.py -> wma200_signals.json).
// Keep this in sync with the scanner's output shape.

export type SignalType =
  | "CROSSED UP"
  | "CROSSED DOWN"
  | "NEAR (above)"
  | "NEAR (below)";

export interface Chart {
  dates: string[];
  price: number[];
  // The MA series can contain nulls for the early weeks before the
  // 200-week window is fully populated.
  ma: (number | null)[];
}

export interface Signal {
  ticker: string;
  signal: SignalType;
  price: number;
  wma200: number;
  dist_pct: number;
  ma_slope_13w_pct: number;
  chart: Chart;
}

export interface Breadth {
  date: string;
  assets_with_full_ma: number;
  pct_above_200wma: number | null;
  crossed_up: number;
  crossed_down: number;
}

export interface ScanResult {
  breadth: Breadth;
  signals: Signal[];
}

export type Universe = "sp500" | "crypto";

// web/public/base_rates.json — per-ticker event-study context.
export interface BaseRate {
  touches: number;
  fwd_mean_pct: number;
  baseline_mean_pct: number;
  edge_pct: number;
  win_pct: number;
}
export interface BaseRates {
  horizon_weeks: number;
  band_pct: number;
  generated?: string;
  _caveat?: string;
  tickers: Record<string, BaseRate | null>;
}

// web/public/breadth_history.json — real historical weekly breadth.
export interface BreadthHistory {
  universe: string;
  generated?: string;
  series: { date: string; pct_above_200wma: number }[];
}
