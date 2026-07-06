import Nav from "@/components/Nav";
import Dashboard from "@/components/Dashboard";
import { loadScan, loadBaseRates, loadEnrichments, loadValueTiming } from "@/lib/data";

export default async function CryptoPage() {
  const [scan, baseRates, enrichments, valueTiming] = await Promise.all([
    loadScan("crypto").catch(() => null),
    loadBaseRates(),
    loadEnrichments(),
    loadValueTiming(),
  ]);
  // Crypto mandate: only actual 200WMA crosses (up or down). "NEAR" proximity
  // signals are noise at crypto volatility — a coin can sit near its 200WMA for
  // months without the cycle turning; the cross IS the event.
  const data = scan
    ? {
        ...scan,
        signals: scan.signals.filter(
          (s) => s.signal === "CROSSED UP" || s.signal === "CROSSED DOWN",
        ),
      }
    : null;
  // Breadth-history trend is S&P-only for now (the historical breadth job runs
  // over the index); crypto shows the current breadth number without the trend.
  return (
    <main>
      <Nav active="crypto" />
      {data ? (
        <Dashboard
          universe="crypto"
          data={data}
          baseRates={baseRates}
          breadthHistory={null}
          enrichments={enrichments}
          valueTiming={valueTiming}
        />
      ) : (
        <p className="empty">
          No crypto scan yet. Run <code>./scripts/weekly_scan.sh</code> (or{" "}
          <code>python/.venv/bin/python python/wma200_scanner.py --universe crypto</code>) to
          generate <code>web/public/wma200_signals_crypto.json</code>.
        </p>
      )}
    </main>
  );
}
