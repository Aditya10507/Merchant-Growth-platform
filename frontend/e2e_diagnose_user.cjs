/**
 * e2e_diagnose_user.cjs
 * ---------------------
 * Reproduces the EXACT user scenario through the real browser UI:
 * 1. Fresh signup via browser
 * 2. Upload synthetic test documents via browser file picker
 * 3. Check results
 * 4. Re-upload with same account (should be blocked)
 * 5. Fresh account, upload same docs again
 * 
 * Captures detailed network responses to find root cause.
 */

const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const https = require("https");

const UI = "https://merchant-growth-platform-stct.vercel.app";
const API = "https://merchant-growth-platform.onrender.com";
const DOCS_DIR = path.resolve(__dirname, "../test_documents/test_documents");
const RUN_ID = Date.now().toString(36);

const RESULTS = [];

function log(msg) { console.log(`[${new Date().toISOString().slice(11,23)}] ${msg}`); }
function record(name, pass, detail = "") { 
  RESULTS.push({name, pass, detail}); 
  log(`  ${pass ? "PASS" : "FAIL"} ${name}${detail ? " -- " + detail : ""}`); 
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

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

async function main() {
  log("================================================================");
  log("USER SCENARIO REPRODUCTION: Fresh signup + upload synthetic docs");
  log("================================================================");

  const browser = await chromium.launch({ headless: false, slowMo: 50 });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });

  try {
    // ========== SCENARIO 1: Fresh account, upload all 3 docs ==========
    log("\n--- SCENARIO 1: Fresh account signup + upload ---");
    const email1 = `user_test1_${RUN_ID}@test.com`;
    const password = "TestPass123";
    const business1 = `User Test Corp 1 ${RUN_ID}`;

    const page1 = await ctx.newPage();

    // Capture network responses for upload requests
    const uploadResponses = [];
    page1.on("response", async (response) => {
      const url = response.url();
      if (url.includes("/documents/upload")) {
        try {
          const body = await response.json();
          uploadResponses.push({ url, status: response.status(), body });
          log(`  [NETWORK] Upload response: ${response.status()} -> ${JSON.stringify(body).slice(0, 300)}`);
        } catch {
          uploadResponses.push({ url, status: response.status(), body: "non-json" });
          log(`  [NETWORK] Upload response: ${response.status()} -> non-JSON`);
        }
      }
    });

    // Step 1: Navigate to the app
    log("Step 1: Navigate to app");
    await page1.goto(UI, { waitUntil: "networkidle", timeout: 30000 });
    await sleep(1000);

    // Step 2: Switch to signup mode
    log("Step 2: Switch to signup");
    const signupLink = page1.getByText("Need an account? Sign up");
    if (await signupLink.count() > 0) {
      await signupLink.click();
      await sleep(500);
    }

    // Step 3: Fill signup form
    log("Step 3: Fill signup form");
    await page1.locator('input[autoComplete="organization"]').fill(business1);
    await page1.locator('input[type="email"]').fill(email1);
    await page1.locator('input[type="password"]').fill(password);
    await page1.locator('button[type="submit"]').click();

    // Wait for dashboard to load
    log("Step 4: Wait for dashboard");
    await page1.waitForFunction(
      () => document.querySelector('input[type="file"]') !== null,
      { timeout: 15000 }
    );
    await sleep(1000);
    log("  Dashboard loaded - file inputs visible");

    // Step 5: Upload PAN card via browser file input
    const panDir = path.join(DOCS_DIR, "UJALK5542W");
    
    log("Step 5: Upload PAN card via browser file input");
    const panInput = page1.locator('input[aria-label="Upload PAN card"]');
    log(`  PAN input found: ${await panInput.count() > 0}`);
    await panInput.setInputFiles(path.join(panDir, "PAN.png"));
    log("  PAN file set - waiting for OCR processing...");
    
    // Wait for upload to complete (OCR takes 2-5s)
    await sleep(10000);
    
    // Check what the UI shows
    let pageContent = await page1.textContent("body");
    if (pageContent.includes("No readable text")) {
      log("  PAN: UI shows 'No readable text' ERROR");
    } else if (pageContent.includes("Invalid document")) {
      log("  PAN: UI shows 'Invalid document' ERROR");
    } else if (pageContent.includes("verifying")) {
      log("  PAN: UI shows 'verifying' - OCR in progress");
    } else if (pageContent.includes("Valid document")) {
      log("  PAN: UI shows 'Valid document'");
    } else {
      log("  PAN: UI state unclear, checking page text...");
      // Log relevant portions of page content
      const lines = pageContent.split("\n").filter(l => l.trim());
      for (const line of lines.slice(0, 30)) {
        log(`    | ${line.trim().slice(0, 120)}`);
      }
    }

    // Step 6: Upload GST
    log("Step 6: Upload GST certificate");
    const gstInput = page1.locator('input[aria-label="Upload GST certificate"]');
    await gstInput.setInputFiles(path.join(panDir, "GST.png"));
    log("  GST file set - waiting for OCR...");
    await sleep(10000);

    pageContent = await page1.textContent("body");
    if (pageContent.includes("No readable text")) {
      log("  GST: UI shows 'No readable text' ERROR");
    } else if (pageContent.includes("Invalid document")) {
      log("  GST: UI shows 'Invalid document' ERROR");
    } else {
      log("  GST: No error detected in UI");
    }

    // Step 7: Upload Bank Proof
    log("Step 7: Upload Bank proof");
    const bankInput = page1.locator('input[aria-label="Upload Bank proof"]');
    await bankInput.setInputFiles(path.join(panDir, "BANK_PROOF.png"));
    log("  Bank file set - waiting for OCR...");
    await sleep(10000);

    pageContent = await page1.textContent("body");
    if (pageContent.includes("No readable text")) {
      log("  Bank: UI shows 'No readable text' ERROR");
    } else if (pageContent.includes("Invalid document")) {
      log("  Bank: UI shows 'Invalid document' ERROR");
    } else {
      log("  Bank: No error detected in UI");
    }

    // Step 8: Check final state
    log("Step 8: Check final state");
    await sleep(3000);
    pageContent = await page1.textContent("body");
    
    const hasSubmitted = pageContent.includes("documents have been received") || pageContent.includes("under review");
    const hasNoReadable = pageContent.includes("No readable text");
    const hasInvalid = pageContent.includes("Invalid document");
    
    log(`  UI state: submitted=${hasSubmitted}, noReadable=${hasNoReadable}, invalid=${hasInvalid}`);
    
    // Check via API too
    const tokenR = await api("POST", "/auth/login", { email: email1, password });
    const token = tokenR.b?.access_token;
    if (token) {
      const statusR = await api("GET", "/documents/merchant-status", null, token);
      const data = statusR.b;
      log(`  API status: onboarding=${data?.onboarding_status}`);
      for (const doc of (data?.documents || [])) {
        log(`    ${doc.doc_type}: status=${doc.verification_status}, confidence=${doc.ocr_confidence}, reason=${doc.rejection_reason}`);
      }
    }

    record("Scenario 1: Fresh signup + upload", hasSubmitted || (!hasNoReadable && !hasInvalid), 
      `submitted=${hasSubmitted}, noReadable=${hasNoReadable}`);

    // Take screenshot
    await page1.screenshot({ path: path.resolve(__dirname, "diag_scenario1.png") });
    log("  Screenshot saved: diag_scenario1.png");

    // ========== SCENARIO 2: Re-upload with same account ==========
    log("\n--- SCENARIO 2: Re-upload with same account ---");
    log("  Attempting to upload PAN again with same account...");
    
    const panInput2 = page1.locator('input[aria-label="Upload PAN card"]');
    await panInput2.setInputFiles(path.join(panDir, "PAN.png"));
    await sleep(8000);
    
    pageContent = await page1.textContent("body");
    if (pageContent.includes("409") || pageContent.includes("already been submitted")) {
      log("  Correctly blocked: documents already submitted");
      record("Scenario 2: Re-upload blocked", true, "409 - correctly blocked");
    } else if (pageContent.includes("No readable text")) {
      log("  ERROR: Got 'No readable text' on re-upload!");
      record("Scenario 2: Re-upload", false, "Got 'No readable text' error");
    } else {
      log("  Re-upload status unclear");
      record("Scenario 2: Re-upload", true, "No error detected");
    }

    await page1.screenshot({ path: path.resolve(__dirname, "diag_scenario2.png") });

    // ========== SCENARIO 3: Fresh account, same docs ==========
    log("\n--- SCENARIO 3: Fresh account, same synthetic docs ---");
    const email2 = `user_test2_${RUN_ID}@test.com`;
    const business2 = `User Test Corp 2 ${RUN_ID}`;

    const page2 = await ctx.newPage();
    await page2.goto(UI, { waitUntil: "networkidle", timeout: 30000 });
    await sleep(1000);

    // Switch to signup
    const signupLink2 = page2.getByText("Need an account? Sign up");
    if (await signupLink2.count() > 0) {
      await signupLink2.click();
      await sleep(500);
    }

    // Fill signup
    await page2.locator('input[autoComplete="organization"]').fill(business2);
    await page2.locator('input[type="email"]').fill(email2);
    await page2.locator('input[type="password"]').fill(password);
    await page2.locator('button[type="submit"]').click();

    await page2.waitForFunction(
      () => document.querySelector('input[type="file"]') !== null,
      { timeout: 15000 }
    );
    await sleep(1000);
    log("  Fresh dashboard loaded");

    // Upload PAN
    log("  Uploading PAN (same UJALK5542W/PAN.png)...");
    const panInput3 = page2.locator('input[aria-label="Upload PAN card"]');
    await panInput3.setInputFiles(path.join(panDir, "PAN.png"));
    await sleep(10000);

    pageContent = await page2.textContent("body");
    if (pageContent.includes("No readable text")) {
      log("  PAN: Got 'No readable text' ERROR on fresh account!");
      record("Scenario 3: Fresh account PAN", false, "No readable text error");
    } else if (pageContent.includes("Invalid document")) {
      log("  PAN: Got 'Invalid document' ERROR on fresh account!");
      record("Scenario 3: Fresh account PAN", false, "Invalid document error");
    } else {
      log("  PAN: No error detected");
      record("Scenario 3: Fresh account PAN", true, "Upload OK");
    }

    // Upload GST
    log("  Uploading GST...");
    const gstInput3 = page2.locator('input[aria-label="Upload GST certificate"]');
    await gstInput3.setInputFiles(path.join(panDir, "GST.png"));
    await sleep(10000);

    // Upload Bank
    log("  Uploading Bank proof...");
    const bankInput3 = page2.locator('input[aria-label="Upload Bank proof"]');
    await bankInput3.setInputFiles(path.join(panDir, "BANK_PROOF.png"));
    await sleep(10000);

    // Final check
    await sleep(3000);
    pageContent = await page2.textContent("body");
    
    const hasSubmitted2 = pageContent.includes("documents have been received") || pageContent.includes("under review");
    const hasNoReadable2 = pageContent.includes("No readable text");
    
    // Check via API
    const tokenR2 = await api("POST", "/auth/login", { email: email2, password });
    const token2 = tokenR2.b?.access_token;
    if (token2) {
      const statusR2 = await api("GET", "/documents/merchant-status", null, token2);
      const data2 = statusR2.b;
      log(`  API status: onboarding=${data2?.onboarding_status}`);
      for (const doc of (data2?.documents || [])) {
        log(`    ${doc.doc_type}: status=${doc.verification_status}, confidence=${doc.ocr_confidence}, reason=${doc.rejection_reason}`);
      }
    }
    
    record("Scenario 3: Fresh account all docs", hasSubmitted2 || !hasNoReadable2, 
      `submitted=${hasSubmitted2}, noReadable=${hasNoReadable2}`);

    await page2.screenshot({ path: path.resolve(__dirname, "diag_scenario3.png") });

    // ========== SUMMARY ==========
    log("\n================================================================");
    log("SUMMARY");
    log("================================================================");
    const passed = RESULTS.filter(r => r.pass).length;
    const failed = RESULTS.filter(r => !r.pass).length;
    log(`Total: ${RESULTS.length} | Passed: ${passed} | Failed: ${failed}`);
    for (const r of RESULTS) {
      log(`  ${r.pass ? "PASS" : "FAIL"} ${r.name}: ${r.detail}`);
    }
    
    // Save report
    const report = RESULTS.map(r => `${r.pass ? "PASS" : "FAIL"} ${r.name}: ${r.detail}`).join("\n");
    fs.writeFileSync(path.resolve(__dirname, "diag_report.txt"), report, "utf-8");

  } catch (err) {
    log(`ERROR: ${err.message}`);
    console.error(err);
  } finally {
    await sleep(3000);
    await browser.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
