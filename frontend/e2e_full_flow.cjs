/**
 * e2e_full_flow.js
 * ----------------
 * Comprehensive E2E test for the Merchant Onboarding Copilot.
 *
 * Tests covered:
 *   1. Merchant Signup (6 accounts via API for speed)
 *   2. Merchant Login (via UI)
 *   3. Document Upload with latency measurement (via UI)
 *   4. Invalid Document Handling (via UI)
 *   5. Admin Panel — Merchant List & Detail View (via UI)
 *   6. Admin Verification & Decision — Approve/Reject (via UI)
 *   7. Merchant Status Updates after Admin Decision (via UI)
 *
 * Run:  node e2e_full_flow.cjs
 */

const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const http = require("http");

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const BASE_URL = "http://localhost:5173";
const API_URL = "http://localhost:8000";
const DOCS_DIR = path.resolve(__dirname, "../test_documents/test_documents");

const RESULTS = [];
const TIMINGS = {};

// ---------------------------------------------------------------------------
// Merchant test accounts
// ---------------------------------------------------------------------------
const MERCHANTS = [
  // Group 1: Valid documents, expect approval
  { name: "Clean Corp Alpha", email: "clean_alpha_e2e@test.com", password: "TestPass123", pan: "UJALK5542W", group: "valid_approved", expectStatus: "active" },
  { name: "Clean Corp Beta",  email: "clean_beta_e2e@test.com",  password: "TestPass123", pan: "HAOEL7625O", group: "valid_approved", expectStatus: "active" },
  { name: "Clean Corp Gamma", email: "clean_gamma_e2e@test.com", password: "TestPass123", pan: "CCZEE2615Q", group: "valid_approved", expectStatus: "active" },
  // Group 2: Invalid document
  { name: "Invalid Doc Corp", email: "invalid_e2e@test.com", password: "TestPass123", pan: "INVALID", group: "invalid_doc", expectStatus: "invalid_format" },
  // Group 3: Valid docs but mismatched in databases
  { name: "Mismatch Corp A", email: "mismatch_a_e2e@test.com", password: "TestPass123", pan: "VDAWP9860F", group: "valid_mismatched", expectStatus: "rejected" },
  { name: "Mismatch Corp B", email: "mismatch_b_e2e@test.com", password: "TestPass123", pan: "RFBPO7258K", group: "valid_mismatched", expectStatus: "rejected" },
];

const ADMIN = { email: "admin@example.com", password: "AdminPass123" };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function log(msg) {
  const ts = new Date().toISOString().slice(11, 23);
  console.log(`[${ts}] ${msg}`);
}

function record(testName, passed, details = "") {
  RESULTS.push({ testName, passed, details });
  const icon = passed ? "✅ PASS" : "❌ FAIL";
  log(`${icon}  ${testName}${details ? " — " + details : ""}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Make an API request. */
function apiRequest(method, path, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, API_URL);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (token) options.headers["Authorization"] = `Bearer ${token}`;

    const req = http.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, body: data });
        }
      });
    });
    req.on("error", reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

/** Signup via API (much faster than UI). */
async function signupAPI(merchant) {
  const start = Date.now();
  const res = await apiRequest("POST", "/auth/signup", {
    business_name: merchant.name,
    email: merchant.email,
    password: merchant.password,
  });
  const elapsed = Date.now() - start;
  TIMINGS[`signup_${merchant.email}`] = elapsed;
  const ok = res.status === 201;
  record(
    `Signup: ${merchant.name}`,
    ok,
    ok ? `Account created in ${elapsed}ms` : `Failed (${res.status}): ${JSON.stringify(res.body)}`
  );
  return ok;
}

/** Login via UI and return the page. */
async function loginUI(context, email, password, label) {
  const page = await context.newPage();
  const start = Date.now();

  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.waitForSelector('button[type="submit"]', { timeout: 10000 });

  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();

  // Wait for auth page to disappear
  await page.waitForFunction(
    () => !document.querySelector('button[type="submit"]'),
    { timeout: 10000 }
  );

  const elapsed = Date.now() - start;
  TIMINGS[`login_${email}`] = elapsed;
  return { page, elapsed };
}

/** Upload a document via the file input. */
async function uploadDoc(page, docType, filePath) {
  const start = Date.now();
  const slotLabels = { PAN: "PAN card", GST: "GST certificate", BANK_PROOF: "Bank proof" };
  const label = slotLabels[docType];
  const input = page.locator(`input[aria-label="Upload ${label}"]`);
  await input.setInputFiles(filePath);
  await sleep(1500);
  return Date.now() - start;
}

// ---------------------------------------------------------------------------
// Main test flow
// ---------------------------------------------------------------------------
async function main() {
  log("Starting comprehensive E2E test suite...");
  log("");

  const browser = await chromium.launch({ headless: false, slowMo: 50 });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });

  try {
    // ====================================================================
    // PHASE 1: SIGNUP (via API for speed)
    // ====================================================================
    log("═══════════════════════════════════════════════════════════");
    log("PHASE 1: Merchant Signup (via API)");
    log("═══════════════════════════════════════════════════════════");
    for (const m of MERCHANTS) await signupAPI(m);
    log("");

    // ====================================================================
    // PHASE 2: LOGIN (via UI)
    // ====================================================================
    log("═══════════════════════════════════════════════════════════");
    log("PHASE 2: Merchant Login (via UI)");
    log("═══════════════════════════════════════════════════════════");

    const merchantPages = {};
    for (const m of MERCHANTS) {
      try {
        const { page, elapsed } = await loginUI(context, m.email, m.password, m.name);
        merchantPages[m.email] = page;
        const onDashboard = (await page.getByText("Complete your onboarding").count()) > 0;
        record(`Login: ${m.name}`, onDashboard, `Login ${elapsed}ms — ${onDashboard ? "reached dashboard" : "FAIL"}`);
      } catch (err) {
        record(`Login: ${m.name}`, false, err.message);
      }
    }
    log("");

    // ====================================================================
    // PHASE 3: DOCUMENT UPLOAD
    // ====================================================================
    log("═══════════════════════════════════════════════════════════");
    log("PHASE 3: Document Upload with Latency");
    log("═══════════════════════════════════════════════════════════");

    const docTypes = ["PAN", "GST", "BANK_PROOF"];

    for (const m of MERCHANTS) {
      const page = merchantPages[m.email];
      if (!page) { record(`Upload: ${m.name}`, false, "No page available"); continue; }

      log(`  Uploading for: ${m.name}`);

      if (m.group === "invalid_doc") {
        // Upload a .txt file (client-side will reject it)
        const txtFile = path.join(DOCS_DIR, "invalid_test.txt");
        if (!fs.existsSync(txtFile)) fs.writeFileSync(txtFile, "This is not a valid document");
        const elapsed = await uploadDoc(page, "PAN", txtFile);
        TIMINGS[`upload_invalid_${m.email}`] = elapsed;
        await sleep(1000);
        // Check for client-side error
        const errorAlert = (await page.locator('[role="alert"]').count()) > 0;
        record(`Upload Invalid: ${m.name}`, errorAlert, `Uploaded .txt in ${elapsed}ms — client rejected: ${errorAlert}`);
        continue;
      }

      const latencies = [];
      for (const dt of docTypes) {
        const fp = path.join(DOCS_DIR, m.pan, `${dt}.png`);
        if (!fs.existsSync(fp)) { record(`Upload ${dt}: ${m.name}`, false, `File not found: ${fp}`); continue; }
        const elapsed = await uploadDoc(page, dt, fp);
        latencies.push(elapsed);
        log(`    ${dt}: ${elapsed}ms`);
        await sleep(3000); // Wait for OCR
      }

      const avg = latencies.length ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : 0;
      TIMINGS[`upload_avg_${m.email}`] = avg;
      record(`Upload Docs: ${m.name}`, latencies.length === 3, `3 docs, avg: ${avg}ms`);

      // Wait for OCR processing and status update
      await sleep(8000);
      const pageContent = await page.textContent("body");
      const submitted = pageContent.includes("Your documents have been received");
      record(`Submit Status: ${m.name}`, submitted, submitted ? "Documents submitted ✓" : "Still processing");
    }
    log("");

    // ====================================================================
    // PHASE 4: ADMIN LOGIN & PANEL
    // ====================================================================
    log("═══════════════════════════════════════════════════════════");
    log("PHASE 4: Admin Login & Panel");
    log("═══════════════════════════════════════════════════════════");

    const { page: adminPage, elapsed: adminElapsed } = await loginUI(context, ADMIN.email, ADMIN.password, "Admin");
    TIMINGS["login_admin"] = adminElapsed;
    const onAdmin = (await adminPage.getByText("Merchant Verification Panel").count()) > 0;
    record("Login: Admin", onAdmin, `Admin login ${adminElapsed}ms — ${onAdmin ? "reached panel" : "FAIL"}`);

    await sleep(1000);

    // Check merchant list
    let found = 0;
    for (const m of MERCHANTS) {
      if ((await adminPage.getByText(m.name).count()) > 0) found++;
    }
    record("Admin Panel: Merchant List", found >= 5, `Found ${found}/${MERCHANTS.length} test merchants`);
    log("");

    // ====================================================================
    // PHASE 5: ADMIN VERIFICATION & DECISION
    // ====================================================================
    log("═══════════════════════════════════════════════════════════");
    log("PHASE 5: Admin Verification & Decision");
    log("═══════════════════════════════════════════════════════════");

    for (const m of MERCHANTS.filter((x) => x.group !== "invalid_doc")) {
      log(`  Processing: ${m.name} (expect: ${m.expectStatus})`);
      try {
        // Reload admin panel for clean state
        await adminPage.reload({ waitUntil: "networkidle" });
        await sleep(1000);

        // Click merchant row
        await adminPage.getByText(m.name).first().click();
        await sleep(1500);

        const detail = adminPage.locator('[aria-label="Merchant detail"]');
        if ((await detail.count()) === 0) {
          record(`Admin Action: ${m.name}`, false, "Detail panel not visible");
          continue;
        }

        // Check if verify button exists
        const verifyBtn = adminPage.getByRole("button", { name: /Verify with internal databases/i }).first();
        if ((await verifyBtn.count()) > 0) {
          const vStart = Date.now();
          await verifyBtn.click();
          await sleep(10000); // Wait for LLM + external checks
          TIMINGS[`verify_${m.email}`] = Date.now() - vStart;
          log(`    Verified in ${Date.now() - vStart}ms`);
        }

        // Read post-verification state
        const detailText = await detail.textContent();
        const isMatching = detailText.includes("All checks matched");
        const isMismatched = detailText.includes("Mismatches found");
        log(`    State: matching=${isMatching}, mismatched=${isMismatched}`);

        if (isMatching) {
          const approveBtn = adminPage.getByRole("button", { name: /Approve/i }).first();
          if ((await approveBtn.count()) > 0) {
            await approveBtn.click();
            await sleep(1500);
            record(`Admin Approve: ${m.name}`, true, "All checks matched → Approved");
          } else {
            record(`Admin Approve: ${m.name}`, false, "Approve button missing");
          }
        } else if (isMismatched) {
          const rejectBtn = adminPage.getByRole("button", { name: /Reject/i }).first();
          if ((await rejectBtn.count()) > 0) {
            await rejectBtn.click();
            await sleep(1500);
            record(`Admin Reject: ${m.name}`, true, "Mismatches found → Rejected");
          } else {
            record(`Admin Reject: ${m.name}`, false, "Reject button missing");
          }
        } else {
          record(`Admin Decision: ${m.name}`, false, "Unexpected state — neither matching nor mismatched");
        }
      } catch (err) {
        record(`Admin Action: ${m.name}`, false, err.message);
      }
    }
    log("");

    // ====================================================================
    // PHASE 6: MERCHANT STATUS CHECKS
    // ====================================================================
    log("═══════════════════════════════════════════════════════════");
    log("PHASE 6: Merchant Status After Admin Decision");
    log("═══════════════════════════════════════════════════════════");

    for (const m of MERCHANTS) {
      const page = merchantPages[m.email];
      if (!page) { record(`Status: ${m.name}`, false, "No page"); continue; }

      try {
        await page.reload({ waitUntil: "networkidle" });
        await sleep(2000);
        const content = await page.textContent("body");

        if (m.group === "invalid_doc") {
          const ok = content.includes("Please upload") || content.includes("invalid") || content.includes("not a valid");
          record(`Status: ${m.name}`, ok, `Expected invalid_format — ${ok ? "Error shown ✓" : "No error shown"}`);
        } else if (m.group === "valid_approved") {
          const ok = content.includes("Your account has been activated");
          record(`Status: ${m.name}`, ok, `Expected active — ${ok ? "Activated ✓" : "Not activated yet"}`);
        } else if (m.group === "valid_mismatched") {
          const ok = content.includes("Start a new application") || content.includes("was not approved");
          record(`Status: ${m.name}`, ok, `Expected rejected — ${ok ? "Rejected ✓" : "Not rejected yet"}`);
        }
      } catch (err) {
        record(`Status: ${m.name}`, false, err.message);
      }
    }
  } catch (err) {
    log(`Fatal: ${err.message}`);
    console.error(err);
  } finally {
    await browser.close();
  }

  // ====================================================================
  // REPORT
  // ====================================================================
  generateReport();
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------
function generateReport() {
  log("");
  log("╔═══════════════════════════════════════════════════════════╗");
  log("║          FINAL TEST REPORT — E2E Full Flow               ║");
  log("╚═══════════════════════════════════════════════════════════╝");
  log("");

  const passed = RESULTS.filter((r) => r.passed).length;
  const failed = RESULTS.filter((r) => !r.passed).length;
  const total = RESULTS.length;

  log(`Total: ${total}  |  Passed: ${passed}  |  Failed: ${failed}  |  Rate: ${total > 0 ? ((passed / total) * 100).toFixed(1) : 0}%`);
  log("");

  const phases = {
    "1. Signup": RESULTS.filter((r) => r.testName.startsWith("Signup")),
    "2. Login": RESULTS.filter((r) => r.testName.startsWith("Login")),
    "3. Document Upload": RESULTS.filter((r) => r.testName.startsWith("Upload") || r.testName.startsWith("Submit")),
    "4. Admin Panel": RESULTS.filter((r) => r.testName.startsWith("Admin")),
    "5. Status Checks": RESULTS.filter((r) => r.testName.startsWith("Status")),
  };

  for (const [phase, results] of Object.entries(phases)) {
    if (!results.length) continue;
    const p = results.filter((r) => r.passed).length;
    log(`── ${phase} (${p}/${results.length}) ──`);
    for (const r of results) {
      log(`  ${r.passed ? "✅" : "❌"} ${r.testName}`);
      if (r.details) log(`     ${r.details}`);
    }
    log("");
  }

  // Latency
  log("── Latency Summary ──");
  for (const [key, val] of Object.entries(TIMINGS).sort()) {
    if (key.startsWith("signup_")) log(`  Signup (${key.replace("signup_", "")}): ${val}ms`);
    if (key.startsWith("login_")) log(`  Login (${key.replace("login_", "")}): ${val}ms`);
    if (key.startsWith("upload_avg_")) log(`  Upload avg (${key.replace("upload_avg_", "")}): ${val}ms`);
    if (key.startsWith("verify_")) log(`  Verify (${key.replace("verify_", "")}): ${val}ms`);
  }
  log("");

  // Merchant summary
  log("── Merchant Outcomes ──");
  for (const m of MERCHANTS) {
    const sr = RESULTS.find((r) => r.testName === `Status: ${m.name}`);
    log(`  ${m.name.padEnd(25)} | ${m.group.padEnd(18)} | Expected: ${m.expectStatus.padEnd(15)} | ${sr ? (sr.passed ? "✅" : "❌") : "⚠️"}`);
  }
  log("");
  log(`═══════════════════════════════════════════════════════════`);
  log(`  OVERALL: ${passed}/${total} passed (${total > 0 ? ((passed / total) * 100).toFixed(1) : 0}%)`);
  log(`═══════════════════════════════════════════════════════════`);

  // Write report file
  const lines = [];
  lines.push("═══════════════════════════════════════════════════════════");
  lines.push("     MERCHANT ONBOARDING — E2E TEST REPORT");
  lines.push(`     Generated: ${new Date().toISOString()}`);
  lines.push("═══════════════════════════════════════════════════════════");
  lines.push("");
  lines.push(`Total: ${total}  |  Passed: ${passed}  |  Failed: ${failed}  |  Rate: ${total > 0 ? ((passed / total) * 100).toFixed(1) : 0}%`);
  lines.push("");
  for (const [phase, results] of Object.entries(phases)) {
    if (!results.length) continue;
    const p = results.filter((r) => r.passed).length;
    lines.push(`── ${phase} (${p}/${results.length}) ──`);
    for (const r of results) {
      lines.push(`  ${r.passed ? "PASS" : "FAIL"}  ${r.testName}`);
      if (r.details) lines.push(`       ${r.details}`);
    }
    lines.push("");
  }
  lines.push("── Latency ──");
  for (const [key, val] of Object.entries(TIMINGS).sort()) {
    lines.push(`  ${key}: ${val}ms`);
  }
  lines.push("");
  lines.push("── Merchant Outcomes ──");
  for (const m of MERCHANTS) {
    const sr = RESULTS.find((r) => r.testName === `Status: ${m.name}`);
    lines.push(`  ${m.name} | ${m.group} | Expected: ${m.expectStatus} | ${sr ? (sr.passed ? "PASS" : "FAIL") : "N/A"}`);
    if (sr && sr.details) lines.push(`    ${sr.details}`);
  }

  const reportPath = path.resolve(__dirname, "e2e_report.txt");
  fs.writeFileSync(reportPath, lines.join("\n"), "utf-8");
  log(`Report saved: ${reportPath}`);
}

main().catch((err) => { console.error("Unhandled:", err); process.exit(1); });
