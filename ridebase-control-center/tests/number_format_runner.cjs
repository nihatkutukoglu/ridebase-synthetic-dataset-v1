"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("function n0(");
const end = template.indexOf("function sgn(", start);

if (start < 0 || end < 0) {
  throw new Error("n0/n1/n2/int0/raw could not be extracted from template.html");
}

const fns = new Function(`${template.slice(start, end)}; return { n0, n1, n2, int0, raw };`)();

process.stdout.write(JSON.stringify({
  n0_28980: fns.n0(28980),
  n1_3320_5: fns.n1(3320.5),
  int0_year: fns.int0(2023),
  int0_count: fns.int0(1),
  raw_dash: fns.raw(null),
}));
