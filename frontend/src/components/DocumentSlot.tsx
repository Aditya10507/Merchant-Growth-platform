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
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [docType, onUploaded]
  );

  const displayedStatus = currentStatus ?? (uploadState.status === "success" ? uploadState.data : null);

  const isInvalidFormat = displayedStatus?.verification_status === "invalid_format";
  const isVerifying = displayedStatus?.verification_status === "verifying";

  return (
    <div className="flex flex-col gap-3 rounded-md border border-gray-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-900">{label}</h3>
        {displayedStatus && <StatusBadge status={displayedStatus.verification_status} />}
      </div>

      <p className="text-xs text-gray-500">{hint}</p>

      <p className="text-xs text-gray-400">
        Accepted: {ALLOWED_FILE_TYPES_LABEL} — Max {MAX_UPLOAD_SIZE_MB}MB
      </p>

      <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-gray-300 px-4 py-6 text-center hover:border-gray-500">
        <span className="text-sm text-gray-700">
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
