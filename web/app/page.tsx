import Nav from "@/components/Nav";
import Dashboard from "@/components/Dashboard";
import { loadScan, loadBaseRates, loadBreadthHistory } from "@/lib/data";

export default async function SP500Page() {
  const [data, baseRates, breadthHistory] = await Promise.all([
    loadScan("sp500"),
    loadBaseRates(),
    loadBreadthHistory(),
  ]);
  return (
    <main>
      <Nav active="sp500" />
      <Dashboard
        universe="sp500"
        data={data}
        baseRates={baseRates}
        breadthHistory={breadthHistory}
      />
    </main>
  );
}
