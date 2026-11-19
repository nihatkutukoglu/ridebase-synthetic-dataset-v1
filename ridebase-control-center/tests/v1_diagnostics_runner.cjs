"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("function v1DiagnosticsFinding(");
const end = template.indexOf("function v1ResultCard(", start);

if (start < 0 || end < 0) {
  throw new Error("v1DiagnosticsFinding() could not be extracted from template.html");
}

function esc(x) { return String(x == null ? "" : x).replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function finding(kind, label, html) { return '<div class="finding ' + (kind || '') + '"><div class="tl">' + esc(label) + '</div><div>' + html + '</div></div>'; }
const fns = new Function("esc", "finding", `${template.slice(start, end)}; return { v1DiagnosticsFinding };`)(esc, finding);

const cases = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map((diag) => fns.v1DiagnosticsFinding(diag))));
