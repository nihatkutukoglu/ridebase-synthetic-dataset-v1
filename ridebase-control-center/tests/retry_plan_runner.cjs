"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("function v2json(");
const end = template.indexOf("function v2Predict(", start);

if (start < 0 || end < 0) {
  throw new Error("v2json/retryPlan could not be extracted from template.html");
}

const fns = new Function(`${template.slice(start, end)}; return { v2json, retryPlan };`)();

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const cases = JSON.parse(input); // [{status, attempt}]
  process.stdout.write(JSON.stringify(cases.map((c) => {
    const err = new Error("boom");
    if (c.status != null) err.status = c.status;
    const rp = fns.retryPlan(err, c.attempt);
    return { message: rp.message, delay: rp.delay };
  })));
});
