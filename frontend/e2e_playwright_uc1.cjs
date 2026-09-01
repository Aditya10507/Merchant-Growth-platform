/**
 * e2e_playwright_uc1.cjs
 * Use Case 1: Upload ALL VALID documents
 * - Sign up as a new merchant
 * - Upload 3 valid documents (PAN, GST, Bank Proof) from UJALK5542W
 * - Verify OCR processes them and merchant status becomes "submitted"
 *
 * Runs in VISIBLE mode so you can watch the browser.
 */

const { chromium } = require("playwright");
const path = require("path");
const https = require("https");

const UI = "https://merchant-growth-platform-stct.vercel.app";
const API = "https://merchant-growth-platform.onrender.com";
const DOCS_DIR = path.resolve(__dirname, "../test_documents/test_documents/UJALK5542W");

const RUN_ID = Date.now().toString(36);
const EMAIL = `uc1_valid_${RUN_ID}@test.com`;
const PASSWORD = "TestPass123";
const BUSINESS_NAME = `UC1 Valid Corp ${RUN_ID}`;

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
  log("  USE CASE 1: ALL VALID DOCUMENTS");
  log("  Documents: UJALK5542W (PAN, GST, Bank Proof)");
  log("═══════════════════════════════════════════════════════════\n");

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

    // Step 3: Upload PAN card
    log("\nStep 3: Uploading PAN card (UJALK5542W/PAN.png)...");
    const panInput = page.locator('input[aria-label="Upload PAN card"]');
    await panInput.setInputFiles(path.join(DOCS_DIR, "PAN.png"));
    log("  PAN uploaded — waiting for OCR processing...");
    await sleep(8000); // Wait for synchronous OCR

    // Step 4: Upload GST certificate
    log("\nStep 4: Uploading GST certificate (UJALK5542W/GST.png)...");
    const gstInput = page.locator('input[aria-label="Upload GST certificate"]');
    await gstInput.setInputFiles(path.join(DOCS_DIR, "GST.png"));
    log("  GST uploaded — waiting for OCR processing...");
    await sleep(8000);

    // Step 5: Upload Bank proof
    log("\nStep 5: Uploading Bank proof (UJALK5542W/BANK_PROOF.png)...");
    const bankInput = page.locator('input[aria-label="Upload Bank proof"]');
    await bankInput.setInputFiles(path.join(DOCS_DIR, "BANK_PROOF.png"));
    log("  Bank proof uploaded — waiting for OCR processing...");
    await sleep(8000);

    // Step 6: Check final status
    log("\nStep 6: Checking final merchant status...");
    const pageContent = await page.textContent("body");

    if (pageContent.includes("Your documents have been received")) {
      log("  Status: ✅ 'Your documents have been received' — merchant submitted!");
    } else if (pageContent.includes("under review")) {
      log("  Status: ✅ Documents under review — merchant submitted!");
    } else if (pageContent.includes("awaiting")) {
      log("  Status: ✅ Awaiting review — merchant submitted!");
    } else {
      log("  Status: ⚠️ Unexpected state — checking API...");
    }

    // Also verify via API
    const tokenR = await api("POST", "/auth/login", { email: EMAIL, password: PASSWORD });
    const token = tokenR.b?.access_token;
    const statusR = await api("GET", "/documents/merchant-status", null, token);
    const merchantStatus = statusR.b?.onboarding_status;
    const docs = statusR.b?.documents || [];

    log(`\n  API Status: ${merchantStatus}`);
    log(`  Documents:`);
    for (const doc of docs) {
      log(`    - ${doc.doc_type}: ${doc.verification_status} (confidence: ${doc.ocr_confidence ?? "null"})`);
      if (doc.extracted_fields) log(`      Fields: ${JSON.stringify(doc.extracted_fields)}`);
    }

    if (merchantStatus === "submitted") {
      log("\n  ✅ USE CASE 1 PASSED: All 3 valid documents processed, merchant submitted!");
    } else {
      log(`\n  ❌ USE CASE 1 RESULT: Merchant status is "${merchantStatus}" (expected "submitted")`);
    }

    // Take screenshot
    await page.screenshot({ path: path.resolve(__dirname, "screenshot_uc1.png") });
    log("\n  Screenshot saved: frontend/screenshot_uc1.png");

  } catch (err) {
    log(`\n  ❌ ERROR: ${err.message}`);
    console.error(err);
  } finally {
    await sleep(3000); // Keep browser open briefly so user can see
    await browser.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
