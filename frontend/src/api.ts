/**
 * api.ts
 * ------
 * The only file that talks to the backend. Components never call
 * `fetch` directly — they call these typed functions instead. This
 * keeps the HTTP/error-handling details in one place and makes the
 * backend contract easy to change without touching UI code.
 */

import { API_BASE_URL } from "./constants";
import type {
  ApiErrorBody,
  AuthResponse,
  DocumentStatus,
  DocumentType,
  MerchantDetail,
  MerchantStatus,
  MerchantSummary,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

let authToken: string | null = null;

/** Called once after login/signup so subsequent requests are authenticated. */
export function setAuthToken(token: string | null): void {
  authToken = token;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    // Network failure (server down, no connectivity) — distinct from an
    // HTTP error response, and just as important to surface clearly.
    throw new ApiError("Could not reach the server. Please check your connection.", 0);
  }

  if (!response.ok) {
    let detail = "Something went wrong. Please try again.";
    try {
      const body = (await response.json()) as ApiErrorBody;
      detail = body.detail || detail;
    } catch {
      // Response body wasn't valid JSON — fall back to the generic message.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export function signup(
  businessName: string,
  email: string,
  password: string
): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_name: businessName, email, password }),
  });
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function uploadDocument(docType: DocumentType, file: File): Promise<DocumentStatus> {
  const formData = new FormData();
  formData.append("file", file);
  return request<DocumentStatus>(`/documents/upload?doc_type=${docType}`, {
    method: "POST",
    body: formData,
  });
}

export function getMerchantStatus(): Promise<MerchantStatus> {
  return request<MerchantStatus>("/documents/merchant-status");
}

/** Restarts a rejected application — retires old docs and resets status to pending. */
export function restartApplication(): Promise<MerchantStatus> {
  return request<MerchantStatus>("/documents/restart-application", { method: "POST" });
}

// ---------------------------------------------------------------------------
// Admin / reviewer endpoints
// ---------------------------------------------------------------------------

/** Lists all merchants, optionally filtered by onboarding_status. */
export function getAdminMerchants(statusFilter?: string, sortByRisk?: boolean): Promise<MerchantSummary[]> {
  const params = new URLSearchParams();
  if (statusFilter) params.set("status_filter", statusFilter);
  if (sortByRisk) params.set("sort_by_risk", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  return request<MerchantSummary[]>(`/admin/merchants${query}`);
}

/** Returns full detail for a single merchant, including documents + audit trail. */
export function getMerchantDetail(merchantId: number): Promise<MerchantDetail> {
  return request<MerchantDetail>(`/admin/merchants/${merchantId}`);
}

/** Phase 3: admin-triggered verification — runs LLM + external checks on demand. */
export function verifyApplication(merchantId: number): Promise<MerchantDetail> {
  return request<MerchantDetail>(`/admin/merchants/${merchantId}/verify`, {
    method: "POST",
  });
}

/** The admin's mandatory sign-off: approve (one click) or reject (note optional, defaults to stored rejection_cause). */
export function decideApplication(
  merchantId: number,
  decision: "approved" | "rejected",
  note?: string,
): Promise<MerchantSummary> {
  return request<MerchantSummary>(`/admin/merchants/${merchantId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note: note || null }),
  });
}

