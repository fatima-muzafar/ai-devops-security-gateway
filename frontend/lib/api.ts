// All backend calls go through this file (decisions.md #99, #103).
// The token is passed in as an argument; this module never stores it (#95).
// This file never mentions the internal tool-execution route (Section 5).
import type {
  ApprovalItem,
  ApprovalStatus,
  ChatResult,
  DecisionResult,
  LoginResult,
  MockService,
  SecurityEvent,
} from "./types";

// Must be the literal process.env.NEXT_PUBLIC_... so Next.js can inline it at build time.
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/+$/,
  "",
);

export class ApiError extends Error {
  status: number; // 0 = the API could not be reached
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function detailText(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return fallback;
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  options: { token?: string; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the API at ${API_BASE}. Is uvicorn running, and is this page's address in CORS_ALLOWED_ORIGINS?`,
    );
  }

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // the body was not JSON; the status code is still reported below
  }
  if (!response.ok) {
    throw new ApiError(response.status, detailText(data, `Request failed (HTTP ${response.status}).`));
  }
  return data as T;
}

export function login(username: string, password: string): Promise<LoginResult> {
  return request<LoginResult>("POST", "/api/auth/login", { body: { username, password } });
}

export function sendChat(token: string, message: string): Promise<ChatResult> {
  return request<ChatResult>("POST", "/api/chat", { token, body: { message } });
}

export function getEvents(token: string): Promise<SecurityEvent[]> {
  return request<SecurityEvent[]>("GET", "/api/security/events?limit=50", { token });
}

export function getServices(token: string): Promise<MockService[]> {
  return request<MockService[]>("GET", "/api/mock/services", { token });
}

export function getApprovals(token: string, status: ApprovalStatus): Promise<ApprovalItem[]> {
  return request<ApprovalItem[]>("GET", `/api/approvals?status=${status}`, { token });
}

export function decideApproval(
  token: string,
  approvalId: number,
  action: "approve" | "reject",
  reason: string,
): Promise<DecisionResult> {
  return request<DecisionResult>("POST", `/api/approvals/${approvalId}/${action}`, {
    token,
    body: { reason: reason.trim() || null },
  });
}
