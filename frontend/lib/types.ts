// Types copied from the real route output (decisions.md #103): backend/app/api/{security,mock,approvals,auth}.py

export type Decision = "ALLOW" | "BLOCK" | "APPROVAL_REQUIRED";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type ApprovalStatus = "pending" | "approved" | "rejected";
export type EnvironmentName = "staging" | "production";
export type ExecutionStatus = "not_executed" | "executed" | "failed";

export interface Risk {
  rule_risk_level: RiskLevel;
  ml_risk_level: RiskLevel;
  final_risk_level: RiskLevel;
  reasons: string[];
}

export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface SecurityEvent {
  request_id: string;
  created_at: string | null;
  requester: string | null;
  agent: string | null;
  service_name: string | null;
  environment: EnvironmentName | null;
  tool: string | null;
  decision: Decision | null;
  reason: string | null;
  execution_status: ExecutionStatus;
  risk: Risk | null;
  approval_status: ApprovalStatus | null;
}

export interface MockService {
  service_name: string;
  environment: EnvironmentName;
  current_version: number;
  known_good_version: number;
  status: string;
  owner: string;
}

export interface ApprovalItem {
  id: number;
  request_id: string;
  status: ApprovalStatus;
  created_at: string | null;
  decided_at: string | null;
  reviewer: string | null;
  reason: string | null;
  revalidation: string | null;
  requester: string | null;
  agent: string | null;
  service_name: string | null;
  environment: EnvironmentName | null;
  tool: string | null;
  arguments: Record<string, unknown>;
  risk: Risk | null;
}

export interface DecisionResult {
  approval_id: number;
  request_id: string;
  approval_status: ApprovalStatus;
  outcome: "executed" | "revalidation_failed" | "rejected";
  reason?: string;
  result?: unknown;
}
