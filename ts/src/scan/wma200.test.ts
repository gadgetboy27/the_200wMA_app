import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { analyse } from "./wma200.js";
import { isFullSignal } from "./types.js";
import type { AnalyseResult, FullSignal, Series } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

interface Vector {
  name: string;
  band_pct: number;
  min_price: number;
  closes: [string, number][];
  expected: unknown;
}

const vectorsFile = resolve(__dirname, "../../../shared/test_vectors.json");
const raw = JSON.parse(readFileSync(vectorsFile, "utf8")) as {
  weeks: number;
  vectors: Vector[];
};

const TOL = 1e-6;

function seriesOf(v: Vector): Series {
  return v.closes.map(([date, close]) => ({ date, close }));
}

describe("analyse — golden vectors from python/", () => {
  it("loads all 7 vectors", () => {
    expect(raw.vectors).toHaveLength(7);
  });

  for (const v of raw.vectors) {
    it(`vector: ${v.name}`, () => {
      const got = analyse(seriesOf(v), v.band_pct, v.min_price);

      // null expected (too_short, below_min_price)
      if (v.expected === null) {
        expect(got).toBeNull();
        return;
      }

      const exp = v.expected as Record<string, unknown>;

      // breadth-only shape: exactly { above }
      if (!("signal" in exp)) {
        expect(got).not.toBeNull();
        expect(isFullSignal(got)).toBe(false);
        const g = got as { above: boolean };
        expect(Object.keys(g).sort()).toEqual(["above"]);
        expect(g.above).toBe(exp.above);
        return;
      }

      // full signal
      expect(isFullSignal(got)).toBe(true);
      const g = got as FullSignal;
      const e = exp as unknown as FullSignal;

      // exact fields
      expect(g.signal).toBe(e.signal);
      expect(g.above).toBe(e.above);

      // numeric scalars within tolerance
      expect(g.price).toBeCloseTo(e.price, 6);
      expect(g.wma200).toBeCloseTo(e.wma200, 6);
      expect(g.dist_pct).toBeCloseTo(e.dist_pct, 6);
      expect(g.ma_slope_13w_pct).toBeCloseTo(e.ma_slope_13w_pct, 6);

      // chart dates exact-equal
      expect(g.chart.dates).toEqual(e.chart.dates);

      // chart price/ma element-wise within tolerance (null aligned)
      expect(g.chart.price).toHaveLength(e.chart.price.length);
      for (let i = 0; i < e.chart.price.length; i++) {
        expect(Math.abs(g.chart.price[i] - e.chart.price[i])).toBeLessThanOrEqual(
          TOL,
        );
      }

      expect(g.chart.ma).toHaveLength(e.chart.ma.length);
      for (let i = 0; i < e.chart.ma.length; i++) {
        const ev = e.chart.ma[i];
        const gv = g.chart.ma[i];
        if (ev === null) {
          expect(gv).toBeNull();
        } else {
          expect(gv).not.toBeNull();
          expect(Math.abs((gv as number) - ev)).toBeLessThanOrEqual(TOL);
        }
      }
    });
  }
});

describe("roundHalfEven (banker's rounding, matches Python round)", () => {
  it("rounds exact halves to even", async () => {
    const { roundHalfEven } = await import("./wma200.js");
    expect(roundHalfEven(0.5, 0)).toBe(0);
    expect(roundHalfEven(1.5, 0)).toBe(2);
    expect(roundHalfEven(2.5, 0)).toBe(2);
    expect(roundHalfEven(0.125, 2)).toBe(0.12);
    expect(roundHalfEven(0.135, 2)).toBe(0.14);
    expect(roundHalfEven(-2.5, 0)).toBe(-2);
  });
});

// Sanity: expected values referenced so unused var lint stays quiet.
export type _V = AnalyseResult;
