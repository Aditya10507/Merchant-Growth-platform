/**
 * DocumentSlot.tsx
 * ----------------
 * One upload slot (PAN / GST / Bank proof). Handles:
 *   - Client-side file type/size validation before anything is sent
 *     over the network (fast feedback, per UI/UX doc).
 *   - Calling the upload API and rendering every resulting state:
 *     empty, uploading, invalid-format, verifying, and the server's
 *     final per-document status badge.
 *
 * The upload endpoint returns instantly (OCR runs in the background),
 * so this component never blocks for more than a second on the upload
 * itself. The "verifying" status updates come via the parent's polling.
 *
 * Important: the "valid document" / "invalid document" messages below
 * are derived directly from `currentStatus` (the latest polled state),
 * never stored in local component state. Storing it locally previously
 * caused a bug where a one-time "verifying identity details..." message
 * kept showing even after the merchant's overall application had
 * already been decided — because local state never resynced with the
 * newer status coming in from the poll.
 *
 * This component also intentionally does NOT show the shared,
 * merchant-wide verification outcome (e.g. an external-database
 * mismatch) here — that's a cross-document, application-level result,
 * not something specific to this one document, and showing it under
 * every single card was confusing (e.g. a bank-proof card claiming
 * "PAN not found in government database"). That explanation is shown
 * once, at the application level, in DashboardPage.
 */

import { memo, useCallback, useRef, useState } from "react";

import { uploadDocument, ApiError } from "../api";
import {
  ALLOWED_FILE_TYPES,
  ALLOWED_FILE_TYPES_LABEL,
  MAX_UPLOAD_SIZE_BYTES,
  MAX_UPLOAD_SIZE_MB,
} from "../constants";
import type { AsyncState, DocumentStatus, DocumentType } from "../types";
import { Alert } from "./Alert";
import { StatusBadge } from "./StatusBadge";

interface DocumentSlotProps {
  docType: DocumentType;
  label: string;
  hint: string;
  onUploaded: (status: DocumentStatus) => void;
  currentStatus: DocumentStatus | null;
}

/** Client-side validation: checks file type and size before uploading. */
function validateFile(file: File): string | null {
  if (!ALLOWED_FILE_TYPES.includes(file.type as (typeof ALLOWED_FILE_TYPES)[number])) {
    return `Please upload a ${ALLOWED_FILE_TYPES_LABEL} file.`;
  }
  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return `File is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum size is ${MAX_UPLOAD_SIZE_MB}MB.`;
  }
  return null;
}

function DocumentSlotBase({ docType, label, hint, onUploaded, currentStatus }: DocumentSlotProps) {
  const [uploadState, setUploadState] = useState<AsyncState<DocumentStatus>>({ status: "idle" });
  const [clientError, setClientError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelected = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      const validationError = validateFile(file);
      if (validationError) {
        setClientError(validationError);
        setUploadState({ status: "idle" });
        return;
      }
      setClientError(null);
      setUploadState({ status: "loading" });

      try {
        const result = await uploadDocument(docType, file);
        setUploadState({ status: "success", data: result });
        onUploaded(result);
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "Upload failed. Please try again.";
        setUploadState({ status: "error", message });
      } finally {
        // Allow re-selecting the same file again (e.g. after a rejection).
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [docType, onUploaded]
  );

  const displayedStatus = currentStatus ?? (uploadState.status === "success" ? uploadState.data : null);

  // Derived directly from the latest known status on every render — this
  // can never go stale the way a separately-tracked boolean could.
  const isInvalidFormat = displayedStatus?.verification_status === "invalid_format";
  const isVerifying = displayedStatus?.verification_status === "verifying";

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-900">{label}</h3>
        {displayedStatus && <StatusBadge status={displayedStatus.verification_status} />}
      </div>

      <p className="text-xs text-gray-500">{hint}</p>

      {/* File constraints hint — shows accepted types and max size */}
      <p className="text-xs text-gray-400">
        Accepted: {ALLOWED_FILE_TYPES_LABEL} — Max {MAX_UPLOAD_SIZE_MB}MB
      </p>

      <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-gray-300 px-4 py-6 text-center hover:border-brand-500">
        <span className="text-sm text-brand-700">
          {uploadState.status === "loading" ? "Uploading…" : "Click to upload"}
        </span>
        <input
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_FILE_TYPES.join(",")}
          className="sr-only"
          onChange={handleFileSelected}
          disabled={uploadState.status === "loading"}
          aria-label={`Upload ${label}`}
        />
      </label>

      {clientError && <Alert variant="error">{clientError}</Alert>}
      {uploadState.status === "error" && <Alert variant="error">{uploadState.message}</Alert>}

      {/* Instant, per-document format feedback only — this document's own
          OCR format check, never the shared merchant-wide verification
          outcome (that's shown once at the application level instead). */}
      {isInvalidFormat && (
        <Alert variant="error">
          {displayedStatus?.rejection_reason || "Invalid document — please check the document and try again."}
        </Alert>
      )}
      {isVerifying && <Alert variant="success">Valid document — verifying identity details…</Alert>}
    </div>
  );
}

export const DocumentSlot = memo(DocumentSlotBase);
