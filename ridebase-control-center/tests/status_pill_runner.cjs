"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("function statusPill(");
const end = template.indexOf("function card(", start);

if (start < 0 || end < 0) {
  throw new Error("statusPill() could not be extracted from template.html");
}

function esc(x) { return String(x == null ? "" : x).replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

const fns = new Function("esc", `${template.slice(start, end)}; return { statusPill };`)(esc);

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const statuses = JSON.parse(input);
  process.stdout.write(JSON.stringify(statuses.map((s) => fns.statusPill(s))));
});
