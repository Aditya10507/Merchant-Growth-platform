/**
 * e2e_diagnose.cjs — Diagnostic script to find exact OCR and verification errors
 */

const https = require("https");
const http = require("http");

const API = "https://merchant-growth-platform.onrender.com";

function api(method, p, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(p, API);
    const mod = url.protocol === "https:" ? https : http;
    const opts = {
      hostname: url.hostname,
      port: url.port || (url.protocol === "https:" ? 443 : 80),
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

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.log("═══ DIAGNOSTIC: Checking document-level statuses ═══\n");

  // Login as admin to see full details
  const adminR = await api("POST", "/auth/login", { email: "admin@example.com", password: "AdminPass123" });
  const adminToken = adminR.b?.access_token;
  console.log("Admin login:", adminToken ? "OK" : "FAILED");

  // Get all merchants
  const listR = await api("GET", "/admin/merchants", null, adminToken);
  const merchants = listR.b || [];
  console.log(`\nTotal merchants in system: ${merchants.length}\n`);

  // Check the most recent merchants (from our test)
  const testMerchants = merchants.filter(m => m.email.includes("@test.com")).slice(-12);

  for (const m of testMerchants) {
    console.log(`\n─────────────────────────────────────────`);
    console.log(`Merchant: ${m.business_name}`);
    console.log(`  Email: ${m.email}`);
    console.log(`  Status: ${m.onboarding_status}`);
    console.log(`  Risk Score: ${m.risk_score}`);

    // Get full detail
    const detailR = await api("GET", `/admin/merchants/${m.merchant_id}`, null, adminToken);
    const detail = detailR.b;
    if (!detail) { console.log("  ❌ Could not fetch detail"); continue; }

    // Document statuses
    console.log(`  Documents:`);
    for (const doc of detail.documents || []) {
      console.log(`    - ${doc.doc_type}: status=${doc.verification_status}, confidence=${doc.ocr_confidence}`);
      if (doc.rejection_reason) console.log(`      Rejection reason: ${doc.rejection_reason}`);
      if (doc.extracted_fields) console.log(`      Extracted fields: ${JSON.stringify(doc.extracted_fields)}`);
    }

    // Verification breakdown
    if (detail.matched_checks?.length) {
      console.log(`  Matched checks (${detail.matched_checks.length}):`);
      for (const c of detail.matched_checks) {
        console.log(`    ✅ ${c.check_name} (${c.document_type}): ${c.detail}`);
      }
    }
    if (detail.mismatched_checks?.length) {
      console.log(`  Mismatched checks (${detail.mismatched_checks.length}):`);
      for (const c of detail.mismatched_checks) {
        console.log(`    ❌ ${c.check_name} (${c.document_type}): ${c.detail}`);
      }
    }
    if (detail.rejection_cause) {
      console.log(`  Rejection cause: ${detail.rejection_cause}`);
    }

    // Audit trail
    if (detail.audit_trail?.length) {
      console.log(`  Audit trail:`);
      for (const a of detail.audit_trail) {
        console.log(`    - ${a.action}: ${a.reason?.substring(0, 120)}`);
      }
    }
  }
}

main().catch(e => { console.error(e); process.exit(1); });
