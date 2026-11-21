// SPDX-License-Identifier: GPL-3.0-or-later
// Checks the layout builder page (GEN-011) in headless Chromium:
//   node generator/configurator/check_builder.js [out.json]
// For every layout style, size and standard: no overlapping keys, unique ids, KLE export at the same positions,
// KO file read back unchanged. Writes all exported files to out.json for the schema check:
//   python3 generator/configurator/check_schema.py out.json
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

(async () => {
  const page = path.resolve(__dirname, "index.html");
  const browser = await chromium.launch();
  const p = await browser.newPage();
  const errors = [];
  p.on("pageerror", e => errors.push(String(e)));
  await p.goto("file://" + page);
  await p.waitForFunction(() => window.__ko);
  const result = await p.evaluate(() => {
    const rects = k => k.shape === "iso-enter" ? [[k.x, k.y, 1.5, 1], [k.x + 0.25, k.y, 1.25, 2]] : [[k.x, k.y, k.w, k.h]];
    const hit = (a, b) => a[0] < b[0] + b[2] - 1e-6 && b[0] < a[0] + a[2] - 1e-6 && a[1] < b[1] + b[3] - 1e-6 && b[1] < a[1] + a[3] - 1e-6;
    function readKLE(rows) {
      const keys = []; let y = 0, first = true;
      for (const row of rows) {
        if (!Array.isArray(row)) continue;
        let x = 0, prop = {};
        if (!first) y += 1;
        first = false;
        for (const item of row) {
          if (typeof item === "object") { if (item.y) y += item.y; if (item.x) x += item.x; prop = { ...prop, ...item }; continue; }
          keys.push({ x, y, w: prop.w || 1, h: prop.h || 1 }); x += prop.w || 1; prop = {};
        }
      }
      return keys;
    }
    const fails = [], files = [];
    for (const style of ["staggered", "grid"]) for (const sz of __ko.SIZES) for (const st of __ko.STANDARDS) {
      const s = __ko.state; s.size = sz.id; s.standard = st.id; s.style = style;
      s.fitted = ["mx", "choc_v1", "choc_v2"]; s.underglow = style === "grid";
      s.extra = { top: [{ keys: Array.from({ length: 30 }, (_, i) => ({ fn: i % 3 ? "play_pause" : (i % 2 ? "custom" : null), label: "obs" })) }],
        left: [{ keys: Array.from({ length: 8 }, () => ({ fn: "stealth" })) }], right: [{ keys: [{ fn: "mute" }] }] };
      __ko.applyState(s);
      const ko = __ko.exportKO(), tag = `${style}/${sz.id}/${st.id}`;
      files.push(ko);
      let overlaps = 0;
      for (let i = 0; i < ko.keys.length; i++) for (let j = i + 1; j < ko.keys.length; j++)
        for (const a of rects(ko.keys[i])) for (const c of rects(ko.keys[j])) if (hit(a, c)) overlaps++;
      if (overlaps) fails.push(`${tag}: ${overlaps} overlapping key pairs`);
      if (new Set(ko.keys.map(k => k.id)).size !== ko.keys.length) fails.push(`${tag}: duplicate key ids`);
      const key = r => [r.y.toFixed(4), r.x.toFixed(4), r.w, r.h].join("|");
      const a = ko.keys.map(k => key({ x: k.shape ? k.x + 0.25 : k.x, y: k.y, w: k.shape ? 1.25 : k.w, h: k.h })).sort();
      const b = readKLE(__ko.exportKLE()).map(key).sort();
      if (JSON.stringify(a) !== JSON.stringify(b)) fails.push(`${tag}: KLE export differs from the KO file`);
      const back = __ko.importKO(JSON.stringify(ko)); __ko.applyState(back);
      if (JSON.stringify(__ko.exportKO()) !== JSON.stringify(ko)) fails.push(`${tag}: KO file does not read back unchanged`);
    }
    return { fails, files };
  });
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(result.files));
  await browser.close();
  const fails = [...result.fails, ...errors.map(e => "page error: " + e)];
  console.log(`${result.files.length} style/size/standard combinations checked`);
  for (const f of fails) console.log("FAIL " + f);
  console.log(fails.length ? "RESULT: FAIL" : "RESULT: PASS");
  process.exit(fails.length ? 1 : 0);
})();
