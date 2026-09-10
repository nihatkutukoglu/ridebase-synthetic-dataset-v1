"use strict";
/* Renders the V3 result card from a fixed API payload and reports what a viewer
   would actually see. Guards the things that must never regress: no NaN or
   undefined on screen, percentages formatted, confidence tiers rendered, the
   synthetic disclaimer present, and "accuracy" never used for a ranking metric. */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const template = fs.readFileSync(path.join(root, "template.html"), "utf8");

function slice(from, to) {
  const a = template.indexOf(from);
  const b = template.indexOf(to, a);
  if (a < 0 || b < 0) throw new Error(`could not extract ${from} .. ${to}`);
  return template.slice(a, b);
}

// helpers the V3 renderer depends on
const helpers = `
function esc(x){return String(x==null?"":x).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function n0(v){return v==null||v!==v?"—":Math.round(v).toLocaleString("tr-TR");}
function pct(v,d){return v==null||v!==v?"—":(v*100).toFixed(d==null?1:d)+"%";}
function card(title,sub,body){return '<div class="card"><h2>'+esc(title)+'</h2>'+(sub?'<div class="sub">'+esc(sub)+'</div>':'')+body+'</div>';}
function finding(kind,label,html){return '<div class="finding '+(kind||'')+'"><div class="tl">'+esc(label)+'</div><div>'+html+'</div></div>';}
function techBox(html){return '<details class="tech"><summary>Teknik detay</summary><div class="tbody">'+html+'</div></details>';}
function kpi(label,value,note,accent){return '<div class="kpi '+(accent||'')+'"><div class="eyebrow">'+esc(label)+'</div><div class="value">'+value+'</div>'+(note?'<div class="note">'+note+'</div>':'')+'</div>';}
`;

const v3src = slice("/* ---------------- V3 — NEXT SERVICE TASKS ---------------- */",
                    "/* ---------------- placeholder (unused modules) ---------------- */");

const mod = new Function(`${helpers}\n${v3src}\nreturn {v3Result:v3Result,v3ContextCard:v3ContextCard,v3ContextTechnical:v3ContextTechnical,v3ConfLabel:v3ConfLabel,v3ConfClass:v3ConfClass,v3Disclaimers:v3Disclaimers,V3_HEADING:V3_HEADING,V3_DISCLAIMER:V3_DISCLAIMER,V3_NOT_FAILURE:V3_NOT_FAILURE};`)();

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => { input += c; });
process.stdin.on("end", () => {
  const payload = JSON.parse(input);
  const html = mod.v3Result(payload);
  const text = html.replace(/<[^>]*>/g, " ");
  process.stdout.write(JSON.stringify({
    html: html,
    html_length: html.length,
    text: text,
    has_nan: /\bNaN\b/.test(html),
    has_undefined: /\bundefined\b/.test(html),
    has_null_literal: /\bnull\b/.test(html),
    heading: mod.V3_HEADING,
    disclaimer_present: html.indexOf(mod.V3_DISCLAIMER) >= 0 || (payload.warnings || []).indexOf(mod.V3_DISCLAIMER) >= 0,
    disclaimers_block: mod.v3Disclaimers(),
    tiers: ["YUKSEK", "ORTA", "DUSUK", "SINIRLI_VERI"].map(mod.v3ConfLabel),
    tier_classes: ["YUKSEK", "ORTA", "DUSUK", "SINIRLI_VERI"].map(mod.v3ConfClass),
    percents: (html.match(/\d+\.\d%/g) || []),
  }));
});
