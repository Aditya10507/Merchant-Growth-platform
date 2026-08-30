/**
 * DashboardPage.tsx
 * -----------------
 * The main onboarding screen: three document upload slots, live status
 * polling, and the states that follow submission.
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

  const handleRestart = useCallback(async () => {
    setRestartState({ status: "loading" });
    try {
      const result = await restartApplication();
      setRestartState({ status: "success", data: result });
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

  const isRejected = statusState.status === "success" && statusState.data.onboarding_status === "rejected";
  const isSubmitted = statusState.status === "success" && statusState.data.onboarding_status === "submitted";
  const isActive = statusState.status === "success" && statusState.data.onboarding_status === "active";

  return (
    <div className="min-h-screen bg-white">
      {/* Header bar — slim, border-based, no background color */}
      <header className="flex items-center justify-between border-b border-gray-200 px-6 py-3">
        <span className="text-sm font-medium text-gray-900">{session?.business_name}</span>
        <Button variant="secondary" onClick={logout}>
          Log out
        </Button>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="mb-2 text-xl font-semibold text-gray-900">Complete your onboarding</h1>
        <p className="mb-8 text-sm text-gray-500">
          Upload the documents below. We&apos;ll verify them automatically and let you know the result.
        </p>

        {statusState.status === "loading" && (
          <p className="text-sm text-gray-500" role="status">
            Loading your onboarding status…
          </p>
        )}

        {statusState.status === "error" && <Alert variant="error">{statusState.message}</Alert>}

        {/* Approved state */}
        {statusState.status === "success" && statusState.data.onboarding_status === "active" && (
          <Alert variant="success">
            Your account has been activated. All services are now enabled for your business.
          </Alert>
        )}

        {/* Submitted state */}
        {statusState.status === "success" && statusState.data.onboarding_status === "submitted" && (
          <Alert variant="info">
            Your documents have been received and are under review. We'll update your status
            here as soon as a decision has been made — no action is needed from you right now.
          </Alert>
        )}

        {/* Rejected state */}
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

        {/* Document upload slots */}
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
