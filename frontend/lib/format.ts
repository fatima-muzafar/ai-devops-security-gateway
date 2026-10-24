// Small display helpers (decisions.md #104). Everything returns plain text or a class name.
import type { Decision, Risk } from "./types";

export function formatTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function riskText(risk: Risk | null): string {
  if (!risk) return "none";
  return `${risk.final_risk_level} (rule ${risk.rule_risk_level}, ml ${risk.ml_risk_level})`;
}

export function reasonsText(risk: Risk | null): string {
  return risk && Array.isArray(risk.reasons) ? risk.reasons.join(", ") : "";
}

export function decisionClass(decision: Decision | null): string {
  if (decision === "ALLOW") return "badge badge-allow";
  if (decision === "BLOCK") return "badge badge-block";
  if (decision === "APPROVAL_REQUIRED") return "badge badge-approval";
  return "badge";
}
