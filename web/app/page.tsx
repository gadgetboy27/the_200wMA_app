import Nav from "@/components/Nav";
import Dashboard from "@/components/Dashboard";
import {
  loadScan,
  loadBaseRates,
  loadBreadthHistory,
  loadEnrichments,
  loadValueTiming,
} from "@/lib/data";

export default async function SP500Page() {
  const [data, baseRates, breadthHistory, enrichments, valueTiming] = await Promise.all([
    loadScan("sp500"),
    loadBaseRates(),
    loadBreadthHistory(),
    loadEnrichments(),
    loadValueTiming(),
  ]);
  return (
    <main>
      <Nav active="sp500" />
      <Dashboard
        universe="sp500"
        data={data}
        baseRates={baseRates}
        breadthHistory={breadthHistory}
        enrichments={enrichments}
        valueTiming={valueTiming}
      />
    </main>
  );
}
