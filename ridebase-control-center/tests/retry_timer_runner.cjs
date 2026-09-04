"use strict";

// Y1: retryTimer() must stop firing once route() bumps VIEW_GEN (user navigated
// away) -- even if the raw setTimeout wasn't cleared in time. Extracts the real
// VIEW_GEN/PENDING_TIMERS/retryTimer/staleView block and drives it directly with
// fake timers (no DOM needed -- this logic never touches one).

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");
const start = template.indexOf("var VIEW_GEN=0;");
const end = template.indexOf("function route(){", start);

if (start < 0 || end < 0) {
  throw new Error("VIEW_GEN/retryTimer could not be extracted from template.html");
}

// Fake timer queue: setTimeout just records {fn, ms}; we fire them manually.
const queue = [];
let nextId = 1;
function fakeSetTimeout(fn, ms) { const id = nextId++; queue.push({ id, fn, ms }); return id; }
function fakeClearTimeout(id) { const i = queue.findIndex((t) => t.id === id); if (i >= 0) queue.splice(i, 1); }

const fns = new Function(
  "setTimeout", "clearTimeout",
  `${template.slice(start, end)}; return { retryTimer, staleView, bump: function(){VIEW_GEN++;PENDING_TIMERS.forEach(clearTimeout);PENDING_TIMERS.length=0;} };`
)(fakeSetTimeout, fakeClearTimeout);

let fired = 0;
fns.retryTimer(() => { fired++; }, 4000);
fns.bump(); // simulate route() navigating away

// Fire whatever is left in the queue (should be nothing -- route() cleared it).
const stillQueued = queue.length;
while (queue.length) { const t = queue.shift(); t.fn(); }

process.stdout.write(JSON.stringify({ fired, stillQueued }));
