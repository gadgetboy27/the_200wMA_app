import type { BreadthHistory } from "@/types";

// Trend of "% of the S&P above its 200WMA" over time. This is the macro-timing
// companion: sustained readings below ~30% are historically washout / strong
// buying zones; above ~85% is euphoria. The single current number is on the
// breadth strip; this shows where it sits in its own range.
export default function BreadthTrend({
  history,
  width = 900,
  height = 160,
}: {
  history: BreadthHistory;
  width?: number;
  height?: number;
}) {
  const series = history.series;
  if (series.length < 2) return null;

  const n = series.length;
  const lo = 0;
  const hi = 100;
  const x = (i: number) => (i / (n - 1)) * width;
  const y = (v: number) => height - ((v - lo) / (hi - lo)) * height;

  const line = series.map((p, i) => `${x(i).toFixed(1)},${y(p.pct_above_200wma).toFixed(1)}`).join(" ");
  const last = series[n - 1].pct_above_200wma;
  const first = series[0].date;
  const lastDate = series[n - 1].date;

  // Horizontal band guides at 30 (washout) and 85 (euphoria).
  const band = (v: number) => y(v).toFixed(1);

  return (
    <div className="trend">
      <div className="trend-head">
        <label>% ABOVE 200WMA — {series.length} weeks</label>
        <span className="trend-now">now {last.toFixed(1)}%</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="trend-svg">
        {/* washout / euphoria zones */}
        <rect x="0" y={band(30)} width={width} height={height - Number(band(30))} className="zone-washout" />
        <rect x="0" y="0" width={width} height={band(85)} className="zone-euphoria" />
        <line x1="0" y1={band(50)} x2={width} y2={band(50)} className="mid" />
        <line x1="0" y1={band(30)} x2={width} y2={band(30)} className="guide" />
        <line x1="0" y1={band(85)} x2={width} y2={band(85)} className="guide" />
        <polyline points={line} className="trend-line" />
      </svg>
      <div className="trend-foot">
        <span>{first}</span>
        <span className="muted">washout &lt;30% · euphoria &gt;85%</span>
        <span>{lastDate}</span>
      </div>
    </div>
  );
}
