"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("function v2RoundHalfEven(");
const end = template.indexOf("function v2UrgencyCard(", start);

if (start < 0 || end < 0) {
  throw new Error("Maintenance urgency functions could not be extracted from template.html");
}

const urgencyFunctions = new Function(
  `${template.slice(start, end)}; return { v2CalculateUrgency };`
)();

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const cases = JSON.parse(input);
  process.stdout.write(JSON.stringify(cases.map((item) => urgencyFunctions.v2CalculateUrgency(item))));
});
