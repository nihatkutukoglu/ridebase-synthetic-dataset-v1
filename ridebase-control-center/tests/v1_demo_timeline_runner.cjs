"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("function v1DemoTimeline(");
const end = template.indexOf("function v1ResultCard(", start);

if (start < 0 || end < 0) {
  throw new Error("v1DemoTimeline() could not be extracted from template.html");
}

function esc(x) { return String(x == null ? "" : x).replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
const fns = new Function("esc", `${template.slice(start, end)}; return { v1DemoTimeline };`)(esc);

const out = fns.v1DemoTimeline(
  { snapshot_date: "2026-01-10", features: { days_since_previous_service: 167 } },
  { next_service_days: 202 },
  null
);
process.stdout.write(out);
