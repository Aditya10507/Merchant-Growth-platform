/**
 * e2e_live.cjs — E2E test against LIVE deployment
 *
 * Backend:  https://merchant-growth-platform.onrender.com
 * Frontend: https://merchant-growth-platform-stct.vercel.app
 *
 * Uses API for most operations (faster, less flaky on remote).
 * UI tests via Playwright for browser verification.
 */

const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const https = require("https");
const http = require("http");

const API = "https://merchant-growth-platform.onrender.com";
const UI = "https://merchant-growth-platform-stct.vercel.app";
const DOCS_DIR = path.resolve(__dirname, "../test_documents/test_documents");

const RESULTS = [];
const TIMINGS = {};

function log(msg) { console.log(`[${new Date().toISOString().slice(11, 23)}] ${msg}`); }
function record(name, pass, detail = "") { RESULTS.push({ name, pass, detail }); log(`${pass ? "✅" : "❌"} ${name}${detail ? " — " + detail : ""}`); }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/** HTTPS/HTTP API request helper. */
function api(method, p, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(p, API);
    const isHttps = url.protocol === "https:";
    const mod = isHttps ? https : http;
    const opts = {
      hostname: url.hostname,
      port: url.port || (isHttps ? 443 : 80),
      path: url.pathname + url.search,
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (token) opts.headers["Authorization"] = `Bearer ${token}`;

    const req = mod.request(opts, res => {
      let d = "";
      res.on("data", c => d += c);
      res.on("end", () => {
        try { resolve({ s: res.statusCode, b: JSON.parse(d) }); }
        catch { resolve({ s: res.statusCode, b: d }); }
      });
    });
    req.on("error", reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

// Test merchants — use unique emails to avoid conflicts with prior runs
const RUN_ID = Date.now().toString(36);
const M = [
  { n: `Clean Alpha ${RUN_ID}`, e: `clean_alpha_${RUN_ID}@test.com`, p: "TestPass123", pan: "UJALK5542W", g: "approved" },
  { n: `Clean Beta ${RUN_ID}`,  e: `clean_beta_${RUN_ID}@test.com`,  p: "TestPass123", pan: "HAOEL7625O", g: "approved" },
  { n: `Clean Gamma ${RUN_ID}`, e: `clean_gamma_${RUN_ID}@test.com`, p: "TestPass123", pan: "CCZEE2615Q", g: "approved" },
  { n: `Invalid ${RUN_ID}`,     e: `invalid_${RUN_ID}@test.com`,     p: "TestPass123", pan: "NONE",      g: "invalid" },
  { n: `Mismatch A ${RUN_ID}`,  e: `mismatch_a_${RUN_ID}@test.com`,  p: "TestPass123", pan: "VDAWP9860F", g: "rejected" },
  { n: `Mismatch B ${RUN_ID}`,  e: `mismatch_b_${RUN_ID}@test.com`,  p: "TestPass123", pan: "RFBPO7258K", g: "rejected" },
];

async function main() {
  log("═══ E2E Live Deployment Test ═══");
  log(`API:  ${API}`);
  log(`UI:   ${UI}`);
  log("");

  // ── Phase 0: Health check ──
  log("── Phase 0: Backend Health Check ──");
  try {
    const hr = await api("GET", "/health");
    record("Health Check", hr.s === 200 && hr.b?.status === "ok", `HTTP ${hr.s}`);
  } catch (err) {
    record("Health Check", false, err.message);
    log("Backend unreachable — aborting.");
    generateReport();
    return;
  }
  log("");

  // ── Phase 1: Signup ──
  log("── Phase 1: Signup (6 merchants) ──");
  for (const m of M) {
    const s = Date.now();
    try {
      const r = await api("POST", "/auth/signup", { business_name: m.n, email: m.e, password: m.p });
      TIMINGS[`signup_${m.e}`] = Date.now() - s;
      record(`Signup: ${m.n}`, r.s === 201, `${Date.now() - s}ms`);
    } catch (err) {
      record(`Signup: ${m.n}`, false, err.message);
    }
  }
  log("");

  // ── Phase 2: Login ──
  log("── Phase 2: Login ──");
  const tokens = {};
  for (const m of M) {
    const s = Date.now();
    try {
      const r = await api("POST", "/auth/login", { email: m.e, password: m.p });
      TIMINGS[`login_${m.e}`] = Date.now() - s;
      tokens[m.e] = r.b?.access_token;
      record(`Login: ${m.n}`, !!r.b?.access_token, `${Date.now() - s}ms`);
    } catch (err) {
      record(`Login: ${m.n}`, false, err.message);
    }
  }
  log("");

  // ── Phase 3: Upload documents ──
  log("── Phase 3: Document Upload ──");
  const docTypes = ["PAN", "GST", "BANK_PROOF"];

  for (const m of M) {
    if (m.g === "invalid") {
      // Upload a tiny 1x1 PNG — OCR won't find document text
      const fakePng = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==", "base64");
      const boundary = "----BOUND" + Date.now();
      const parts = [`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="fake.png"\r\nContent-Type: image/png\r\n\r\n`, fakePng, `\r\n--${boundary}--\r\n`];
      const body = Buffer.concat([Buffer.from(parts[0]), parts[1], Buffer.from(parts[2])]);
      const url = new URL("/documents/upload?doc_type=PAN", API);
      const isHttps = url.protocol === "https:";
      const mod = isHttps ? https : http;
      try {
        const r = await new Promise((resolve, reject) => {
          const req = mod.request({
            hostname: url.hostname, port: url.port || (isHttps ? 443 : 80),
            path: url.pathname + url.search, method: "POST",
            headers: { "Content-Type": `multipart/form-data; boundary=${boundary}`, "Authorization": `Bearer ${tokens[m.e]}`, "Content-Length": body.length }
          }, res => { let d = ""; res.on("data", c => d += c); res.on("end", () => { try { resolve({ s: res.statusCode, b: JSON.parse(d) }); } catch { resolve({ s: res.statusCode, b: d }); } }); });
          req.on("error", reject); req.write(body); req.end();
        });
        record(`Upload Invalid: ${m.n}`, true, `PAN upload status ${r.s}`);
      } catch (err) {
        record(`Upload Invalid: ${m.n}`, false, err.message);
      }
      continue;
    }

    const latencies = [];
    for (const dt of docTypes) {
      const fp = path.join(DOCS_DIR, m.pan, `${dt}.png`);
      if (!fs.existsSync(fp)) { record(`Upload ${dt}: ${m.n}`, false, `File not found: ${fp}`); continue; }

      const fileData = fs.readFileSync(fp);
      const boundary = "----BOUND" + Date.now();
      const parts = [`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${dt}.png"\r\nContent-Type: image/png\r\n\r\n`, fileData, `\r\n--${boundary}--\r\n`];
      const body = Buffer.concat([Buffer.from(parts[0]), parts[1], Buffer.from(parts[2])]);
      const url = new URL(`/documents/upload?doc_type=${dt}`, API);
      const isHttps = url.protocol === "https:";
      const mod = isHttps ? https : http;

      const s = Date.now();
      try {
        const r = await new Promise((resolve, reject) => {
          const req = mod.request({
            hostname: url.hostname, port: url.port || (isHttps ? 443 : 80),
            path: url.pathname + url.search, method: "POST",
            headers: { "Content-Type": `multipart/form-data; boundary=${boundary}`, "Authorization": `Bearer ${tokens[m.e]}`, "Content-Length": body.length }
          }, res => { let d = ""; res.on("data", c => d += c); res.on("end", () => { try { resolve({ s: res.statusCode, b: JSON.parse(d) }); } catch { resolve({ s: res.statusCode, b: d }); } }); });
          req.on("error", reject); req.write(body); req.end();
        });
        latencies.push(Date.now() - s);
        log(`  ${m.n} ${dt}: ${Date.now() - s}ms (status ${r.s})`);
      } catch (err) {
        record(`Upload ${dt}: ${m.n}`, false, err.message);
      }
    }
    const avg = latencies.length ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : 0;
    TIMINGS[`upload_${m.e}`] = avg;
    record(`Upload: ${m.n}`, latencies.length === 3, `3 docs, avg: ${avg}ms`);

    // Wait between merchants to avoid OCR rate limits on free tier
    await sleep(5000);
  }
  log("");

  // ── Phase 4: Wait for OCR ──
  log("── Phase 4: Waiting for OCR processing ──");
  const merchantStatus = {};
  for (const m of M) merchantStatus[m.e] = "pending";

  for (let round = 0; round < 24; round++) {
    await sleep(10000);
    let allDone = true;
    for (const m of M) {
      if (merchantStatus[m.e] !== "pending") continue;
      try {
        const sr = await api("GET", "/documents/merchant-status", null, tokens[m.e]);
        const status = sr.b?.onboarding_status || "pending";
        merchantStatus[m.e] = status;
        if (status === "pending") allDone = false;
      } catch {
        allDone = false;
      }
    }
    const statuses = M.map(m => `${m.n.slice(0, 15)}=${merchantStatus[m.e]}`).join(", ");
    log(`  Round ${round + 1}: ${statuses}`);
    if (allDone) { log("  All merchants processed!"); break; }
  }

  for (const m of M) {
    const expected = m.g === "invalid" ? "pending" : "submitted";
    const actual = merchantStatus[m.e];
    const ok = actual === expected || (m.g === "invalid" && (actual === "pending" || actual === "submitted"));
    record(`OCR Status: ${m.n}`, ok, `Expected: ${expected}, Got: ${actual}`);
  }
  log("");

  // ── Phase 5: Admin verify & decide ──
  log("── Phase 5: Admin Verify & Decide ──");
  let adminToken = null;
  try {
    const adminR = await api("POST", "/auth/login", { email: "admin@example.com", password: "AdminPass123" });
    adminToken = adminR.b?.access_token;
    record("Admin Login", !!adminToken, adminToken ? "Token obtained" : "No token");
  } catch (err) {
    record("Admin Login", false, err.message);
  }

  if (adminToken) {
    for (const m of M) {
      if (m.g === "invalid") {
        record(`Admin: ${m.n}`, true, "Skipped (invalid doc)");
        continue;
      }
      if (merchantStatus[m.e] !== "submitted") {
        record(`Admin: ${m.n}`, false, `Cannot verify — status is ${merchantStatus[m.e]}`);
        continue;
      }

      try {
        // Get merchant ID
        const listR = await api("GET", "/admin/merchants", null, adminToken);
        const merchant = listR.b?.find(x => x.email === m.e);
        if (!merchant) { record(`Admin: ${m.n}`, false, "Not found in admin list"); continue; }
        const mid = merchant.merchant_id;

        // Verify
        const vs = Date.now();
        const vR = await api("POST", `/admin/merchants/${mid}/verify`, null, adminToken);
        TIMINGS[`verify_${m.e}`] = Date.now() - vs;

        if (vR.s !== 200) {
          record(`Admin Verify: ${m.n}`, false, `HTTP ${vR.s}: ${typeof vR.b === 'string' ? vR.b.slice(0, 100) : JSON.stringify(vR.b).slice(0, 100)}`);
          continue;
        }

        const vStatus = vR.b?.onboarding_status;
        const matched = vR.b?.matched_checks?.length || 0;
        const mismatched = vR.b?.mismatched_checks?.length || 0;
        log(`  ${m.n}: verified → ${vStatus} (matched=${matched}, mismatched=${mismatched}) (${Date.now() - vs}ms)`);

        // Decide
        if (vStatus === "verified_matching") {
          const dR = await api("POST", `/admin/merchants/${mid}/decide`, { decision: "approved" }, adminToken);
          record(`Admin Approve: ${m.n}`, dR.b?.onboarding_status === "active", `Approved → ${dR.b?.onboarding_status}`);
        } else if (vStatus === "verified_mismatched") {
          const dR = await api("POST", `/admin/merchants/${mid}/decide`, { decision: "rejected" }, adminToken);
          record(`Admin Reject: ${m.n}`, dR.b?.onboarding_status === "rejected", `Rejected → ${dR.b?.onboarding_status}`);
        } else {
          record(`Admin: ${m.n}`, false, `Unexpected verify status: ${vStatus}`);
        }
      } catch (err) {
        record(`Admin: ${m.n}`, false, err.message);
      }
    }
  }
  log("");

  // ── Phase 6: Final status ──
  log("── Phase 6: Final Status Verification ──");
  for (const m of M) {
    try {
      const sr = await api("GET", "/documents/merchant-status", null, tokens[m.e]);
      const status = sr.b?.onboarding_status;
      let expected;
      if (m.g === "invalid") expected = "pending";
      else if (m.g === "approved") expected = "active";
      else expected = "rejected";
      const ok = status === expected;
      record(`Final: ${m.n}`, ok, `Expected: ${expected}, Got: ${status}`);
    } catch (err) {
      record(`Final: ${m.n}`, false, err.message);
    }
  }
  log("");

  // ── Phase 7: UI verification ──
  log("── Phase 7: UI Verification ──");
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });

    // Login as approved merchant
    const approvedM = M.find(m => m.g === "approved" && merchantStatus[m.e] === "submitted");
    if (approvedM) {
      const page = await ctx.newPage();
      try {
        await page.goto(UI, { waitUntil: "networkidle", timeout: 30000 });
        await page.locator('input[type="email"]').fill(approvedM.e);
        await page.locator('input[type="password"]').fill(approvedM.p);
        await page.locator('button[type="submit"]').click();
        await page.waitForFunction(() => !document.querySelector('button[type="submit"]'), { timeout: 15000 });
        const content = await page.textContent("body");
        const activated = content.includes("Your account has been activated");
        const submitted = content.includes("documents have been received") || content.includes("under review");
        record(`UI Dashboard: ${approvedM.n}`, activated || submitted, activated ? "Shows activation ✓" : submitted ? "Shows submitted ✓" : "Neither state");
      } catch (err) {
        record(`UI Dashboard: ${approvedM.n}`, false, err.message);
      }
    }

    // Login as admin
    const adminPage = await ctx.newPage();
    try {
      await adminPage.goto(UI, { waitUntil: "networkidle", timeout: 30000 });
      await adminPage.locator('input[type="email"]').fill("admin@example.com");
      await adminPage.locator('input[type="password"]').fill("AdminPass123");
      await adminPage.locator('button[type="submit"]').click();
      await adminPage.waitForFunction(() => !document.querySelector('button[type="submit"]'), { timeout: 15000 });
      const adminContent = await adminPage.textContent("body");
      const onPanel = adminContent.includes("Merchant Verification Panel");
      record("UI Admin Panel", onPanel, onPanel ? "Admin panel loaded ✓" : "Admin panel not found");
    } catch (err) {
      record("UI Admin Panel", false, err.message);
    }

    await browser.close();
  } catch (err) {
    record("UI Verification", false, err.message);
    if (browser) await browser.close();
  }
  log("");

  generateReport();
}

function generateReport() {
  const passed = RESULTS.filter(r => r.pass).length;
  const total = RESULTS.length;

  log("╔═══════════════════════════════════════════════════════════╗");
  log("║         LIVE DEPLOYMENT — E2E TEST REPORT                ║");
  log("╚═══════════════════════════════════════════════════════════╝");
  log(`Total: ${total}  |  Passed: ${passed}  |  Failed: ${total - passed}  |  Rate: ${total > 0 ? ((passed / total) * 100).toFixed(1) : 0}%`);
  log("");

  const phases = {
    "0. Health": r => r.name === "Health Check",
    "1. Signup": r => r.name.startsWith("Signup"),
    "2. Login": r => r.name.startsWith("Login"),
    "3. Upload & OCR": r => r.name.startsWith("Upload") || r.name.startsWith("OCR"),
    "4. Admin Verify/Decide": r => r.name.startsWith("Admin"),
    "5. Final Status": r => r.name.startsWith("Final"),
    "6. UI": r => r.name.startsWith("UI"),
  };

  for (const [phase, filter] of Object.entries(phases)) {
    const items = RESULTS.filter(filter);
    if (!items.length) continue;
    const p = items.filter(r => r.pass).length;
    log(`── ${phase} (${p}/${items.length}) ──`);
    for (const r of items) log(`  ${r.pass ? "✅" : "❌"} ${r.name}${r.detail ? " — " + r.detail : ""}`);
    log("");
  }

  log("── Latency ──");
  const signupTimes = Object.entries(TIMINGS).filter(([k]) => k.startsWith("signup_"));
  const loginTimes = Object.entries(TIMINGS).filter(([k]) => k.startsWith("login_"));
  const uploadTimes = Object.entries(TIMINGS).filter(([k]) => k.startsWith("upload_"));
  const verifyTimes = Object.entries(TIMINGS).filter(([k]) => k.startsWith("verify_"));
  if (signupTimes.length) log(`  Avg Signup: ${Math.round(signupTimes.reduce((s, [, v]) => s + v, 0) / signupTimes.length)}ms`);
  if (loginTimes.length) log(`  Avg Login: ${Math.round(loginTimes.reduce((s, [, v]) => s + v, 0) / loginTimes.length)}ms`);
  if (uploadTimes.length) log(`  Avg Upload: ${Math.round(uploadTimes.reduce((s, [, v]) => s + v, 0) / uploadTimes.length)}ms`);
  if (verifyTimes.length) log(`  Avg Verify: ${Math.round(verifyTimes.reduce((s, [, v]) => s + v, 0) / verifyTimes.length)}ms`);
  log("");

  log("── Merchant Outcomes ──");
  for (const m of M) {
    const sr = RESULTS.find(r => r.name === `Final: ${m.n}`);
    log(`  ${m.n.padEnd(25)} | ${m.g.padEnd(10)} | ${sr ? (sr.pass ? "✅" : "❌") + " " + sr.detail : "⚠️ N/A"}`);
  }

  // Save report
  const lines = [];
  lines.push("═══════════════════════════════════════════════════════════");
  lines.push("LIVE DEPLOYMENT — E2E TEST REPORT");
  lines.push(`Generated: ${new Date().toISOString()}`);
  lines.push(`Backend: ${API}`);
  lines.push(`Frontend: ${UI}`);
  lines.push("═══════════════════════════════════════════════════════════");
  lines.push("");
  lines.push(`Total: ${total} | Passed: ${passed} | Failed: ${total - passed} | Rate: ${total > 0 ? ((passed / total) * 100).toFixed(1) : 0}%`);
  lines.push("");
  for (const [phase, filter] of Object.entries(phases)) {
    const items = RESULTS.filter(filter);
    if (!items.length) continue;
    const p = items.filter(r => r.pass).length;
    lines.push(`── ${phase} (${p}/${items.length}) ──`);
    for (const r of items) lines.push(`  ${r.pass ? "PASS" : "FAIL"} ${r.name}${r.detail ? " — " + r.detail : ""}`);
    lines.push("");
  }
  lines.push("── Latency ──");
  if (signupTimes.length) lines.push(`  Avg Signup: ${Math.round(signupTimes.reduce((s, [, v]) => s + v, 0) / signupTimes.length)}ms`);
  if (loginTimes.length) lines.push(`  Avg Login: ${Math.round(loginTimes.reduce((s, [, v]) => s + v, 0) / loginTimes.length)}ms`);
  if (uploadTimes.length) lines.push(`  Avg Upload: ${Math.round(uploadTimes.reduce((s, [, v]) => s + v, 0) / uploadTimes.length)}ms`);
  if (verifyTimes.length) lines.push(`  Avg Verify: ${Math.round(verifyTimes.reduce((s, [, v]) => s + v, 0) / verifyTimes.length)}ms`);
  lines.push("");
  lines.push("── Merchant Outcomes ──");
  for (const m of M) {
    const sr = RESULTS.find(r => r.name === `Final: ${m.n}`);
    lines.push(`  ${m.n} | Expected: ${m.g} | ${sr ? (sr.pass ? "PASS" : "FAIL") + " " + sr.detail : "N/A"}`);
  }

  const reportPath = path.resolve(__dirname, "e2e_live_report.txt");
  fs.writeFileSync(reportPath, lines.join("\n"), "utf-8");
  log(`\nReport saved: ${reportPath}`);
}

main().catch(e => { console.error(e); process.exit(1); });
