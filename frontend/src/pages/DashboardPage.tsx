/**
 * DashboardPage.tsx
 * -----------------
 * The main onboarding screen: three document upload slots, live status
 * polling, and the states that follow submission.
 *
 * Flow:
 *   - Merchant uploads all 3 documents. Each only gets an instant
 *     format-validity check (see DocumentSlot.tsx) — no identity or
 *     government-database verification happens client-side or is shown
 *     to the merchant directly.
 *   - Once all 3 pass format checks, onboarding_status becomes
 *     "submitted" — document slots hide, and a neutral "under review"
 *     message shows. The automated OCR/LLM/external-check pipeline runs
 *     in the background as a RECOMMENDATION for the admin only (see
 *     documents.py's _run_verification_if_ready) — it never reaches the
 *     merchant directly.
 *   - An admin's explicit decision (AdminPage.tsx) is the only thing
 *     that can move onboarding_status to "active" or "rejected". The
 *     "rejection_reason" field, when present, is already humanized by
 *     verify.humanize_reason() and safe to show directly.
 *   - "rejected" hides the document slots and shows a "Start a new
 *     application" button (see restartApplication()).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { getMerchantStatus, restartApplication, ApiError } from "../api";
import { useAuth } from "../AuthContext";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { DocumentSlot } from "../components/DocumentSlot";
import { DOCUMENT_SLOTS } from "../constants";
import type { AsyncState, DocumentStatus, DocumentType, MerchantStatus } from "../types";

const POLL_INTERVAL_MS = 4000;

export function DashboardPage() {
  const { session, logout } = useAuth();
  const [statusState, setStatusState] = useState<AsyncState<MerchantStatus>>({ status: "loading" });
  const [restartState, setRestartState] = useState<AsyncState<MerchantStatus>>({ status: "idle" });
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getMerchantStatus();
      setStatusState({ status: "success", data });
    } catch (error) {
      setStatusState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not load your status.",
      });
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    // Poll for updates while any document is still verifying, so the
    // merchant sees the outcome without manually refreshing.
    pollTimerRef.current = setInterval(fetchStatus, POLL_INTERVAL_MS);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [fetchStatus]);

  const handleUploaded = useCallback((updated: DocumentStatus) => {
    setStatusState((prev) => {
      if (prev.status !== "success") return prev;
      const withoutOld = prev.data.documents.filter((d) => d.doc_type !== updated.doc_type);
      return {
        status: "success",
        data: { ...prev.data, documents: [...withoutOld, updated] },
      };
    });
  }, []);

  /** Calls the restart-application endpoint, then refreshes status to show empty slots. */
  const handleRestart = useCallback(async () => {
    setRestartState({ status: "loading" });
    try {
      const result = await restartApplication();
      setRestartState({ status: "success", data: result });
      // Refresh the full status so the empty document slots reappear.
      await fetchStatus();
    } catch (error) {
      setRestartState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not restart application.",
      });
    }
  }, [fetchStatus]);

  const findDocument = useCallback(
    (docType: DocumentType, documents: DocumentStatus[]): DocumentStatus | null =>
      documents.find((d) => d.doc_type === docType) ?? null,
    []
  );

  /** Whether the merchant's application is in the rejected state. */
  const isRejected = statusState.status === "success" && statusState.data.onboarding_status === "rejected";
  const isSubmitted = statusState.status === "success" && statusState.data.onboarding_status === "submitted";
  const isActive = statusState.status === "success" && statusState.data.onboarding_status === "active";

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <span className="text-sm font-medium text-gray-900">{session?.business_name}</span>
        <Button variant="secondary" onClick={logout}>
          Log out
        </Button>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="mb-2 text-xl font-medium text-gray-900">Complete your onboarding</h1>
        <p className="mb-8 text-sm text-gray-500">
          Upload the documents below. We&apos;ll verify them automatically and let you know the result.
        </p>

        {statusState.status === "loading" && (
          <p className="text-sm text-gray-500" role="status">
            Loading your onboarding status…
          </p>
        )}

        {statusState.status === "error" && <Alert variant="error">{statusState.message}</Alert>}

        {/* Approved state — account activated */}
        {statusState.status === "success" && statusState.data.onboarding_status === "active" && (
          <Alert variant="success">
            Your account has been activated. All services are now enabled for your business.
          </Alert>
        )}

        {/* Submitted state — documents received, awaiting the admin's
            mandatory review. The merchant never sees the automated
            check's technical reasoning here; only a plain status update.
            Document slots stay hidden while awaiting review (mirrors the
            already-submitted 409 the backend returns on re-upload). */}
        {statusState.status === "success" && statusState.data.onboarding_status === "submitted" && (
          <Alert variant="info">
            Your documents have been received and are under review. We'll update your status
            here as soon as a decision has been made — no action is needed from you right now.
          </Alert>
        )}

        {/* Rejected state — show humanized rejection reason and restart button */}
        {statusState.status === "success" && isRejected && (
          <div className="mt-6 flex flex-col gap-4">
            <Alert variant="error">
              {statusState.data.rejection_reason ||
                "Your application was not approved. Please review the feedback below and start a new application."}
            </Alert>
            <div>
              <Button onClick={handleRestart} isLoading={restartState.status === "loading"}>
                Start a new application
              </Button>
            </div>
            {restartState.status === "error" && <Alert variant="error">{restartState.message}</Alert>}
          </div>
        )}

        {/* Document upload slots — hidden once submitted (awaiting review), rejected, or active */}
        {statusState.status === "success" && !isRejected && !isSubmitted && !isActive && (
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {DOCUMENT_SLOTS.map((slot) => (
              <DocumentSlot
                key={slot.type}
                docType={slot.type}
                label={slot.label}
                hint={slot.hint}
                onUploaded={handleUploaded}
                currentStatus={findDocument(slot.type, statusState.data.documents)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
