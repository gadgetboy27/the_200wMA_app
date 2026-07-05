// Stitch the two prerendered Next routes (/ and /crypto) + the compiled CSS into
// ONE self-contained HTML page with working in-page tabs, for the Artifact tool.
// Faithful snapshot of the real dashboard — no reskin.
import fs from "node:fs";
import path from "node:path";

const WEB = path.resolve(process.cwd(), "web");
const OUT = path.resolve(process.cwd(), "scratch_dashboard.html");

const cssFile = fs.readdirSync(path.join(WEB, ".next/static/css")).find((f) => f.endsWith(".css"));
const css = fs.readFileSync(path.join(WEB, ".next/static/css", cssFile), "utf-8");

function mainOf(htmlPath) {
  const html = fs.readFileSync(htmlPath, "utf-8");
  const m = html.match(/<main[^>]*>([\s\S]*?)<\/main>/);
  if (!m) throw new Error("no <main> in " + htmlPath);
  // Drop the in-page <div class="nav">…</nav></div> (we provide our own tabs).
  return m[1].replace(/<div class="nav">[\s\S]*?<\/nav><\/div>/, "");
}

const sp = mainOf(path.join(WEB, ".next/server/app/index.html"));
const cr = mainOf(path.join(WEB, ".next/server/app/crypto.html"));

const page = `<style>
${css}
/* Artifact-only chrome: our own tab bar + snapshot banner */
.af-top { display:flex; align-items:baseline; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:14px; }
.af-top h1 { font-size:18px; letter-spacing:2px; color:#7fd4a8; margin:0; }
.af-snap { font-size:11px; color:#5c6a78; }
.af-tabs { display:flex; gap:8px; margin-bottom:22px; }
.af-tab { font:inherit; font-size:13px; letter-spacing:1px; text-transform:uppercase; color:#5c6a78;
  padding:5px 16px; border:1px solid #1f2b3a; border-radius:20px; background:transparent; cursor:pointer; }
.af-tab[aria-selected="true"] { color:#0b0f14; background:#4fd08a; border-color:#4fd08a; font-weight:700; }
.af-tab:focus-visible { outline:2px solid #4fa8f0; outline-offset:2px; }
.af-view[hidden] { display:none; }
</style>

<div class="af-top">
  <h1>200-WEEK MA SCAN</h1>
  <span class="af-snap">Static snapshot of the live dashboard · data from the real weekly scan</span>
</div>
<div class="af-tabs" role="tablist" aria-label="Universe">
  <button class="af-tab" role="tab" id="tab-sp" aria-controls="view-sp" aria-selected="true">S&amp;P 500</button>
  <button class="af-tab" role="tab" id="tab-cr" aria-controls="view-cr" aria-selected="false">Crypto</button>
</div>
<div class="af-view" id="view-sp" role="tabpanel" aria-labelledby="tab-sp">${sp}</div>
<div class="af-view" id="view-cr" role="tabpanel" aria-labelledby="tab-cr" hidden>${cr}</div>

<script>
(function () {
  var tabs = [["tab-sp","view-sp"],["tab-cr","view-cr"]];
  function show(id) {
    tabs.forEach(function (t) {
      var sel = t[0] === id;
      document.getElementById(t[0]).setAttribute("aria-selected", sel ? "true" : "false");
      document.getElementById(t[1]).hidden = !sel;
    });
  }
  document.getElementById("tab-sp").addEventListener("click", function () { show("tab-sp"); });
  document.getElementById("tab-cr").addEventListener("click", function () { show("tab-cr"); });
})();
</script>`;

fs.writeFileSync(OUT, page);
console.log("wrote", OUT, "(" + (page.length / 1024).toFixed(0) + " KB)");
