/**
 * AdminPage.tsx
 * -------------
 * The admin/reviewer panel for managing merchant verification cases.
 * Wrapped in Layout.tsx sidebar shell. Monochrome enterprise design.
 *
 * Layout (Session 24/26): fixed-viewport dashboard — the page never
 * scrolls; the applicants table and the merchant-detail pane each scroll
 * internally. The panel is intentionally SIMPLE (Session 26): three tabs
 * (Applicants / Active merchants / Rejected) and the stationary detail
 * pane where the admin verifies documents, sees the fraud-ring analysis
 * and verification details, then accepts or rejects — the decision
 * message flows back to the merchant's dashboard.
 */

import { memo, useCallback, useEffect, useState } from "react";

import {
  getAdminMerchants,
  getMerchantDetail,
  verifyApplication,
  decideApplication,
  ApiError,
} from "../api";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { Layout } from "../components/Layout";
import { RiskBadge } from "../components/RiskBadge";
import { RiskBreakdown } from "../components/RiskBreakdown";
import { StatusBadge } from "../components/StatusBadge";
import { VerificationTimeline } from "../components/VerificationTimeline";
import type {
  AsyncState,
  CheckResult,
  DocumentStatus,
  MerchantDetail,
  MerchantSummary,
} from "../types";

// ---------------------------------------------------------------------------
// Tabs — the simple three-way split of the review queue
// ---------------------------------------------------------------------------

const TABS = [
  {
    id: "applicants",
    label: "Applicants",
    filter: "pending,submitted,verified_matching,verified_mismatched",
    empty: "No pending applications",
  },
  {
    id: "active",
    label: "Active merchants",
    filter: "active",
    empty: "No approved merchants yet",
  },
  {
    id: "rejected",
    label: "Rejected",
    filter: "rejected",
    empty: "No rejected applications",
  },
] as const;

type TabId = (typeof TABS)[number]["id"];

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function AdminPageBase() {
  const [activeTab, setActiveTab] = useState<TabId>("applicants");
  const [listState, setListState] = useState<AsyncState<MerchantSummary[]>>({ status: "idle" });
  const [selectedMerchantId, setSelectedMerchantId] = useState<number | null>(null);
  const [detailState, setDetailState] = useState<AsyncState<MerchantDetail>>({ status: "idle" });
  const [verifyState, setVerifyState] = useState<AsyncState<MerchantDetail>>({ status: "idle" });
  const [resolveNote, setResolveNote] = useState<string>("");
  const [resolveState, setResolveState] = useState<AsyncState<MerchantSummary>>({ status: "idle" });

  const activeTabDef = TABS.find((t) => t.id === activeTab) ?? TABS[0];

  const fetchMerchants = useCallback(async (tab: TabId) => {
    const def = TABS.find((t) => t.id === tab) ?? TABS[0];
    setListState({ status: "loading" });
    try {
      const data = await getAdminMerchants(def.filter);
      setListState({ status: "success", data });
    } catch (error) {
      setListState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not load merchants.",
      });
    }
  }, []);

  useEffect(() => {
    fetchMerchants(activeTab);
  }, [activeTab, fetchMerchants]);

  const selectMerchant = useCallback(async (merchantId: number) => {
    setSelectedMerchantId(merchantId);
    setDetailState({ status: "loading" });
    setResolveNote("");
    setResolveState({ status: "idle" });
    setVerifyState({ status: "idle" });
    try {
      const data = await getMerchantDetail(merchantId);
      setDetailState({ status: "success", data });
    } catch (error) {
      setDetailState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not load merchant detail.",
      });
    }
  }, []);

  const handleVerify = useCallback(async () => {
    if (selectedMerchantId === null) return;
    setVerifyState({ status: "loading" });
    try {
      const result = await verifyApplication(selectedMerchantId);
      setVerifyState({ status: "success", data: result });
      await selectMerchant(selectedMerchantId);
      await fetchMerchants(activeTab);
    } catch (error) {
      setVerifyState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Verification failed. Please try again.",
      });
    }
  }, [selectedMerchantId, activeTab, selectMerchant, fetchMerchants]);

  const handleDecide = useCallback(
    async (decision: "approved" | "rejected") => {
      if (selectedMerchantId === null) return;
      setResolveState({ status: "loading" });
      try {
        const result = await decideApplication(selectedMerchantId, decision, resolveNote || undefined);
        setResolveState({ status: "success", data: result });
        await selectMerchant(selectedMerchantId);
        await fetchMerchants(activeTab);
        setResolveNote("");
      } catch (error) {
        setResolveState({
          status: "error",
          message: error instanceof ApiError ? error.message : "Could not submit decision.",
        });
      }
    },
    [selectedMerchantId, resolveNote, activeTab, selectMerchant, fetchMerchants]
  );

  const closeDetail = useCallback(() => {
    setSelectedMerchantId(null);
    setDetailState({ status: "idle" });
    setResolveNote("");
    setResolveState({ status: "idle" });
    setVerifyState({ status: "idle" });
  }, []);

  return (
    <Layout>
      <div className="flex h-full flex-col overflow-hidden">
        {/* Page header — pinned */}
        <div className="flex flex-shrink-0 items-baseline justify-between gap-4 px-6 pt-5 pb-3">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              Merchant Verification Panel
            </h1>
            <p className="mt-0.5 text-sm text-gray-500">
              Review applications, verify documents, and accept or reject each
              merchant. Decisions are sent straight to the applicant's dashboard.
            </p>
          </div>
        </div>

        {/* Tabs — pinned */}
        <div className="flex flex-shrink-0 items-center gap-2 px-6 pb-4">
          <nav aria-label="Filter merchants" className="flex gap-2">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-150 ${
                  activeTab === tab.id
                    ? "bg-gray-900 text-white"
                    : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
                }`}
                aria-pressed={activeTab === tab.id}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Review row: queue scrolls internally, detail panel is a fixed
            stationary pane that never scrolls away with the page. */}
        <div className="flex min-h-0 flex-1 gap-6 px-6 pb-6">
          {/* Merchant list — data table, its own vertical scroll region */}
          <section className="flex min-h-0 min-w-0 flex-1 flex-col rounded-md border border-gray-200 bg-white" aria-label="Merchant list">
            {listState.status === "loading" && (
              <p className="p-4 text-sm text-gray-500" role="status">Loading merchants…</p>
            )}
            {listState.status === "error" && (
              <div className="p-4"><Alert variant="error">{listState.message}</Alert></div>
            )}

            {listState.status === "success" && listState.data.length === 0 && (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
                <p className="text-sm font-medium text-gray-900">{activeTabDef.empty}</p>
                <p className="text-xs text-gray-500">
                  New merchant sign-ups appear here as they submit their documents.
                </p>
              </div>
            )}

            {listState.status === "success" && listState.data.length > 0 && (
              <div className="min-h-0 flex-1 overflow-y-auto">
                <table className="w-full border-collapse text-sm">
                  <thead className="sticky top-0 z-10 bg-white">
                    <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      <th className="py-2.5 pl-4 pr-4">Business</th>
                      <th className="py-2.5 pr-4">Status</th>
                      <th className="py-2.5 pr-4">Risk</th>
                      <th className="py-2.5 pr-4">Submitted</th>
                      <th className="py-2.5 pr-4"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {listState.data.map((merchant) => (
                      <tr
                        key={merchant.merchant_id}
                        className={`cursor-pointer border-b border-gray-100 hover:bg-gray-50 ${
                          selectedMerchantId === merchant.merchant_id ? "bg-gray-100" : ""
                        }`}
                        onClick={() => selectMerchant(merchant.merchant_id)}
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            selectMerchant(merchant.merchant_id);
                          }
                        }}
                      >
                        <td className="py-3 pl-4 pr-4 font-medium text-gray-900">{merchant.business_name}</td>
                        <td className="py-3 pr-4">
                          <StatusBadge status={merchant.onboarding_status as DocumentStatus["verification_status"]} />
                        </td>
                        <td className="py-3 pr-4">
                          <RiskBadge score={merchant.risk_score} />
                        </td>
                        <td className="py-3 pr-4 text-gray-500">{formatDate(merchant.created_at)}</td>
                        <td className="py-3 pr-4 text-right">
                          <Button variant="secondary" onClick={(e) => { e.stopPropagation(); selectMerchant(merchant.merchant_id); }}>
                            View
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Detail panel — stationary pane; only its content scrolls */}
          {selectedMerchantId !== null && (
            <section
              className="flex w-96 flex-shrink-0 flex-col overflow-hidden rounded-md border border-gray-200 bg-white"
              aria-label="Merchant detail"
            >
              {detailState.status === "loading" && (
                <p className="p-4 text-sm text-gray-500" role="status">Loading merchant detail…</p>
              )}
              {detailState.status === "error" && (
                <div className="p-4"><Alert variant="error">{detailState.message}</Alert></div>
              )}

              {detailState.status === "success" && (
                <div className="min-h-0 flex-1 overflow-y-auto p-5">
                  <MerchantDetailView
                    detail={detailState.data}
                    verifyState={verifyState}
                    handleVerify={handleVerify}
                    resolveNote={resolveNote}
                    setResolveNote={setResolveNote}
                    handleDecide={handleDecide}
                    resolveState={resolveState}
                    closeDetail={closeDetail}
                  />
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </Layout>
  );
}

// ---------------------------------------------------------------------------
// Check result list — renders matched or mismatched checks
// ---------------------------------------------------------------------------

interface CheckResultListProps {
  checks: CheckResult[];
  variant: "matched" | "mismatched";
}

function CheckResultListBase({ checks, variant }: CheckResultListProps) {
  if (checks.length === 0) {
    return (
      <p className="text-xs text-gray-500 italic">
        {variant === "matched" ? "No matched checks." : "No mismatched checks."}
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {checks.map((check, idx) => {
        const isFraudRing = check.check_name.startsWith("fraud_ring_");
        // A prompt-injection payload is a security finding — render it
        // with the same prominence as a fraud-ring signal.
        const isInjection = check.check_name === "prompt_injection_suspected";
        const highlighted = isFraudRing || isInjection;
        return (
          <li
            key={`${check.check_name}-${idx}`}
            className={`rounded-md border px-3 py-2 text-xs ${
              variant === "matched"
                ? "border-gray-200 bg-gray-50"
                : highlighted
                  ? "border-2 border-gray-900 bg-gray-100"
                  : "border-gray-200 bg-gray-50"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={`font-medium ${variant === "matched" ? "text-gray-700" : "text-gray-900"}`}>
                {isInjection
                  ? "⚠ Security — suspected prompt injection"
                  : `${check.document_type} — ${check.check_name.replace(/_/g, " ")}`}
              </span>
              <span className={variant === "matched" ? "text-gray-500" : "text-gray-900"}>
                {variant === "matched" ? "✓" : "✗"}
              </span>
            </div>
            <p className={`mt-0.5 ${variant === "matched" ? "text-gray-600" : "text-gray-700"}`}>
              {check.detail}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

const CheckResultList = memo(CheckResultListBase);

// ---------------------------------------------------------------------------
// Fraud-ring analysis — shared identifiers across applicants
// ---------------------------------------------------------------------------

function FraudRingAnalysis({ detail }: { detail: MerchantDetail }) {
  const all = [
    ...(detail.matched_checks ?? []),
    ...(detail.mismatched_checks ?? []),
  ].filter((c) => c.check_name.startsWith("fraud_ring_"));

  if (all.length === 0) {
    return (
      <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-xs">
        <p className="font-medium text-gray-900">Fraud-ring analysis</p>
        <p className="mt-1 text-gray-500">
          No cross-applicant shared-identifier check has run yet. Run
          verification to scan for shared PAN / bank accounts across applicants.
        </p>
      </div>
    );
  }

  const flagged = all.filter((c) => !c.matched);
  return (
    <div className={`rounded-md border p-3 text-xs ${flagged.length > 0 ? "border-2 border-gray-900 bg-gray-100" : "border-gray-200 bg-gray-50"}`}>
      <p className="font-medium text-gray-900">
        Fraud-ring analysis{" "}
        <span className={`ml-1 rounded px-1.5 py-0.5 text-xs font-semibold ${flagged.length > 0 ? "bg-gray-900 text-white" : "bg-gray-200 text-gray-700"}`}>
          {flagged.length > 0 ? `${flagged.length} signal${flagged.length === 1 ? "" : "s"} found` : "no shared identifiers"}
        </span>
      </p>
      <ul className="mt-2 flex flex-col gap-1.5">
        {all.map((check, idx) => (
          <li key={`${check.check_name}-${idx}`} className="flex items-start justify-between gap-2">
            <span className={check.matched ? "text-gray-600" : "font-semibold text-gray-900"}>
              {check.matched ? "✓" : "✗"} {check.detail}
            </span>
          </li>
        ))}
      </ul>
      {flagged.length > 0 && (
        <p className="mt-2 text-gray-700">
          This applicant shares identifiers with other applications — treat as
          higher-risk and review carefully before approving.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Merchant detail panel — three-state view
// ---------------------------------------------------------------------------

interface MerchantDetailViewProps {
  detail: MerchantDetail;
  verifyState: AsyncState<MerchantDetail>;
  handleVerify: () => void;
  resolveNote: string;
  setResolveNote: (note: string) => void;
  handleDecide: (decision: "approved" | "rejected") => void;
  resolveState: AsyncState<MerchantSummary>;
  closeDetail: () => void;
}

function MerchantDetailViewBase({
  detail,
  verifyState,
  handleVerify,
  resolveNote,
  setResolveNote,
  handleDecide,
  resolveState,
  closeDetail,
}: MerchantDetailViewProps) {
  const isSubmitted = detail.onboarding_status === "submitted";
  const isVerifiedMatching = detail.onboarding_status === "verified_matching";
  const isVerifiedMismatched = detail.onboarding_status === "verified_mismatched";

  return (
    <div className="flex flex-col gap-4">
      {/* Close button */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">Merchant Detail</h2>
        <button onClick={closeDetail} className="text-gray-400 hover:text-gray-600 text-sm" aria-label="Close detail panel">
          ✕
        </button>
      </div>

      {/* Basic info */}
      <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm">
        <p className="font-medium text-gray-900">{detail.business_name}</p>
        <p className="text-gray-600">{detail.email}</p>
        <div className="mt-2 flex items-center gap-2">
          <StatusBadge status={detail.onboarding_status as DocumentStatus["verification_status"]} />
          <RiskBadge score={detail.risk_score} />
        </div>
        {detail.rejection_reason && (
          <p className="mt-2 text-xs text-gray-700">{detail.rejection_reason}</p>
        )}
      </div>

      {/* Documents section */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Documents</h3>
        {detail.documents.length === 0 ? (
          <p className="text-xs text-gray-500">No active documents.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {detail.documents.map((doc) => (
              <div key={doc.id} className="rounded-md border border-gray-200 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-700">{doc.doc_type}</span>
                  <StatusBadge status={doc.verification_status} />
                </div>
                {doc.ocr_confidence !== null && (
                  <p className="mt-1 text-xs text-gray-500">
                    OCR confidence: {(doc.ocr_confidence * 100).toFixed(1)}%
                  </p>
                )}
                {doc.extracted_fields && (
                  <div className="mt-2 space-y-0.5">
                    {Object.entries(doc.extracted_fields).map(([key, value]) => (
                      <p key={key} className="text-xs text-gray-600">
                        <span className="font-medium">{key}:</span> {value}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* STATE: submitted → Show "Verify" button */}
      {isSubmitted && (
        <div className="rounded-md border border-gray-300 bg-gray-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-gray-900">Ready for verification</h3>
          <p className="mb-3 text-xs text-gray-600">
            All 3 documents have passed format checks. Run the internal
            verification to check consistency across databases, external
            sources, and other applicants (fraud ring).
          </p>
          <Button variant="primary" onClick={handleVerify} isLoading={verifyState.status === "loading"}>
            Verify with internal databases
          </Button>
          {verifyState.status === "error" && <Alert variant="error">{verifyState.message}</Alert>}
        </div>
      )}

      {/* STATE: verified_matching → fraud ring + matched checks + Approve */}
      {isVerifiedMatching && detail.matched_checks && (
        <div className="rounded-md border border-gray-300 bg-gray-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-gray-900">All checks matched</h3>
          <div className="mb-3">
            <FraudRingAnalysis detail={detail} />
          </div>
          <p className="mb-3 text-xs text-gray-600">
            The following verification checks all passed successfully:
          </p>
          <CheckResultList checks={detail.matched_checks} variant="matched" />
          <div className="mt-4">
            <Button variant="primary" onClick={() => handleDecide("approved")} isLoading={resolveState.status === "loading"}>
              Approve &amp; activate account
            </Button>
          </div>
          {resolveState.status === "error" && <Alert variant="error">{resolveState.message}</Alert>}
          {resolveState.status === "success" && <Alert variant="success">Decision recorded successfully.</Alert>}
        </div>
      )}

      {/* STATE: verified_mismatched → fraud ring + mismatches + risk score + Reject */}
      {isVerifiedMismatched && (
        <div className="rounded-md border border-gray-900 bg-gray-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-gray-900">Mismatches found</h3>

          <div className="mb-3">
            <FraudRingAnalysis detail={detail} />
          </div>

          {detail.matched_checks && detail.matched_checks.length > 0 && (
            <div className="mb-3">
              <p className="mb-1 text-xs font-semibold text-gray-700">Passed checks:</p>
              <CheckResultList checks={detail.matched_checks} variant="matched" />
            </div>
          )}

          {detail.mismatched_checks && (
            <div className="mb-3">
              <p className="mb-1 text-xs font-semibold text-gray-900">Failed checks:</p>
              <CheckResultList checks={detail.mismatched_checks} variant="mismatched" />
            </div>
          )}

          {detail.mismatched_checks && detail.mismatched_checks.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-gray-700">Risk Score Breakdown:</p>
              <RiskBreakdown mismatchedChecks={detail.mismatched_checks} />
            </div>
          )}

          <div className="mt-3">
            <InputField
              label="Rejection message (shown to merchant)"
              value={resolveNote}
              onChange={(e) => setResolveNote(e.target.value)}
              placeholder={detail.rejection_cause || "Enter a rejection reason…"}
            />
            <p className="mt-1 text-xs text-gray-600">
              Pre-filled from verification results. Edit if needed, or leave as-is to
              send the auto-generated message.
            </p>
          </div>

          <div className="mt-3">
            <Button variant="secondary" onClick={() => handleDecide("rejected")} isLoading={resolveState.status === "loading"}>
              Reject &amp; notify merchant
            </Button>
          </div>
          {resolveState.status === "error" && <Alert variant="error">{resolveState.message}</Alert>}
          {resolveState.status === "success" && <Alert variant="success">Decision recorded successfully.</Alert>}
        </div>
      )}

      {/* Audit trail */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Audit Trail</h3>
        <VerificationTimeline entries={detail.audit_trail} compact={false} />
      </div>
    </div>
  );
}

const MerchantDetailView = memo(MerchantDetailViewBase);

export const AdminPage = memo(AdminPageBase);