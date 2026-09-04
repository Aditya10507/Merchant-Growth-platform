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
  MaintenanceResult,
  MerchantDetail,
  MerchantSummary,
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

  return (
    <Layout>
      <h1 className="mb-2 text-xl font-semibold text-gray-900">
        Merchant Verification Panel
      </h1>
      <p className="mb-6 text-sm text-gray-500">
        Review submitted applications, run verification checks, and decide
        whether to activate or reject each account.
      </p>

      {/* Status filter tabs + maintenance action */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <nav aria-label="Filter merchants by status" className="flex gap-2 flex-wrap">
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

      <div className="flex gap-6">
        {/* Merchant list — data table */}
        <section className="flex-1" aria-label="Merchant list">
          {listState.status === "loading" && (
            <p className="text-sm text-gray-500" role="status">Loading merchants…</p>
          )}
          {listState.status === "error" && <Alert variant="error">{listState.message}</Alert>}

          {listState.status === "success" && listState.data.length === 0 && (
            <p className="text-sm text-gray-500">No merchants found for this filter.</p>
          )}

          {listState.status === "success" && listState.data.length > 0 && (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  <th className="py-2 pr-4">Business</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Risk</th>
                  <th className="py-2 pr-4">Submitted</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {listState.data.map((merchant) => (
                  <tr
                    key={merchant.merchant_id}
                    className={`border-b border-gray-100 hover:bg-gray-50 cursor-pointer ${
                      selectedMerchantId === merchant.merchant_id ? "bg-gray-50" : ""
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
                    <td className="py-3 pr-4 font-medium text-gray-900">{merchant.business_name}</td>
                    <td className="py-3 pr-4">
                      <StatusBadge status={merchant.onboarding_status as DocumentStatus["verification_status"]} />
                    </td>
                    <td className="py-3 pr-4">
                      <RiskBadge score={merchant.risk_score} />
                    </td>
                    <td className="py-3 pr-4 text-gray-500">{formatDate(merchant.created_at)}</td>
                    <td className="py-3">
                      <Button variant="secondary" onClick={(e) => { e.stopPropagation(); selectMerchant(merchant.merchant_id); }}>
                        View
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Detail panel */}
        {selectedMerchantId !== null && (
          <section
            className="w-96 flex-shrink-0 rounded-md border border-gray-200 bg-white p-5"
            aria-label="Merchant detail"
          >
            {detailState.status === "loading" && (
              <p className="text-sm text-gray-500" role="status">Loading merchant detail…</p>
            )}
            {detailState.status === "error" && <Alert variant="error">{detailState.message}</Alert>}

            {detailState.status === "success" && (
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
            )}
          </section>
        )}
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
        return (
          <li
            key={`${check.check_name}-${idx}`}
            className={`rounded-md border px-3 py-2 text-xs ${
              variant === "matched"
                ? "border-gray-200 bg-gray-50"
                : isFraudRing
                  ? "border-2 border-gray-900 bg-gray-100"
                  : "border-gray-200 bg-gray-50"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={`font-medium ${variant === "matched" ? "text-gray-700" : "text-gray-900"}`}>
                {check.document_type} — {check.check_name.replace(/_/g, " ")}
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

export const AdminPage = memo(AdminPageBase);
