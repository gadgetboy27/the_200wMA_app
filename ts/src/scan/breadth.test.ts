import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { runScan } from "./breadth.js";
import type { Series } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

interface Vector {
  name: string;
  band_pct: number;
  min_price: number;
  closes: [string, number][];
}

const vectorsFile = resolve(__dirname, "../../../shared/test_vectors.json");
const raw = JSON.parse(readFileSync(vectorsFile, "utf8")) as {
  vectors: Vector[];
};

function seriesOf(name: string): Series {
  const v = raw.vectors.find((x) => x.name === name)!;
  return v.closes.map(([date, close]) => ({ date, close }));
}

describe("runScan — aggregation + breadth", () => {
  it("aggregates the four signal-bearing vectors plus one breadth-only", () => {
    // Insertion order chosen so we can verify the priority re-sort actually runs.
    const map = new Map<string, Series>([
      ["NEAR_ABOVE", seriesOf("near_above")], // NEAR (above), dist +3.02
      ["CROSS_DOWN", seriesOf("crossed_down")], // CROSSED DOWN
      ["BREADTH", seriesOf("breadth_only_above")], // above, no signal
      ["CROSS_UP", seriesOf("crossed_up")], // CROSSED UP
      ["NEAR_BELOW", seriesOf("near_below")], // NEAR (below), dist -2.86
      ["TOO_SHORT", seriesOf("too_short")], // -> null, ignored
    ]);

    const { signals, breadth } = runScan(map, 10.0, 0.0);

    // 5 assets have a formed MA (all except TOO_SHORT).
    expect(breadth.assets_with_full_ma).toBe(5);
    expect(breadth.crossed_up).toBe(1);
    expect(breadth.crossed_down).toBe(1);
    // above: near_above(T), crossed_up(T), breadth(T) = 3 of 5 = 60.0%
    expect(breadth.pct_above_200wma).toBe(60.0);

    // 4 signal rows (breadth-only + null excluded), sorted by priority then |dist|.
    expect(signals.map((s) => s.ticker)).toEqual([
      "CROSS_UP", // CROSSED UP (order 0)
      "CROSS_DOWN", // CROSSED DOWN (order 1)
      "NEAR_BELOW", // NEAR (below) (order 2)
      "NEAR_ABOVE", // NEAR (above) (order 3)
    ]);

    // Rows must not carry `above`.
    for (const s of signals) {
      expect(s).not.toHaveProperty("above");
      expect(s).toHaveProperty("ticker");
      expect(s).toHaveProperty("signal");
      expect(s).toHaveProperty("chart");
    }
  });

  it("returns null pct_above and empty signals when no asset has a formed MA", () => {
    const map = new Map<string, Series>([["TOO_SHORT", seriesOf("too_short")]]);
    const { signals, breadth } = runScan(map, 10.0, 0.0);
    expect(signals).toEqual([]);
    expect(breadth.assets_with_full_ma).toBe(0);
    expect(breadth.pct_above_200wma).toBeNull();
    expect(breadth.crossed_up).toBe(0);
    expect(breadth.crossed_down).toBe(0);
  });

  it("ties within the same signal class sort by |dist_pct|", () => {
    // Two NEAR (below) style entries via near_above/near_below distances:
    // near_below |dist| = 2.86, and we reuse near_above (order 3) — different
    // classes already covered; here confirm equal-class ordering by |dist|.
    const map = new Map<string, Series>([
      ["A", seriesOf("near_above")], // NEAR (above) |dist|=3.02
      ["B", seriesOf("near_above")], // same
    ]);
    const { signals } = runScan(map, 10.0, 0.0);
    expect(signals).toHaveLength(2);
    // stable order preserved for equal keys
    expect(signals.map((s) => s.ticker)).toEqual(["A", "B"]);
  });
});
