import fs from "node:fs/promises";
import path from "node:path";
import type {
  BaseRates,
  BreadthHistory,
  Enrichments,
  ScanResult,
  Universe,
  ValueTiming,
} from "@/types";

const PUBLIC = path.join(process.cwd(), "public");

async function readJson<T>(...names: string[]): Promise<T | null> {
  for (const name of names) {
    try {
      const raw = await fs.readFile(path.join(PUBLIC, name), "utf-8");
      return JSON.parse(raw) as T;
    } catch {
      // try next / return null
    }
  }
  return null;
}

// Real scan output written by python/wma200_scanner.py + scripts/weekly_scan.sh.
// Falls back to the bundled sample so the skeleton still renders pre-scan.
// Later: swap for an HTTP API / Supabase fetch.
export async function loadScan(universe: Universe): Promise<ScanResult> {
  const files =
    universe === "crypto"
      ? ["wma200_signals_crypto.json"]
      : ["wma200_signals.json", "sample-signals.json"];
  const data = await readJson<ScanResult>(...files);
  if (!data) throw new Error(`No scan data for ${universe} in web/public/`);
  return data;
}

// Optional companions — null until the weekly job has produced them.
export async function loadBaseRates(): Promise<BaseRates | null> {
  return readJson<BaseRates>("base_rates.json");
}

export async function loadBreadthHistory(): Promise<BreadthHistory | null> {
  return readJson<BreadthHistory>("breadth_history.json");
}

export async function loadEnrichments(): Promise<Enrichments | null> {
  return readJson<Enrichments>("enrichment.json");
}

export async function loadValueTiming(): Promise<ValueTiming | null> {
  return readJson<ValueTiming>("value_timing.json");
}
