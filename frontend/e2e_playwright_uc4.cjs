/**
 * e2e_playwright_uc4.cjs
 * Use Case 4: All valid documents but WRONG/MISMATCHED for admin verification
 * - Upload 3 valid documents (VDAWP9860F — a PAN from the "mismatch" group)
 * - Documents are real images, OCR will extract text successfully
 * - But admin verification will find mismatches in external databases
 *   (PAN marked as "invalid" in govt DB, bank account not verified, etc.)
 * - Admin should reject the merchant
 *
 * Runs in VISIBLE mode so you can watch the browser.
 */

const { chromium } = require("playwright");
const path = require("path");
const https = require("https");

const UI = "https://merchant-growth-platform-stct.vercel.app";
const API = "https://merchant-growth-platform.onrender.com";
const DOCS_DIR = path.resolve(__dirname, "../test_documents/test_documents/VDAWP9860F");

const RUN_ID = Date.now().toString(36);
const EMAIL = `uc4_mismatch_${RUN_ID}@test.com`;
const PASSWORD = "TestPass123";
const BUSINESS_NAME = `UC4 Mismatch Corp ${RUN_ID}`;

function log(msg) { console.log(`[${new Date().toISOString().slice(11, 23)}] ${msg}`); }

function api(method, p, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(p, API);
    const opts = {
      hostname: url.hostname, port: 443, path: url.pathname + url.search,
      method, headers: { "Content-Type": "application/json" },
    };
    if (token) opts.headers["Authorization"] = `Bearer ${token}`;
    const req = https.request(opts, res => {
      let d = ""; res.on("data", c => d += c);
      res.on("end", () => { try { resolve({ s: res.statusCode, b: JSON.parse(d) }); } catch { resolve({ s: res.statusCode, b: d }); } });
    });
    req.on("error", reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  log("═══════════════════════════════════════════════════════════");
  log("  USE CASE 4: VALID DOCS BUT MISMATCHED FOR VERIFICATION");
  log("  Documents: VDAWP9860F (PAN, GST, Bank Proof)");
  log("  PAN is marked 'invalid' in government database");
  log("  Bank account not in validation database");
  log("═══════════════════════════════════════════════════════════\n");

  // Step 1: Sign up + login
  log("Step 1: Signing up and logging in...");
  await api("POST", "/auth/signup", { business_name: BUSINESS_NAME, email: EMAIL, password: PASSWORD });

  const browser = await chromium.launch({ headless: false, slowMo: 100 });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();

  try {
    await page.goto(UI, { waitUntil: "networkidle", timeout: 30000 });
    await sleep(1000);
    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForFunction(() => !document.querySelector('button[type="submit"]'), { timeout: 10000 });
    log("  ✅ Merchant logged in\n");

    // Step 2: Upload all 3 documents
    log("Step 2: Uploading 3 documents (VDAWP9860F)...");
    await page.locator('input[aria-label="Upload PAN card"]').setInputFiles(path.join(DOCS_DIR, "PAN.png"));
    log("  PAN uploaded — processing...");
    await sleep(8000);

    await page.locator('input[aria-label="Upload GST certificate"]').setInputFiles(path.join(DOCS_DIR, "GST.png"));
    log("  GST uploaded — processing...");
    await sleep(8000);

    await page.locator('input[aria-label="Upload Bank proof"]').setInputFiles(path.join(DOCS_DIR, "BANK_PROOF.png"));
    log("  Bank proof uploaded — processing...");
    await sleep(8000);

    // Check merchant status
    const tokenR = await api("POST", "/auth/login", { email: EMAIL, password: PASSWORD });
    const merchantToken = tokenR.b?.access_token;
    const statusR = await api("GET", "/documents/merchant-status", null, merchantToken);
    log(`  Merchant status: ${statusR.b?.onboarding_status}`);
    for (const doc of statusR.b?.documents || []) {
      log(`    - ${doc.doc_type}: ${doc.verification_status} (confidence: ${doc.ocr_confidence ?? "null"})`);
      if (doc.extracted_fields) log(`      Fields: ${JSON.stringify(doc.extracted_fields)}`);
    }

    // Step 3: Login as admin
    log("\nStep 3: Logging in as admin...");
    const adminPage = await ctx.newPage();
    await adminPage.goto(UI, { waitUntil: "networkidle", timeout: 30000 });
    await sleep(1000);
    await adminPage.locator('input[type="email"]').fill("admin@example.com");
    await adminPage.locator('input[type="password"]').fill("AdminPass123");
    await adminPage.locator('button[type="submit"]').click();
    await adminPage.waitForFunction(() => !document.querySelector('button[type="submit"]'), { timeout: 10000 });
    log("  ✅ Admin logged in\n");
    await sleep(2000);

    // Step 4: Find and click on the merchant
    log("Step 4: Finding merchant in admin panel...");
    const merchantRow = adminPage.getByText(BUSINESS_NAME).first();
    if (await merchantRow.count() > 0) {
      await merchantRow.click();
      await sleep(2000);
      log(`  ✅ Found and clicked on "${BUSINESS_NAME}"`);
    } else {
      log(`  ❌ Merchant "${BUSINESS_NAME}" not found in admin panel`);
      return;
    }

    // Step 5: Click "Verify with internal databases"
    log("\nStep 5: Running admin verification...");
    const verifyBtn = adminPage.getByRole("button", { name: /Verify with internal databases/i }).first();
    if (await verifyBtn.count() > 0) {
      await verifyBtn.click();
      log("  ⏳ Verification running (LLM + external checks)...");
      await sleep(10000);
      log("  ✅ Verification complete");
    } else {
      log("  ❌ Verify button not found");
    }

    // Take screenshot of verification results
    await adminPage.screenshot({ path: path.resolve(__dirname, "screenshot_uc4_verified.png") });
    log("  Screenshot saved: screenshot_uc4_verified.png");

    // Step 6: Check verification result
    log("\nStep 6: Checking verification result...");
    const adminTokenR = await api("POST", "/auth/login", { email: "admin@example.com", password: "AdminPass123" });
    const adminToken = adminTokenR.b?.access_token;
    const listR = await api("GET", "/admin/merchants", null, adminToken);
    const merchant = listR.b?.find(m => m.email === EMAIL);
    if (merchant) {
      const detailR = await api("GET", `/admin/merchants/${merchant.merchant_id}`, null, adminToken);
      const detail = detailR.b;
      log(`  Status: ${detail.onboarding_status}`);
      log(`  Risk Score: ${detail.risk_score}`);
      if (detail.matched_checks?.length) {
        log(`  Matched checks (${detail.matched_checks.length}):`);
        for (const c of detail.matched_checks) log(`    ✅ ${c.check_name} (${c.document_type}): ${c.detail}`);
      }
      if (detail.mismatched_checks?.length) {
        log(`  Mismatched checks (${detail.mismatched_checks.length}):`);
        for (const c of detail.mismatched_checks) log(`    ❌ ${c.check_name} (${c.document_type}): ${c.detail}`);
      }
      if (detail.rejection_cause) {
        log(`  Rejection cause: ${detail.rejection_cause}`);
      }

      // Step 7: Reject if verified_mismatched
      if (detail.onboarding_status === "verified_mismatched") {
        log("\nStep 7: Merchant verified as MISMATCHED — rejecting...");
        const rejectBtn = adminPage.getByRole("button", { name: /Reject/i }).first();
        if (await rejectBtn.count() > 0) {
          await rejectBtn.click();
          await sleep(2000);
          log("  ✅ Rejected!");
        }
      } else if (detail.onboarding_status === "verified_matching") {
        log("\n  ⚠️ Unexpected: Merchant verified as MATCHING (should be mismatched)");
      }
    }

    // Take final screenshot
    await adminPage.screenshot({ path: path.resolve(__dirname, "screenshot_uc4_final.png") });
    log("\n  Screenshot saved: screenshot_uc4_final.png");

    // Final status
    const finalStatusR = await api("GET", "/documents/merchant-status", null, merchantToken);
    const finalStatus = finalStatusR.b?.onboarding_status;
    log(`\n  Final merchant status: ${finalStatus}`);

    if (finalStatus === "rejected" || finalStatus === "verified_mismatched") {
      log("\n  ✅ USE CASE 4 PASSED: Mismatched merchant correctly identified and rejected!");
    } else {
      log(`\n  ⚠️ USE CASE 4 RESULT: Status is "${finalStatus}"`);
    }

  } catch (err) {
    log(`\n  ❌ ERROR: ${err.message}`);
    console.error(err);
  } finally {
    await sleep(3000);
    await browser.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
