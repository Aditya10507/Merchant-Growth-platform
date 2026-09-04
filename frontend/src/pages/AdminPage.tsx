/**
 * AdminPage.tsx
 * -------------
 * The admin/reviewer panel for managing merchant verification cases.
 * Wrapped in Layout.tsx sidebar shell. Monochrome enterprise design.
 */

import { memo, useCallback, useEffect, useState } from "react";

import {
  getAdminMerchants,
  getMerchantDetail,
  verifyApplication,
  decideApplication,
  clearTestMerchants,
  getFaultState,
  setFault,
  resetFaults,
  runRiskEval,
  ApiError,
} from "../api";
import { useAuth } from "../AuthContext";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { Layout } from "../components/Layout";
import { RiskBadge } from "../components/RiskBadge";
import { RiskBreakdown } from "../components/RiskBreakdown";
import { StatusBadge } from "../components/StatusBadge";
import { VerificationTimeline } from "../components/VerificationTimeline";
import { STATUS_LABELS } from "../constants";
import type {
  AsyncState,
  CheckResult,
  DocumentStatus,
  FaultName,
  FaultState,
  MaintenanceResult,
  MerchantDetail,
  MerchantSummary,
  RiskEvalReport,
} from "../types";

const STATUS_TABS = [
  "All",
  "pending",
  "submitted",
  "verified_matching",
  "verified_mismatched",
  "active",
  "rejected",
] as const;
type StatusTab = (typeof STATUS_TABS)[number];

function tabToFilter(tab: StatusTab): string | undefined {
  return tab === "All" ? undefined : tab;
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function AdminPageBase() {
  const { session } = useAuth();
  const isAdmin = session?.role === "admin";
  const [activeTab, setActiveTab] = useState<StatusTab>("All");
  const [listState, setListState] = useState<AsyncState<MerchantSummary[]>>({ status: "idle" });
  const [selectedMerchantId, setSelectedMerchantId] = useState<number | null>(null);
  const [detailState, setDetailState] = useState<AsyncState<MerchantDetail>>({ status: "idle" });
  const [verifyState, setVerifyState] = useState<AsyncState<MerchantDetail>>({ status: "idle" });
  const [resolveNote, setResolveNote] = useState<string>("");
  const [resolveState, setResolveState] = useState<AsyncState<MerchantSummary>>({ status: "idle" });
  const [maintenanceState, setMaintenanceState] = useState<AsyncState<MaintenanceResult>>({ status: "idle" });
  // Feature 1: demo fault toggles (admin chaos panel)
  const [faultState, setFaultState] = useState<FaultState | null>(null);
  const [faultError, setFaultError] = useState<string | null>(null);
  // Feature 2: empirical risk calibration
  const [riskEvalState, setRiskEvalState] = useState<AsyncState<RiskEvalReport>>({ status: "idle" });

  const fetchMerchants = useCallback(async (tab: StatusTab) => {
    setListState({ status: "loading" });
    try {
      const data = await getAdminMerchants(tabToFilter(tab));
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

  const handleClearTestMerchants = useCallback(async () => {
    setMaintenanceState({ status: "loading" });
    try {
      const result = await clearTestMerchants();
      setMaintenanceState({ status: "success", data: result });
      // Archived merchants disappear from the review queue
      await fetchMerchants(activeTab);
    } catch (error) {
      setMaintenanceState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not archive test merchants.",
      });
    }
  }, [activeTab, fetchMerchants]);

  const closeDetail = useCallback(() => {
    setSelectedMerchantId(null);
    setDetailState({ status: "idle" });
    setResolveNote("");
    setResolveState({ status: "idle" });
    setVerifyState({ status: "idle" });
  }, []);

  // --- Feature 1: demo fault toggles (admin chaos panel) ---
  const refreshFaultState = useCallback(async () => {
    try {
      const state = await getFaultState();
      setFaultState(state);
      setFaultError(null);
    } catch (error) {
      setFaultError(error instanceof ApiError ? error.message : "Could not load fault state.");
    }
  }, []);

  useEffect(() => {
    if (isAdmin) refreshFaultState();
  }, [isAdmin, refreshFaultState]);

  const handleToggleFault = useCallback(
    async (fault: FaultName, enabled: boolean) => {
      setFaultError(null);
      try {
        const state = await setFault(fault, enabled);
        setFaultState(state);
      } catch (error) {
        setFaultError(error instanceof ApiError ? error.message : "Could not toggle fault.");
      }
    },
    []
  );

  const handleResetFaults = useCallback(async () => {
    setFaultError(null);
    try {
      const state = await resetFaults();
      setFaultState(state);
    } catch (error) {
      setFaultError(error instanceof ApiError ? error.message : "Could not reset faults.");
    }
  }, []);

  // --- Feature 2: run the empirical risk calibration ---
  const handleRunRiskEval = useCallback(async () => {
    setRiskEvalState({ status: "loading" });
    try {
      const report = await runRiskEval();
      setRiskEvalState({ status: "success", data: report });
    } catch (error) {
      setRiskEvalState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not run calibration.",
      });
    }
  }, []);

  return (
    <Layout>
      {/* Fixed dashboard column: header blocks are pinned (shrink-0); the
          review row below is the only thing that flexes, and its two panes
          (queue + detail) scroll internally instead of moving the page. */}
      <div className="flex h-full flex-col overflow-hidden">
        {/* Page header */}
        <div className="flex flex-shrink-0 items-baseline justify-between gap-4 px-6 pt-5 pb-3">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              Merchant Verification Panel
            </h1>
            <p className="mt-0.5 text-sm text-gray-500">
              Review submitted applications, run verification checks, and decide
              whether to activate or reject each account.
            </p>
          </div>
        </div>

        {/* ============================================================
            Admin-only engineering tools: failure-injection demo mode
            (Feature 1) and empirical risk calibration (Feature 2). These
            are the Failure Recovery + AI Judgment demo artifacts — a
            reviewer never sees them.
        ============================================================ */}
        {isAdmin && (
          <div className="grid flex-shrink-0 grid-cols-1 gap-4 px-6 pb-3 lg:grid-cols-2">
            {/* Chaos panel: simulate outages, watch graceful degradation */}
            <ChaosPanel
              faultState={faultState}
              faultError={faultError}
              onToggle={handleToggleFault}
              onReset={handleResetFaults}
            />

            {/* Risk calibration: measure the weights against labeled data */}
            <RiskEvalCard
              state={riskEvalState}
              onRun={handleRunRiskEval}
            />
          </div>
        )}

        {/* Status filter tabs + maintenance action */}
        <div className="flex flex-shrink-0 flex-wrap items-start justify-between gap-3 px-6 pb-4">
          <nav aria-label="Filter merchants by status" className="flex flex-wrap gap-2">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-150 ${
                  activeTab === tab
                    ? "bg-gray-900 text-white"
                    : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
                }`}
                aria-pressed={activeTab === tab}
              >
                {tab === "All" ? "All" : STATUS_LABELS[tab] ?? tab}
              </button>
            ))}
          </nav>

          {isAdmin && (
            <div className="flex flex-col items-end gap-1.5">
              <Button
                variant="secondary"
                onClick={handleClearTestMerchants}
                isLoading={maintenanceState.status === "loading"}
              >
                Archive test merchants
              </Button>
              <p className="text-right text-xs text-gray-400">
                Removes E2E/test-run accounts from this queue and the batch-test
                accuracy report. Their records are preserved, not deleted.
              </p>
              {maintenanceState.status === "success" && (
                <Alert variant="success">
                  Archived {maintenanceState.data.archived_count} test merchant
                  {maintenanceState.data.archived_count === 1 ? "" : "s"}. Batch test
                  now scores {maintenanceState.data.remaining_count} merchant
                  {maintenanceState.data.remaining_count === 1 ? "" : "s"}.
                </Alert>
              )}
              {maintenanceState.status === "error" && (
                <Alert variant="error">{maintenanceState.message}</Alert>
              )}
            </div>
          )}
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
                <p className="text-sm font-medium text-gray-900">No applicants {activeTab === "All" ? "yet" : `with status “${STATUS_LABELS[activeTab] ?? activeTab}”`}</p>
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
        // Feature 3: a prompt-injection payload is a security finding —
        // render it with the same prominence as a fraud-ring signal.
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
            verification to check consistency across databases.
          </p>
          <Button variant="primary" onClick={handleVerify} isLoading={verifyState.status === "loading"}>
            Verify with internal databases
          </Button>
          {verifyState.status === "error" && <Alert variant="error">{verifyState.message}</Alert>}
        </div>
      )}

      {/* STATE: verified_matching → Show matched checks + Approve button */}
      {isVerifiedMatching && detail.matched_checks && (
        <div className="rounded-md border border-gray-300 bg-gray-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-gray-900">All checks matched</h3>
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

      {/* STATE: verified_mismatched → Show mismatched checks + editable cause + Reject button */}
      {isVerifiedMismatched && (
        <div className="rounded-md border border-gray-900 bg-gray-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-gray-900">Mismatches found</h3>

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

// ---------------------------------------------------------------------------
// Feature 1: Chaos panel — simulate outages, watch graceful degradation
// ---------------------------------------------------------------------------

const FAULT_DESCRIPTIONS: Record<FaultName, { label: string; hint: string }> = {
  ocr_down: {
    label: "OCR engine down",
    hint: "Uploads surface the retry-friendly 'temporarily unavailable' status instead of extracting.",
  },
  llm_down: {
    label: "LLM verification down",
    hint: "Admin verify is DEFERRED (no determination on partial signals) until the fault clears.",
  },
  sources_down: {
    label: "External sources down",
    hint: "The 5 simulated data sources raise an outage; verify defers rather than scoring silence.",
  },
};

const FAULT_ORDER: FaultName[] = ["ocr_down", "llm_down", "sources_down"];

interface ChaosPanelProps {
  faultState: FaultState | null;
  faultError: string | null;
  onToggle: (fault: FaultName, enabled: boolean) => void;
  onReset: () => void;
}

function ChaosPanelBase({ faultState, faultError, onToggle, onReset }: ChaosPanelProps) {
  const anyActive = faultState !== null && faultState.active.length > 0;
  return (
    <section className="rounded-md border border-gray-200 bg-white p-4">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">Failure-injection demo</h2>
        <Button variant="secondary" onClick={onReset} disabled={!anyActive} className="px-2 py-1 text-xs">
          Clear all faults
        </Button>
      </div>
      <p className="mb-3 text-xs text-gray-500">
        Toggle a simulated outage and watch the system degrade gracefully —
        same recovery paths a real outage takes. Process-local; auto-resets
        on restart, so a demo can never get stuck.
      </p>

      {anyActive && (
        <div className="mb-3">
          <Alert variant="info">
            {faultState!.active.length} fault{faultState!.active.length === 1 ? " is" : "s are"} active:
            {" "}{faultState!.active.join(", ")}. Use “Clear all faults” to recover instantly.
          </Alert>
        </div>
      )}
      {faultError && <div className="mb-3"><Alert variant="error">{faultError}</Alert></div>}

      <div className="flex flex-col gap-2">
        {FAULT_ORDER.map((fault) => {
          const active = faultState ? faultState[fault] : false;
          const desc = FAULT_DESCRIPTIONS[fault];
          return (
            <div
              key={fault}
              className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                active ? "border-gray-900 bg-gray-100" : "border-gray-200 bg-gray-50"
              }`}
            >
              <button
                role="switch"
                aria-checked={active}
                aria-label={`${desc.label} demo fault`}
                onClick={() => onToggle(fault, !active)}
                className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors duration-150 ${
                  active ? "bg-gray-900" : "bg-gray-300"
                }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform duration-150 ${
                    active ? "translate-x-[18px]" : "translate-x-0.5"
                  }`}
                />
              </button>
              <div className="min-w-0">
                <p className={`text-xs font-medium ${active ? "text-gray-900" : "text-gray-700"}`}>
                  {desc.label}
                </p>
                <p className="text-xs text-gray-500">{desc.hint}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const ChaosPanel = memo(ChaosPanelBase);

// ---------------------------------------------------------------------------
// Feature 2: Risk calibration — measure the weights against labeled data
// ---------------------------------------------------------------------------

interface RiskEvalCardProps {
  state: AsyncState<RiskEvalReport>;
  onRun: () => void;
}

function RiskEvalCardBase({ state, onRun }: RiskEvalCardProps) {
  return (
    <section className="rounded-md border border-gray-200 bg-white p-4">
      <h2 className="text-sm font-semibold text-gray-900">Risk-weight calibration</h2>
      <p className="mb-3 text-xs text-gray-500">
        Scores every labeled merchant under the CURRENT weights and measures
        how well risk separates clean from flagged cases — the “how do you
        know your model is good?” answer.
      </p>

      {state.status === "idle" && (
        <Button variant="secondary" onClick={onRun}>
          Run calibration
        </Button>
      )}
      {state.status === "loading" && (
        <p className="text-sm text-gray-500" role="status">Scoring labeled merchants…</p>
      )}
      {state.status === "error" && (
        <>
          <Alert variant="error">{state.message}</Alert>
          <div className="mt-2">
            <Button variant="secondary" onClick={onRun}>Retry</Button>
          </div>
        </>
      )}
      {state.status === "success" && <CalibrationReport report={state.data} onRerun={onRun} />}
    </section>
  );
}

const RiskEvalCard = memo(RiskEvalCardBase);

function CalibrationReport({ report, onRerun }: { report: RiskEvalReport; onRerun: () => void }) {
  if (report.total_labeled === 0) {
    return (
      <div className="flex flex-col gap-2">
        <Alert variant="info">
          No labeled merchants found. Run <code>python seed.py</code> to create the 25
          ground-truth merchants this report evaluates.
        </Alert>
        <Button variant="secondary" onClick={onRerun}>Run again</Button>
      </div>
    );
  }

  const conf = report.best_confusion;
  return (
    <div className="flex flex-col gap-2 text-xs">
      <div className="rounded-md border border-gray-200 bg-gray-50 p-2">
        <p className="text-gray-700">
          <span className="font-semibold text-gray-900">{report.total_labeled}</span> labeled merchants
          ({report.good_count} clean, {report.bad_count} flagged)
          {report.replayed_count > 0 && <> — {report.replayed_count} scored by replaying the check engine</>}
          {report.pipeline_scored_count > 0 && <> — {report.pipeline_scored_count} from real pipeline runs</>}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-md border border-gray-200 p-2">
          <p className="text-gray-500">Clean — mean risk</p>
          <p className="text-base font-semibold text-gray-900">{report.good_stats.mean_score.toFixed(1)}</p>
          <p className="text-gray-400">min {report.good_stats.min_score} · max {report.good_stats.max_score}</p>
        </div>
        <div className="rounded-md border border-gray-900 bg-gray-50 p-2">
          <p className="text-gray-600">Flagged — mean risk</p>
          <p className="text-base font-semibold text-gray-900">{report.bad_stats.mean_score.toFixed(1)}</p>
          <p className="text-gray-500">min {report.bad_stats.min_score} · max {report.bad_stats.max_score}</p>
        </div>
      </div>

      <div className="rounded-md border border-gray-200 p-2">
        <p className="text-gray-500">Best-F1 decision threshold: <span className="font-semibold text-gray-900">≥ {report.best_threshold}</span> (F1 = {report.best_f1.toFixed(3)})</p>
        <p className="mt-1 text-gray-500">
          TP {conf.true_positives ?? 0} · FP {conf.false_positives ?? 0} ·
          FN {conf.false_negatives ?? 0} · TN {conf.true_negatives ?? 0}
        </p>
      </div>

      <details className="rounded-md border border-gray-200 p-2">
        <summary className="cursor-pointer text-gray-700">Cutoff sweep (precision / recall / F1)</summary>
        <table className="mt-2 w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="py-1 pr-2 font-medium">Cutoff</th>
              <th className="py-1 pr-2 font-medium">Precision</th>
              <th className="py-1 pr-2 font-medium">Recall</th>
              <th className="py-1 font-medium">F1</th>
            </tr>
          </thead>
          <tbody>
            {report.threshold_sweep.map((row) => (
              <tr key={row.threshold} className="border-b border-gray-100">
                <td className="py-1 pr-2">
                  <span className={row.threshold === report.best_threshold ? "font-semibold text-gray-900" : "text-gray-700"}>
                    ≥ {row.threshold}
                    {row.threshold === report.best_threshold && " ★"}
                  </span>
                </td>
                <td className="py-1 pr-2 text-gray-600">{row.precision.toFixed(2)}</td>
                <td className="py-1 pr-2 text-gray-600">{row.recall.toFixed(2)}</td>
                <td className="py-1 text-gray-600">{row.f1.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <div>
        <Button variant="secondary" onClick={onRerun}>Run again</Button>
      </div>
    </div>
  );
}

export const AdminPage = memo(AdminPageBase);
