/**
 * e2e_playwright_uc2.cjs
 * Use Case 2: Upload INVALID documents
 * - 1 invalid document (1x1 blank PNG uploaded as PAN) → should show invalid_format
 * - 2 valid documents (GST + Bank Proof from UJALK5542W)
 * - Verify invalid doc is rejected and valid docs are processed
 *
 * Runs in VISIBLE mode so you can watch the browser.
 */

const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const https = require("https");

const UI = "https://merchant-growth-platform-stct.vercel.app";
const API = "https://merchant-growth-platform.onrender.com";
const VALID_DOCS_DIR = path.resolve(__dirname, "../test_documents/test_documents/UJALK5542W");

const RUN_ID = Date.now().toString(36);
const EMAIL = `uc2_invalid_${RUN_ID}@test.com`;
const PASSWORD = "TestPass123";
const BUSINESS_NAME = `UC2 Invalid Corp ${RUN_ID}`;

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
  log("  USE CASE 2: 1 INVALID + 2 VALID DOCUMENTS");
  log("  Invalid: 1x1 blank PNG as PAN");
  log("  Valid: GST + Bank Proof from UJALK5542W");
  log("═══════════════════════════════════════════════════════════\n");

  // Create a fake 1x1 blank PNG for the invalid PAN upload
  const fakePngPath = path.resolve(__dirname, "fake_blank.png");
  const fakePng = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==", "base64");
  fs.writeFileSync(fakePngPath, fakePng);

  // Step 1: Sign up via API
  log("Step 1: Signing up merchant...");
  const signupR = await api("POST", "/auth/signup", {
    business_name: BUSINESS_NAME, email: EMAIL, password: PASSWORD,
  });
  log(`  Signup: ${signupR.s === 201 ? "✅ OK" : "❌ FAIL (" + signupR.s + ")"}`);

  // Step 2: Login via browser
  log("\nStep 2: Opening browser and logging in...");
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
    log("  Login: ✅ Reached dashboard");
    await sleep(1000);

    // Step 3: Upload INVALID PAN (1x1 blank PNG)
    log("\nStep 3: Uploading INVALID PAN (1x1 blank PNG)...");
    log("  Expected: Document should be marked invalid_format or rejected");
    const panInput = page.locator('input[aria-label="Upload PAN card"]');
    await panInput.setInputFiles(fakePngPath);
    log("  Invalid PAN uploaded — waiting for OCR processing...");
    await sleep(8000);

    // Take screenshot after invalid upload
    await page.screenshot({ path: path.resolve(__dirname, "screenshot_uc2_after_invalid.png") });
    log("  Screenshot saved: screenshot_uc2_after_invalid.png");

    // Step 4: Upload VALID GST
    log("\nStep 4: Uploading VALID GST certificate...");
    const gstInput = page.locator('input[aria-label="Upload GST certificate"]');
    await gstInput.setInputFiles(path.join(VALID_DOCS_DIR, "GST.png"));
    log("  GST uploaded — waiting for OCR processing...");
    await sleep(8000);

    // Step 5: Upload VALID Bank Proof
    log("\nStep 5: Uploading VALID Bank proof...");
    const bankInput = page.locator('input[aria-label="Upload Bank proof"]');
    await bankInput.setInputFiles(path.join(VALID_DOCS_DIR, "BANK_PROOF.png"));
    log("  Bank proof uploaded — waiting for OCR processing...");
    await sleep(8000);

    // Step 6: Check status via API
    log("\nStep 6: Checking document statuses...");
    const tokenR = await api("POST", "/auth/login", { email: EMAIL, password: PASSWORD });
    const token = tokenR.b?.access_token;
    const statusR = await api("GET", "/documents/merchant-status", null, token);
    const merchantStatus = statusR.b?.onboarding_status;
    const docs = statusR.b?.documents || [];

    log(`  Merchant status: ${merchantStatus}`);
    for (const doc of docs) {
      const icon = doc.verification_status === "invalid_format" || doc.verification_status === "rejected" ? "❌" : "✅";
      log(`  ${icon} ${doc.doc_type}: ${doc.verification_status} (confidence: ${doc.ocr_confidence ?? "null"})`);
      if (doc.rejection_reason) log(`     Reason: ${doc.rejection_reason}`);
      if (doc.extracted_fields) log(`     Fields: ${JSON.stringify(doc.extracted_fields)}`);
    }

    // Take final screenshot
    await page.screenshot({ path: path.resolve(__dirname, "screenshot_uc2_final.png") });
    log("\n  Screenshot saved: screenshot_uc2_final.png");

    // Evaluate result
    const invalidDocs = docs.filter(d => d.verification_status === "invalid_format" || d.verification_status === "rejected");
    const validDocs = docs.filter(d => d.verification_status !== "invalid_format" && d.verification_status !== "rejected");

    if (invalidDocs.length >= 1 && validDocs.length >= 2) {
      log("\n  ✅ USE CASE 2 PASSED:");
      log(`     - ${invalidDocs.length} invalid document(s) correctly rejected`);
      log(`     - ${validDocs.length} valid document(s) processed successfully`);
    } else if (invalidDocs.length >= 1) {
      log("\n  ⚠️ USE CASE 2 PARTIAL: Invalid doc rejected but not all valid docs processed");
    } else {
      log("\n  ❌ USE CASE 2 FAILED: No documents were rejected");
    }

  } catch (err) {
    log(`\n  ❌ ERROR: ${err.message}`);
    console.error(err);
  } finally {
    await sleep(3000);
    await browser.close();
    // Clean up fake PNG
    if (fs.existsSync(fakePngPath)) fs.unlinkSync(fakePngPath);
  }
}

main().catch(e => { console.error(e); process.exit(1); });
