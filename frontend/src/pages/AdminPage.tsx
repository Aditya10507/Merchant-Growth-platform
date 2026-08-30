/**
 * AdminPage.tsx
 * -------------
 * The admin/reviewer panel for managing merchant verification cases.
 *
 * Phase 3: Three-state detail view:
 *   - "submitted"        → shows a "Verify with internal databases" button
 *   - "verified_matching" → shows matched checks list + "Approve" button (no note needed)
 *   - "verified_mismatched" → shows mismatched checks + editable rejection_cause + "Reject" button
 *
 * All fetch states follow the AsyncState<T> pattern for consistent
 * loading/success/error handling.
 */

import { memo, useCallback, useEffect, useState } from "react";

import {
  getAdminMerchants,
  getMerchantDetail,
  verifyApplication,
  decideApplication,
  ApiError,
} from "../api";
import { useAuth } from "../AuthContext";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { RiskBadge } from "../components/RiskBadge";
import { RiskBreakdown } from "../components/RiskBreakdown";
import { StatusBadge } from "../components/StatusBadge";
import { VerificationTimeline } from "../components/VerificationTimeline";
import { STATUS_LABELS } from "../constants";
import type {
  AsyncState,
  CheckResult,
  DocumentStatus,
  MerchantDetail,
  MerchantSummary,
} from "../types";

/** Status filter tabs shown at the top of the merchant list. */
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

/** Maps tab labels to the query parameter value (empty string for "All"). */
function tabToFilter(tab: StatusTab): string | undefined {
  return tab === "All" ? undefined : tab;
}

/** Format an ISO string for display. */
function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function AdminPageBase() {
  const { session, logout } = useAuth();

  // Merchant list state
  const [activeTab, setActiveTab] = useState<StatusTab>("All");
  const [listState, setListState] = useState<AsyncState<MerchantSummary[]>>({
    status: "idle",
  });

  // Merchant detail state
  const [selectedMerchantId, setSelectedMerchantId] = useState<number | null>(
    null
  );
  const [detailState, setDetailState] = useState<AsyncState<MerchantDetail>>({
    status: "idle",
  });

  // Verify action state
  const [verifyState, setVerifyState] = useState<
    AsyncState<MerchantDetail>
  >({ status: "idle" });

  // Decide action state
  const [resolveNote, setResolveNote] = useState<string>("");
  const [resolveState, setResolveState] = useState<
    AsyncState<MerchantSummary>
  >({ status: "idle" });

  /** Fetches the merchant list, filtered by the currently active tab. */
  const fetchMerchants = useCallback(async (tab: StatusTab) => {
    setListState({ status: "loading" });
    try {
      const data = await getAdminMerchants(tabToFilter(tab));
      setListState({ status: "success", data });
    } catch (error) {
      setListState({
        status: "error",
        message:
          error instanceof ApiError ? error.message : "Could not load merchants.",
      });
    }
  }, []);

  // Fetch merchants when tab changes
  useEffect(() => {
    fetchMerchants(activeTab);
  }, [activeTab, fetchMerchants]);

  /** Fetches full detail for a selected merchant. */
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
        message:
          error instanceof ApiError
            ? error.message
            : "Could not load merchant detail.",
      });
    }
  }, []);

  /** Triggers the admin-triggered verification run. */
  const handleVerify = useCallback(async () => {
    if (selectedMerchantId === null) return;
    setVerifyState({ status: "loading" });
    try {
      const result = await verifyApplication(selectedMerchantId);
      setVerifyState({ status: "success", data: result });
      // Refresh both detail and list
      await selectMerchant(selectedMerchantId);
      await fetchMerchants(activeTab);
    } catch (error) {
      setVerifyState({
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "Verification failed. Please try again.",
      });
    }
  }, [selectedMerchantId, activeTab, selectMerchant, fetchMerchants]);

  /** Submits the admin's decision (approve or reject). */
  const handleDecide = useCallback(
    async (decision: "approved" | "rejected") => {
      if (selectedMerchantId === null) return;
      setResolveState({ status: "loading" });
      try {
        const result = await decideApplication(
          selectedMerchantId,
          decision,
          resolveNote || undefined
        );
        setResolveState({ status: "success", data: result });
        // Refresh both the detail view and the list
        await selectMerchant(selectedMerchantId);
        await fetchMerchants(activeTab);
        setResolveNote("");
      } catch (error) {
        setResolveState({
          status: "error",
          message:
            error instanceof ApiError
              ? error.message
              : "Could not submit decision.",
        });
      }
    },
    [selectedMerchantId, resolveNote, activeTab, selectMerchant, fetchMerchants]
  );

  /** Closes the detail panel and resets selection. */
  const closeDetail = useCallback(() => {
    setSelectedMerchantId(null);
    setDetailState({ status: "idle" });
    setResolveNote("");
    setResolveState({ status: "idle" });
    setVerifyState({ status: "idle" });
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-900">
            {session?.business_name}
          </span>
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700">
            {session?.role === "admin" ? "Admin" : "Reviewer"}
          </span>
        </div>
        <Button variant="secondary" onClick={logout}>
          Log out
        </Button>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <h1 className="mb-2 text-xl font-medium text-gray-900">
          Merchant Verification Panel
        </h1>
        <p className="mb-6 text-sm text-gray-500">
          Review submitted applications, run verification checks, and decide
          whether to activate or reject each account.
        </p>

        {/* Status filter tabs */}
        <nav aria-label="Filter merchants by status" className="mb-6 flex gap-2 flex-wrap">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "bg-brand-600 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              }`}
              aria-pressed={activeTab === tab}
            >
              {tab === "All" ? "All" : STATUS_LABELS[tab] ?? tab}
            </button>
          ))}
        </nav>

        <div className="flex gap-6">
          {/* Merchant list */}
          <section className="flex-1" aria-label="Merchant list">
            {listState.status === "loading" && (
              <p className="text-sm text-gray-500" role="status">
                Loading merchants…
              </p>
            )}
            {listState.status === "error" && (
              <Alert variant="error">{listState.message}</Alert>
            )}

            {listState.status === "success" && listState.data.length === 0 && (
              <p className="text-sm text-gray-500">
                No merchants found for this filter.
              </p>
            )}

            {listState.status === "success" && listState.data.length > 0 && (
              <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                <table className="w-full text-left text-sm" role="grid">
                  <thead className="bg-gray-50 text-xs text-gray-500">                        <tr>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Business Name
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Email
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Status
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Risk
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Created
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {listState.data.map((merchant) => (
                      <tr
                        key={merchant.merchant_id}
                        onClick={() => selectMerchant(merchant.merchant_id)}
                        className={`cursor-pointer transition-colors hover:bg-brand-50 ${
                          selectedMerchantId === merchant.merchant_id
                            ? "bg-brand-50"
                            : ""
                        }`}
                        role="row"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            selectMerchant(merchant.merchant_id);
                          }
                        }}
                        aria-selected={
                          selectedMerchantId === merchant.merchant_id
                        }
                      >
                        <td className="px-4 py-3 font-medium text-gray-900">
                          {merchant.business_name}
                        </td>
                        <td className="px-4 py-3 text-gray-600">
                          {merchant.email}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge
                            status={
                              merchant.onboarding_status as DocumentStatus["verification_status"]
                            }
                          />
                        </td>
                        <td className="px-4 py-3">
                          <RiskBadge score={merchant.risk_score} />
                        </td>
                        <td className="px-4 py-3 text-gray-500">
                          {formatDate(merchant.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Detail panel */}
          {selectedMerchantId !== null && (
            <section
              className="w-96 flex-shrink-0 rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
              aria-label="Merchant detail"
            >
              {detailState.status === "loading" && (
                <p className="text-sm text-gray-500" role="status">
                  Loading merchant detail…
                </p>
              )}
              {detailState.status === "error" && (
                <Alert variant="error">{detailState.message}</Alert>
              )}

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
      </main>
    </div>
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
      {checks.map((check, idx) => (
        <li
          key={`${check.check_name}-${idx}`}
          className={`rounded-md border px-3 py-2 text-xs ${
            variant === "matched"
              ? "border-green-200 bg-green-50"
              : "border-red-200 bg-red-50"
          }`}
        >
          <div className="flex items-center justify-between">
            <span
              className={`font-medium ${
                variant === "matched" ? "text-green-800" : "text-red-800"
              }`}
            >
              {check.document_type} — {check.check_name.replace(/_/g, " ")}
            </span>
            <span
              className={
                variant === "matched" ? "text-green-600" : "text-red-600"
              }
            >
              {variant === "matched" ? "✓" : "✗"}
            </span>
          </div>
          <p
            className={`mt-0.5 ${
              variant === "matched" ? "text-green-700" : "text-red-700"
            }`}
          >
            {check.detail}
          </p>
        </li>
      ))}
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
  const isVerifiedMismatched =
    detail.onboarding_status === "verified_mismatched";

  return (
    <div className="flex flex-col gap-4">
      {/* Close button */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">
          Merchant Detail
        </h2>
        <button
          onClick={closeDetail}
          className="text-gray-400 hover:text-gray-600 text-sm"
          aria-label="Close detail panel"
        >
          ✕
        </button>
      </div>

      {/* Basic info */}
      <div className="rounded-md bg-gray-50 p-3 text-sm">
        <p className="font-medium text-gray-900">{detail.business_name}</p>
        <p className="text-gray-600">{detail.email}</p>
        <div className="mt-2 flex items-center gap-2">
          <StatusBadge
            status={
              detail.onboarding_status as DocumentStatus["verification_status"]
            }
          />
          <RiskBadge score={detail.risk_score} />
        </div>
        {detail.rejection_reason && (
          <p className="mt-2 text-xs text-red-700">
            {detail.rejection_reason}
          </p>
        )}
      </div>

      {/* Documents section */}
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase text-gray-500">
          Documents
        </h3>
        {detail.documents.length === 0 ? (
          <p className="text-xs text-gray-500">No active documents.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {detail.documents.map((doc) => (
              <div key={doc.id} className="rounded-md border border-gray-100 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-700">
                    {doc.doc_type}
                  </span>
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

      {/* ================================================================
          STATE-DEPENDENT ACTION AREA
          ================================================================ */}

      {/* STATE: submitted → Show "Verify" button */}
      {isSubmitted && (
        <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-blue-900">
            Ready for verification
          </h3>
          <p className="mb-3 text-xs text-blue-700">
            All 3 documents have passed format checks. Run the internal
            verification to check consistency across databases.
          </p>
          <Button
            variant="primary"
            onClick={handleVerify}
            isLoading={verifyState.status === "loading"}
          >
            Verify with internal databases
          </Button>
          {verifyState.status === "error" && (
            <Alert variant="error">{verifyState.message}</Alert>
          )}
        </div>
      )}

      {/* STATE: verified_matching → Show matched checks + Approve button */}
      {isVerifiedMatching && detail.matched_checks && (
        <div className="rounded-md border border-green-200 bg-green-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-green-900">
            All checks matched
          </h3>
          <p className="mb-3 text-xs text-green-700">
            The following verification checks all passed successfully:
          </p>
          <CheckResultList checks={detail.matched_checks} variant="matched" />
          <div className="mt-4">
            <Button
              variant="primary"
              onClick={() => handleDecide("approved")}
              isLoading={resolveState.status === "loading"}
            >
              Approve &amp; activate account
            </Button>
          </div>
          {resolveState.status === "error" && (
            <Alert variant="error">{resolveState.message}</Alert>
          )}
          {resolveState.status === "success" && (
            <Alert variant="success">Decision recorded successfully.</Alert>
          )}
        </div>
      )}

      {/* STATE: verified_mismatched → Show mismatched checks + editable cause + Reject button */}
      {isVerifiedMismatched && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-red-900">
            Mismatches found
          </h3>

          {/* Show matched checks (green) if any */}
          {detail.matched_checks && detail.matched_checks.length > 0 && (
            <div className="mb-3">
              <p className="mb-1 text-xs font-medium text-green-800">
                Passed checks:
              </p>
              <CheckResultList
                checks={detail.matched_checks}
                variant="matched"
              />
            </div>
          )}

          {/* Show mismatched checks (red) */}
          {detail.mismatched_checks && (
            <div className="mb-3">
              <p className="mb-1 text-xs font-medium text-red-800">
                Failed checks:
              </p>
              <CheckResultList
                checks={detail.mismatched_checks}
                variant="mismatched"
              />
            </div>
          )}

          {/* Risk breakdown — point-by-point explanation */}
          {detail.mismatched_checks && detail.mismatched_checks.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-gray-700">
                Risk Score Breakdown:
              </p>
              <RiskBreakdown mismatchedChecks={detail.mismatched_checks} />
            </div>
          )}

          {/* Editable rejection cause — pre-filled from auto-generated cause */}
          <div className="mt-3">
            <InputField
              label="Rejection message (shown to merchant)"
              value={resolveNote}
              onChange={(e) => setResolveNote(e.target.value)}
              placeholder={detail.rejection_cause || "Enter a rejection reason…"}
            />
            <p className="mt-1 text-xs text-red-600">
              Pre-filled from verification results. Edit if needed, or leave as-is to
              send the auto-generated message.
            </p>
          </div>

          <div className="mt-3">
            <Button
              variant="secondary"
              onClick={() => handleDecide("rejected")}
              isLoading={resolveState.status === "loading"}
            >
              Reject &amp; notify merchant
            </Button>
          </div>
          {resolveState.status === "error" && (
            <Alert variant="error">{resolveState.message}</Alert>
          )}
          {resolveState.status === "success" && (
            <Alert variant="success">Decision recorded successfully.</Alert>
          )}
        </div>
      )}

      {/* Audit trail — always shown */}
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase text-gray-500">
          Audit Trail
        </h3>
        <VerificationTimeline entries={detail.audit_trail} compact={false} />
      </div>
    </div>
  );
}

const MerchantDetailView = memo(MerchantDetailViewBase);

export const AdminPage = memo(AdminPageBase);
