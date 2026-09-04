"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("var V2_DEFAULT_API=");
const end = template.indexOf("\ntry{\n  var _q=", start);

if (start < 0 || end < 0) {
  throw new Error("allowedApiUrl() could not be extracted from template.html");
}

const fns = new Function(
  `${template.slice(start, end)}; return { allowedApiUrl };`
)();

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const urls = JSON.parse(input);
  process.stdout.write(JSON.stringify(urls.map((u) => fns.allowedApiUrl(u))));
});
