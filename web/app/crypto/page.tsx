import Nav from "@/components/Nav";
import Dashboard from "@/components/Dashboard";
import { loadScan, loadBaseRates } from "@/lib/data";

export default async function CryptoPage() {
  const [data, baseRates] = await Promise.all([
    loadScan("crypto").catch(() => null),
    loadBaseRates(),
  ]);
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
