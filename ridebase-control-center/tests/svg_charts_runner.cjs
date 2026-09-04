"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("function chartFrame(");
const end = template.indexOf("function tbl(", start);

if (start < 0 || end < 0) {
  throw new Error("chart functions could not be extracted from template.html");
}

function esc(x) { return String(x == null ? "" : x).replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function asNum(v) { const x = typeof v === "string" ? parseFloat(v) : v; return (typeof x === "number" && isFinite(x)) ? x : null; }

const fns = new Function(
  "esc", "asNum",
  `${template.slice(start, end)}; return { svgSurvivalCurve, svgHorizonBars, svgHistogram, svgCalibrationScatter };`
)(esc, asNum);

const out = {
  survival: fns.svgSurvivalCurve({ risk_30d: 0.63, risk_60d: 0.72, risk_90d: 0.85, risk_120d: 0.91 }),
  bars: fns.svgHorizonBars(["30", "60", "90", "120"],
    { label: "Brier", values: { "30": 0.083, "60": 0.111, "90": 0.108, "120": 0.091 } },
    { label: "AUC", values: { "30": 0.777, "60": 0.794, "90": 0.808, "120": 0.819 } }),
  hist: fns.svgHistogram({ n: 1282, bins: [{ start: 0, end: 23.4, count: 896 }, { start: 23.4, end: 46.8, count: 226 }] }, "gün"),
  scatter: fns.svgCalibrationScatter(
    [{ bin: 0, mean_pred: 34.2, mean_actual: 34.0 }, { bin: 1, mean_pred: 47.2, mean_actual: 46.5 }],
    "gün"
  ),
};

process.stdout.write(JSON.stringify(out));
