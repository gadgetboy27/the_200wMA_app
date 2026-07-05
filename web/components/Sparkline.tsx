import type { Chart } from "@/types";

// Inline-SVG sparkline of price vs 200-week MA.
//
// This mirrors the Python `svg_chart` approach in wma200_scanner.py:
//   - normalize BOTH series against one shared min/max (padded 2% each side)
//   - draw two polylines: MA (dashed amber) underneath, price (solid blue) on top
// No chart library — just points mapped into a viewBox.

interface SparklineProps {
  chart: Chart;
  width?: number;
  height?: number;
}

const PRICE_COLOR = "#4fa8f0";
const MA_COLOR = "#e8c45a";

export default function Sparkline({
  chart,
  width = 560,
  height = 150,
}: SparklineProps) {
  const prices = chart.price ?? [];
  const maValues = (chart.ma ?? []).filter(
    (m): m is number => m !== null && m !== undefined,
  );

  // Nothing to draw — match the Python behaviour of rendering nothing.
  if (prices.length === 0 || maValues.length === 0) {
    return null;
  }

  const lo = Math.min(Math.min(...prices), Math.min(...maValues)) * 0.98;
  const hi = Math.max(Math.max(...prices), Math.max(...maValues)) * 1.02;
  const span = hi - lo || 1;
  const n = prices.length;

  // Map a series to a "x,y x,y ..." polyline points string, skipping nulls.
  const pts = (vals: (number | null)[]): string =>
    vals
      .map((v, i) => {
        if (v === null || v === undefined) return null;
        const x = n > 1 ? (i / (n - 1)) * width : 0;
        const y = height - ((v - lo) / span) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .filter((p): p is string => p !== null)
      .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="chart"
      role="img"
      aria-label="Price versus 200-week moving average"
    >
      <polyline
        points={pts(chart.ma)}
        fill="none"
        stroke={MA_COLOR}
        strokeWidth={1.4}
        strokeDasharray="5 4"
      />
      <polyline
        points={pts(prices)}
        fill="none"
        stroke={PRICE_COLOR}
        strokeWidth={1.6}
      />
    </svg>
  );
}
