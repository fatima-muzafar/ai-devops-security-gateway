# Security Gateway for Autonomous DevOps AI Agents

*Complete FYP Planning & Pre-Implementation Specification — Revision 6*

Final project: Security Gateway for Autonomous DevOps AI Agents

Domain: Artificial Intelligence + Cybersecurity + Agentic AI + Secure DevOps Tool Execution

Agent framework: Python + LangChain + LLM

Backend: Python + FastAPI | Security Gateway: Python | MCP: Python | Database: PostgreSQL

Environment: Stateful mock/sandbox DevOps environment only

Team: 3 members (confirmed Revision 6). No module, tool, service, or role scope changes were made as a result of team-size confirmation — see Section 27.

**Purpose of this revision:** Revision 6 closes review findings from the independent Revision 5 assessment. It does not add modules, tools, services, roles, or timeline. Specifically, Revision 6: (1) defines the previously-unspecified rule-risk / ML-risk decision combination logic (Section 11); (2) redefines Staged-Attack Detection Rate and Approve-then-Execute Gap Prevention Rate as measured over repeated generated trials rather than single demonstrations (Section 25); (3) reframes E1 as a necessity/sanity check rather than a headline research result (Section 25); (4) divides tool-sequence anomaly detection explicitly between the rule engine and the ML model to avoid overlapping/redundant detection claims (Section 10); (5) defines the version representation used for version_change_delta (Section 13); (6) documents the synthetic-anomaly evaluation limitation for the final report (Section 23); and (7) makes several minor clarifications (Sections 9, 11, 16, 27, 33). All changes are specification precision, not new features.

# 1. Executive Summary

The project is an AI-powered DevOps automation system protected by a dedicated Security Gateway. A developer interacts with an Autonomous DevOps AI Agent using natural language. The agent uses an LLM and LangChain to understand the request and generate a structured tool request when an operational action is needed.

The agent does not directly execute DevOps tools. Every tool request must pass through the Security Gateway. The Gateway authenticates the requester, validates the request, checks identity, service ownership and environment permissions, applies policy, evaluates deterministic and behavioral risk, and produces ALLOW, BLOCK, or APPROVAL_REQUIRED.

If the final decision is ALLOW, the Gateway calls the internal MCP server. MCP executes the registered tool against the stateful mock DevOps environment. A state-changing action therefore produces an observable state change. BLOCK means MCP is not called and the mock state does not change. APPROVAL_REQUIRED pauses execution until an authorized human approves, after which the Gateway revalidates the request before MCP execution.

The project is therefore not merely a chatbot. The core FYP contribution is controlled AI-agent tool execution for DevOps operations using policy enforcement, environment-aware authorization, behavioral anomaly detection, human approval, auditability, and measurable security evaluation.

Research question: Can a Security Gateway combining authorization/policy enforcement and behavioral anomaly detection reduce unsafe tool execution by an autonomous DevOps AI agent, particularly unauthorized or abnormal production actions, while maintaining acceptable latency and false-positive rates?

# 2. Project Identity and Scope

| Field | Final definition |
| --- | --- |
| Project | Security Gateway for Autonomous DevOps AI Agents |
| Domain | AI + Cybersecurity + Agentic AI + Secure DevOps Tool Execution |
| Application | Controlled DevOps / infrastructure operations automation |
| Primary objective | Prevent or contain unauthorized, abnormal, invalid, and unapproved AI-agent infrastructure actions |
| Team size | 3 members (confirmed Revision 6) |
| Agent | One autonomous DevOps AI agent |
| Agent framework | Python + LangChain + LLM |
| Tools | Five MCP tools |
| Environment | Stateful mock/sandbox only |
| Services | 3 services x 2 environments |
| Roles | junior_developer, senior_developer, admin/SRE |
| Decisions | ALLOW, BLOCK, APPROVAL_REQUIRED |
| ML | Isolation Forest anomaly detection |
| Human control | Admin/lead approval workflow |

# 3. Problem Statement

Autonomous AI agents can interpret developer requests and generate tool calls that change infrastructure state. In DevOps, operations such as restarting services, rolling back deployments, and deploying new versions can have significant impact, especially in production.

If an agent is manipulated, misconfigured, or behaves abnormally, direct tool access creates a security and reliability risk. The proposed solution inserts a Security Gateway between the agent and the MCP/tool execution layer.

The Gateway treats every tool request as untrusted until it passes authentication, schema/business validation, identity and ownership checks, environment authorization, policy, risk assessment, decision enforcement, and audit logging.

# 4. High-Level Architecture

Developer -> Next.js Frontend -> Python FastAPI Backend -> Autonomous DevOps AI Agent -> LLM + LangChain -> Structured Tool Request -> SECURITY GATEWAY (Authentication, Validation, Identity/Service Ownership, Environment Authorization, Policy Engine, Rule Risk, ML Anomaly Detection, Decision Engine, Approval Workflow, Audit Logging) -> ALLOW/BLOCK/APPROVAL_REQUIRED -> Internal MCP Server -> Five Registered DevOps Tools -> Stateful Mock DevOps Environment

Trust boundary: the browser and the agent are not trusted execution layers. MCP is downstream of the Gateway. The Gateway is the mandatory security boundary.

Core execution rule: Agent -> structured request -> Gateway -> decision -> MCP only when execution is authorized.

# 5. Architectural and Security Principles

- Every agent tool request must pass through the Security Gateway.
- The Gateway is a security boundary, not merely a router.
- The browser never calls MCP directly.
- The agent never calls MCP directly.
- Authentication, validation, authorization, risk assessment, decision enforcement, execution, and audit logging are separate responsibilities.
- Policy handles known authorization rules; ML handles behavioral anomalies that static rules may miss.
- A forbidden authorization/policy action remains forbidden even if ML considers the behavior normal.
- ML risk cannot grant permissions. ML can only escalate a decision toward APPROVAL_REQUIRED or BLOCK, never move it toward ALLOW (see Section 11).
- ALLOW means the authorized MCP tool actually executes against the mock environment.
- BLOCK means MCP is not called and no mock-environment state change occurs.
- APPROVAL_REQUIRED means execution is paused until authorized approval; the request is revalidated before execution.
- The mock environment is stateful so approved state-changing operations create observable changes.
- All tool execution remains confined to the mock environment.
- Request IDs connect the agent request, Gateway checks, risk assessment, approval, MCP execution, state change, and audit evidence.

# 6. Autonomous DevOps AI Agent

Implementation choice: The agent will be implemented in Python. LangChain will be used as the agent/tool-orchestration framework, while the LLM provides natural-language understanding and structured tool-selection capability.

LangChain is an orchestration layer, not the security layer. The agent may use LangChain to define the available tool schemas and decide which tool request should be proposed, but the actual tool execution is controlled outside the agent by the Security Gateway.

## Agent responsibilities

- Accept developer natural-language commands.
- Understand intent and relevant conversation context.
- Answer informational questions without tools when possible.
- Determine when a DevOps operation is required.
- Generate a structured tool request containing tool name and validated-looking arguments.
- Send the structured request to the Security Gateway instead of executing it directly.
- Receive the Gateway/MCP result and convert it into a natural-language response.
- Never bypass the Gateway.

Example: Developer says "Restart payment-service in staging." The agent proposes restart_service(service=payment-service, environment=staging). The Gateway independently decides whether this request is executable.

# 7. LangChain Agent Design

Selected approach: Python + LangChain + LLM with structured tool requests. LangChain is included because it simplifies agent orchestration, prompt management, tool schemas, and model/tool interaction without requiring the team to build a custom agent framework.

Important security design: The five MCP tools are not exposed to the LangChain agent as directly executable infrastructure functions. Instead, the agent produces a structured tool-request object that is sent to the Gateway. The Gateway is the only component permitted to invoke MCP.

Recommended logical flow: LangChain Agent -> Tool intent / structured request -> POST /api/gateway/tool-request -> Security Gateway -> MCP only after ALLOW / approved request

Why this matters: If LangChain were allowed to execute infrastructure tools directly, the agent could bypass the main security contribution. Therefore, LangChain handles reasoning/orchestration, while the Gateway handles authorization and execution control.

Scope control: Start with a simple single-agent LangChain implementation. Do not introduce multi-agent orchestration or complex LangGraph workflows unless a later evaluation demonstrates a genuine need.

# 8. Security Gateway

## Gateway pipeline

Tool Request -> Authentication -> Schema + Business Validation -> Identity / Role -> Service Ownership -> Environment Permission -> Policy -> Rule Risk + ML Anomaly -> Decision Engine -> ALLOW / BLOCK / APPROVAL_REQUIRED -> MCP only when permitted

- Authenticate the developer and identify the agent.
- Validate that the tool is registered and enabled.
- Validate argument schema and business constraints.
- Resolve role, target service, and target environment.
- Check service ownership independently from role permission.
- Check role + action + environment policy.
- Calculate deterministic rule risk.
- Generate an ML anomaly signal from behavioral history, drawn from a sliding context window of the most recent N = 5 actions per identity per target service/environment (see Section 10).
- Combine rule risk and ML anomaly into a single final risk level using the fixed combination logic in Section 11, then apply decision precedence.
- Return ALLOW, BLOCK, or APPROVAL_REQUIRED.
- Call MCP only when the final decision permits execution.
- On an APPROVAL_REQUIRED path, apply TOCTOU-style revalidation: re-run authentication, authorization, ownership and policy checks immediately before MCP invocation, so that a request approved earlier cannot execute against a state that has since changed (see Section 11 and Section 14).
- Record complete security evidence.

Naming note: the revalidation-before-execution step already existed in Revision 4's approval workflow; Revision 5 gave it the standard security-literature name (time-of-check-to-time-of-use, TOCTOU) so it can be cited precisely in the report and evaluated as its own control. Revision 6 makes no further change to this control beyond the decision-logic clarification in Section 11.

# 9. Identity, Service Ownership and Policy Engine [UPDATED in Revision 6]

Identity answers who is requesting. Service ownership answers whether that identity is assigned to the target service. Environment authorization answers whether that role is permitted to act in staging or production. Policy combines these controls with action sensitivity.

| Role | Typical permissions |
| --- | --- |
| junior_developer | Read logs/metrics on assigned services only; restart assigned services in staging. Junior developers cannot read logs/metrics on services they are not assigned to — read access follows the same ownership check as write access, it is not a separately relaxed permission. |
| senior_developer | Restart/rollback staging and production for assigned services; deploy on staging; production actions may require approval |
| admin / SRE | Configured administrative access and approval management |

*Clarification (Revision 6): the Revision 5 draft left it ambiguous whether low-sensitivity read tools (get_logs, get_metrics) were exempt from the ownership check. They are not. All five tools, including the two read-only tools, are subject to the same service-ownership check; only sensitivity (used in rule risk, Section 10) differs by tool. This is a clarification of existing intent, not a policy change.*

Examples: junior developer + assigned staging restart -> ALLOW; junior developer + production deploy -> BLOCK/APPROVAL_REQUIRED according to policy; any role + unassigned service -> BLOCK; production deployment without required approval -> no MCP execution.

# 10. Risk Engine and Behavioral ML [UPDATED in Revision 6]

The Risk Engine combines deterministic rule signals with a behavioral anomaly model. The initial model is Isolation Forest using scikit-learn.

Rule risk represents known operational/security conditions such as production targeting, sensitive tools, repeated denied requests, or approval-required operations. ML anomaly represents behavior that deviates from learned normal behavior. How the two are combined into one decision is fixed and specified in Section 11 — this section defines the input signals only.

Sliding context window: behavioral features are computed over a sliding window of the last N = 5 actions per (identity, target service, target environment) tuple, in addition to the rolling time-window counts below. N = 5 is a starting default for calibration in Semester 2, not a fixed constant; the evaluation in Section 25 should confirm it before the final report.

## Candidate behavior features

- Requests per recent time window.
- Restart/deployment frequency.
- Production-targeting frequency.
- Outside-working-hours activity flag (off_hours_flag) — boolean feature marking whether a request timestamp falls outside the configured working-hours window.
- Distinct services touched within a short period.
- Repeated failed or denied attempts.
- Unusual tool sequences within the last N = 5 actions (the sliding context window) — see the rule/ML division below.
- Deploy followed immediately by rollback.
- Burst activity from one identity.
- Version change magnitude (version_change_delta) — a state-aware feature computed from the mock environment's current_version/known_good_version fields (see Section 13 for the integer version representation), capturing how large a version jump a deploy or rollback represents.

## Rule engine vs ML: division of sequence-detection responsibility

*Clarification (Revision 6): Section 15 assigns several threats jointly to "Rules + ML", and Section 10 lists "unusual tool sequences" as an ML feature. Without a stated division, the rule engine and the Isolation Forest could end up detecting the same enumerable patterns, which would understate the ML model's real contribution in E2. The division is fixed as follows and must not be changed without new evaluation evidence (Section 31).*

- Rule engine (deterministic, enumerated) detects specific, named sequence patterns that are cheap to hand-code and do not require learned history: deploy immediately followed by rollback on the same service; N or more consecutive denied/failed attempts followed by a success; the identical destructive action (restart, rollback, deploy) repeated more than a fixed count within a short fixed time window.
- ML / Isolation Forest detects sequences that are statistically rare for a given identity's learned normal behavior but are not on the enumerated rule list — e.g. an atypical but individually-valid order of tool calls across two services, or a combination of low-risk actions whose joint frequency is abnormal for that identity even though no single named pattern matches.
- E2 (ML contribution) and E6 (multi-step/TOCTOU) must report which staged-attack test cases were caught by rule-based sequence detection alone versus which required the ML signal, so the ML contribution claim in the final report is not inflated by rule-catchable cases.

Critical rule: ML does not replace authorization. A developer who is forbidden from touching a service remains forbidden even if the ML model considers the request behaviorally normal.

Scope note: version_change_delta and off_hours_flag are the only two new features added in Revision 5. They are logged from data the mock environment and request timestamps already produce, so they do not require a new subsystem — but they are new features, and should be counted as such in the feature-engineering writeup rather than described as a pure relabeling.

# 11. Decision Engine and Execution Semantics [UPDATED in Revision 6]

The system must not use a single risk-score threshold as the only security mechanism. Hard authentication, validation, ownership, and policy failures have precedence.

## Step 1 — Hard checks (unconditional)

| Condition | Decision | MCP | Mock state |
| --- | --- | --- | --- |
| Authentication failure | BLOCK | No | No change |
| Malformed/invalid request | BLOCK | No | No change |
| Unregistered/disabled tool | BLOCK | No | No change |
| Ownership violation | BLOCK | No | No change |
| Forbidden role/action/environment | BLOCK | No | No change |

If any Step 1 condition is met, the Gateway returns BLOCK immediately. Risk scoring (Steps 2–4) is not performed — there is nothing to escalate.

## Step 2 — Rule risk level and ML risk level (independent computation)

*New in Revision 6: the combination logic below was unspecified in Revision 5. This closes that gap. It does not add new signals — rule risk and ML anomaly score were already planned inputs (Section 10); this defines how they become one decision.*

- rule_risk_level ∈ {LOW, MEDIUM, HIGH} is computed deterministically from the rule-risk conditions in Section 10 (production targeting, sensitive tool, repeated denials, etc.). Each rule-risk condition is assigned a fixed level at design time in Phase 9; combining multiple simultaneous rule-risk conditions takes the highest level triggered.
- ml_risk_level ∈ {LOW, MEDIUM, HIGH} is derived by mapping the Isolation Forest's continuous anomaly score against two calibrated thresholds, set during Phase 14/15 calibration using held-out normal data (target: keep false-positive rate on held-out normal traffic below an agreed ceiling, to be fixed during calibration and reported in Section 25).
- A policy rule may also independently mark an action as "always requires approval" regardless of computed risk (e.g. "production deploy always requires approval"). This is a policy flag, not a risk level, and is evaluated in Step 4.

## Step 3 — Combination (fixed rule)

- final_risk_level = max(rule_risk_level, ml_risk_level). The ML signal can only move the final level up, never down — this is the concrete mechanism behind the existing Section 5 principle that "ML risk cannot grant permissions." A LOW rule_risk_level with a HIGH ml_risk_level produces a HIGH final_risk_level; a HIGH rule_risk_level is never reduced by a LOW ml_risk_level.

## Step 4 — Decision mapping

| final_risk_level or policy flag | Decision | MCP | Mock state |
| --- | --- | --- | --- |
| Policy-mandated approval (regardless of risk level) | APPROVAL_REQUIRED | After approval + TOCTOU revalidation | After approval |
| LOW | ALLOW | Yes | Changes if state-changing |
| MEDIUM | APPROVAL_REQUIRED | After approval + TOCTOU revalidation | After approval |
| HIGH, non-production or reversible action | APPROVAL_REQUIRED | After approval + TOCTOU revalidation | After approval |
| HIGH, production and policy-designated irreversible/high-impact action | BLOCK | No | No change |

Which specific actions fall into the last two rows (HIGH → APPROVAL_REQUIRED vs HIGH → BLOCK) is a policy configuration decided per role/action/environment in Phase 8/15, not a runtime ML decision — this preserves "hard authorization/policy failures cannot be overridden by ML" (Section 5, Section 30).

## TOCTOU-style revalidation

For both APPROVAL_REQUIRED rows above, the Gateway re-checks authentication, authorization, ownership and policy at the moment of execution, not only at the moment of approval. This closes the gap between when a human approves a request and when MCP actually runs it — the same class of gap referenced generically as "revalidation" in Revision 4, named explicitly in Revision 5 so it can be tested as its own control in Section 25.

# 12. MCP Server and Five DevOps Tools

MCP is the controlled tool-execution layer. The Gateway is the only component allowed to invoke the MCP execution path.

| Tool | Sensitivity | Mock-environment effect |
| --- | --- | --- |
| get_logs() | Low | Read-only logs |
| get_metrics() | Low | Read-only metrics |
| restart_service() | Medium | Updates restart/status metadata |
| rollback_deployment() | Medium–High | Changes current version to known-good version |
| deploy_service() | High | Changes deployed/current version and records deployment |

The tool registry stores tool name, schema, sensitivity, enabled status, and allowed action metadata. Unregistered or disabled tools cannot execute.

# 13. Stateful Mock DevOps Environment [UPDATED in Revision 6]

The environment is deliberately simulated. No real AWS, Azure, GCP, Kubernetes cluster, or production infrastructure is connected. The mock environment is not just a set of hard-coded responses; it maintains state.

Recommended scope: 3 services x 2 environments = 6 combinations.

| Service | Staging | Production | Seeded owner example |
| --- | --- | --- | --- |
| auth-service | Yes | Yes | senior_developer_1, admin |
| payment-service | Yes | Yes | senior_developer_2, admin |
| notification-service | Yes | Yes | junior_developer_1, senior_developer_1 |

Each service/environment maintains current version, known-good version, status, deployment history, restart history, simulated logs, simulated metrics, timestamps, and counters.

*New in Revision 6 — version representation: current_version and known_good_version are stored as monotonically increasing integer counters (a per-service deployment sequence number), not semantic-version strings. version_change_delta = |current_version − target_version|, a plain integer subtraction. This was unspecified in Revision 5; a semver string representation would have made version_change_delta ambiguous to compute (e.g. is 2.0.0 → 1.9.9 a delta of 1 or of a major-version rollback?) and is deliberately avoided to keep the state-aware feature simple and defensible.*

Important behavior: if restart_service() is ALLOWED, restart count/history changes; if deploy_service() is ALLOWED, current version and deployment history change; if BLOCKED, none of these changes occur.

# 14. Human Approval Workflow

- Create pending approval with request_id.
- Show request, user, agent, service, environment, tool, risk, and reasons.
- Admin/lead approves or rejects.
- On approval, Gateway performs TOCTOU-style revalidation of authentication/authorization/policy and request integrity, immediately before execution.
- Only after successful revalidation does Gateway invoke MCP.
- Record reviewer, decision, reason, and timestamps.

This is the same step Revision 4 described as "revalidates the request before MCP execution"; Revision 5 names it explicitly as TOCTOU-style revalidation so it appears as a named control in the threat model (Section 15) and evaluation (Section 25) rather than only in prose.

# 15. Security Threat Model and Attack Scenarios

| Threat | Primary control | Expected result |
| --- | --- | --- |
| Prompt-injection-induced unsafe request | Validation + policy + risk | Block/approval |
| Unauthorized tool access | Role authorization | Block |
| Unassigned-service access | Ownership | Block |
| Disallowed environment | Environment policy | Block/approval |
| Excessive tool-call burst | Rules + ML (rule-enumerated bursts caught by rules; statistically rare bursts by ML — see Section 10) | Block/approval |
| Abnormal deploy/restart | Rules + ML (see Section 10 division) | Block/approval |
| Lateral movement | Ownership + ML | Block/approval |
| Production deploy without approval | Policy + approval | No MCP until approved |
| Invalid arguments | Schema/business validation | Block |
| Unregistered tool | Tool registry | Block |
| Direct MCP access attempt | Internal trust/authentication | Reject |
| Approve-then-execute gap (state changes between approval and execution) | TOCTOU-style revalidation | Re-block or re-escalate at execution time |
| Multi-step / staged attack (individually low-risk actions combined) | Sliding-window (N = 5) behavioral features + ML (rule-enumerated staged patterns are caught earlier by rules — see Section 10) | Block/approval on the sequence, not just the single action |

# 16. Database Design [UPDATED in Revision 6]

| Table | Purpose / key information |
| --- | --- |
| users | Identities and roles |
| agents | Registered AI agents |
| services | service_id, service_name, environment, current_version, known_good_version (integers, see Section 13), owner, status |
| tools | Tool registry, sensitivity, enabled state |
| policies | Role/action/service/environment authorization rules, including policy-mandated-approval flags (Section 11 Step 2) |
| security_requests | Central request record with request_id, service, environment, decision |
| risk_assessments | Per-request decision evidence: rule_risk_level, ml_risk_level, final_risk_level, decision, reasons, is_production (see Section 11) |
| approval_requests | Pending/approved/rejected review records |
| behavior_events | Raw per-action history feeding feature computation: identity, service, environment, tool, timestamp, outcome — incl. fields needed for the N = 5 sliding window and version_change_delta |
| incidents | Optional security incident/alert tracking |

*Clarification (Revision 6): risk_assessments and behavior_events are intentionally distinct and not redundant. risk_assessments stores the computed decision evidence for one specific request (an output). behavior_events stores raw historical actions used as input to compute the sliding-window and ML features for future requests. Confirm during Phase 2 schema implementation that no columns are duplicated between them beyond the shared request_id/identity foreign keys needed to join them.*

The database stores evidence and state. Application logic makes security decisions; the database itself is not the policy engine.

# 17. API and Communication Design

| Endpoint | Purpose |
| --- | --- |
| POST /api/chat | Developer <-> DevOps Agent |
| POST /api/gateway/tool-request | Agent -> Security Gateway |
| GET /api/approvals | Admin/lead pending approvals |
| POST /api/approvals/:id/approve | Approve request |
| POST /api/approvals/:id/reject | Reject request |
| POST /mcp/tools/execute | Gateway -> internal MCP |
| GET /api/security/events | Security dashboard |
| GET /api/mock/services | Current mock service state |

Example agent-to-gateway request: { "request_id": "REQ-2001", "user_id": "U010", "agent_id": "AG001", "tool": "restart_service", "arguments": { "service": "payment-service", "environment": "production" } }

Example decision: { "request_id": "REQ-2001", "decision": "APPROVAL_REQUIRED", "risk_level": "HIGH", "reason": "production + sensitive operation" }

# 18. End-to-End Execution Examples

- Scenario A — Low-risk read: get_logs on assigned service -> Gateway checks pass -> ALLOW -> MCP executes -> logs returned. No state mutation.
- Scenario B — Authorized state change: assigned staging restart -> ALLOW -> MCP executes -> mock restart count/history changes.
- Scenario C — Unauthorized production action: junior developer attempts production deploy -> policy/role check fails -> BLOCK -> MCP not called -> mock state unchanged.
- Scenario D — Human approval: senior developer requests production deploy -> APPROVAL_REQUIRED -> admin approves -> Gateway revalidates -> MCP executes -> mock current version changes.
- Scenario E — Behavioral anomaly: abnormal restart burst -> rule/ML anomaly -> BLOCK or APPROVAL_REQUIRED -> no execution unless final decision is ALLOW.
- Scenario F — Prompt injection: simulated malicious log content causes the agent to propose an unsafe tool request -> Gateway independently evaluates the structured request -> policy/risk controls contain the action.

# 19. Technology Stack

| Technology | Responsibility |
| --- | --- |
| Next.js + TypeScript | Developer/admin frontend |
| Tailwind CSS | UI styling |
| Python + FastAPI | Backend APIs and Security Gateway |
| Python + LangChain | Autonomous DevOps agent orchestration and structured tool-request generation |
| LLM API | Natural-language understanding and tool-selection reasoning |
| Python MCP | Controlled tool execution |
| Stateful Python mock environment | Simulated services, versions, logs, metrics and state transitions |
| PostgreSQL | Persistent application/security evidence |
| SQLAlchemy | ORM |
| Alembic | Database migrations |
| scikit-learn / Isolation Forest | Behavioral anomaly detection |
| JWT | Authentication |
| Git + GitHub | Version control |

Framework boundary: LangChain is used for the agent layer. The Security Gateway remains custom Python/FastAPI logic so its security decisions are explicit, testable, and independent of the agent framework.

# 20. Project Modules and Scope

| Module | Must-have responsibility |
| --- | --- |
| M1 — DevOps Agent | LangChain + LLM, chat, structured tool requests, Gateway integration |
| M2 — Security Gateway | Authentication, validation, authorization, routing, decision enforcement, audit |
| M3 — Identity & Policy | Roles, service ownership, environment permissions, policies |
| M4 — Risk & ML | Rules, feature extraction, Isolation Forest, anomaly score, decision combination logic |
| M5 — MCP + Mock Environment | Five tools and stateful sandbox |
| M6 — Human Approval | Queue, approve/reject, revalidation |
| M7 — Security Dashboard | Events, decisions, approvals, mock state |
| M8 — Testing & Evaluation | Baseline, attack scenarios, ML, security, state and performance |

No new module was added in Revision 6. All changes in this revision fit inside M2 (Gateway), M4 (Risk & ML) and M8 (Evaluation), the same modules Revision 5 touched.

Out of scope: real cloud infrastructure, real production access, multi-agent orchestration, custom LLM training, deep learning without demonstrated need, reinforcement learning, Kubernetes/Kafka, mobile/voice interfaces, dozens of tools, dynamic ownership reassignment, real-time model retraining.

# 21. Functional Requirements

- FR-01 — Authenticate users and identify roles.
- FR-02 — Agent generates structured DevOps tool requests.
- FR-03 — Every tool request passes through the Security Gateway.
- FR-04 — Gateway validates tool registration, enabled state, arguments, and business constraints.
- FR-05 — Enforce role-based policies.
- FR-06 — Verify service ownership and environment permission.
- FR-07 — Calculate deterministic rule risk.
- FR-08 — Calculate ML anomaly signal from behavioral history within a sliding window of the last N = 5 actions.
- FR-09 — Combine rule risk level and ML risk level using the fixed max-of-two, ML-can-only-escalate logic in Section 11, then apply decision precedence.
- FR-10 — Support ALLOW, BLOCK, APPROVAL_REQUIRED.
- FR-11 — ALLOW causes authorized MCP execution against mock environment.
- FR-12 — BLOCK prevents MCP execution and state mutation.
- FR-13 — APPROVAL_REQUIRED prevents MCP execution until authorized approval and TOCTOU-style revalidation.
- FR-14 — MCP exposes only registered mock tools.
- FR-15 — MCP accepts execution only from the trusted Gateway path.
- FR-16 — Mock environment persists observable state changes.
- FR-17 — Admin/lead can approve or reject pending requests.
- FR-18 — Record requests, risk, approvals, outcomes using request_id.
- FR-19 — Dashboard displays security events and current mock state.
- FR-20 — Support controlled attack scenarios including ownership violation and lateral movement.

# 22. Non-Functional Requirements

- Security — server-side secrets, secure authentication, internal MCP protection, server-side authorization.
- Auditability — decisions traceable by request_id and timestamps.
- Performance — Gateway overhead measured against a direct baseline.
- Reliability — failed tool calls are never recorded as successful executions.
- Privacy — retain only necessary operational/evaluation data.
- Maintainability — logical modularity without unnecessary microservices.
- Usability — clear developer and security-review interfaces.
- Reproducibility — document dataset generation, features, training, thresholds, and evaluation.
- Safety — no execution path reaches real infrastructure.
- State integrity — state-changing tools mutate mock state only after permitted execution.

# 23. Attack and Behavioral Dataset Plan [UPDATED in Revision 6]

The ML dataset is controlled and generated from the prototype/mock environment. It does not require real infrastructure logs, credentials, or sensitive organizational data.

Normal behavior: ordinary log/metric reads, assigned staging restarts, scheduled deployments, approved rollbacks, normal service activity.

Anomalous behavior: restart/deployment bursts, repeated restarts, outside-hours deployment, unusual production activity, rapid rollback after deployment, one identity touching unrelated services quickly, repeated denied attempts, unusual tool sequences, and lateral movement patterns.

Multi-step / staged behavior: sequences where each individual action would pass authorization on its own, but the sequence within the N = 5 sliding window is abnormal — e.g. read logs -> read metrics -> restart -> deploy -> rollback across two services in a short interval. These are generated as a distinct labeled category so E4/E6 evaluation (Section 25) can report detection of staged attacks separately from single-action anomalies.

Isolation Forest is trained primarily on normal behavior and evaluated using held-out normal examples plus simulated anomalous examples. Synthetic traffic generation starts in Semester 1 so the system has meaningful behavior history before ML evaluation.

*Evaluation limitation to document in the final report (new in Revision 6): because both the normal training data and the anomalous test data are synthetically generated by the same team using the same feature schema, precision/recall/F1 figures are likely to be optimistic relative to real-world attacker behavior that was not designed with these features in mind. This is a known, acceptable limitation for an FYP-scale controlled evaluation, but it must be stated explicitly in Section 25/final report rather than presented as evidence of real-world generalization. No design change is required — this is a reporting requirement.*

# 24. ML Training and Evaluation Workflow

Mock activity -> behavior_events -> Feature engineering (incl. N = 5 sliding-window features, version_change_delta, off_hours_flag) -> Normal-behavior training set -> Isolation Forest training -> Validation/calibration -> Held-out normal + simulated anomalies -> Precision / Recall / F1 / FPR -> Integration with Gateway decision engine (Section 11 Step 2–4)

Important: ML training and inference are separate from policy authorization. The model provides an anomaly signal; the Gateway's deterministic security logic remains authoritative.

# 25. Evaluation Plan [UPDATED in Revision 6]

Baseline: DevOps Agent -> MCP/Tools -> Mock Environment, without the Security Gateway. The baseline remains sandboxed.

Proposed system: DevOps Agent -> Security Gateway -> MCP/Tools -> Mock Environment.

*Reframing (new in Revision 6): E1 establishes that a Security Gateway is necessary at all — an unprotected baseline agent will have a near-100% unauthorized execution rate almost by construction. Treat E1 as a sanity/necessity check, not as the project's headline finding. The research contribution rests on E2 (does the ML signal add detection beyond rules alone) and E6 (does the sliding-window/TOCTOU design catch what single-action, non-windowed, non-revalidating approaches miss). Report and present accordingly.*

| Experiment | Comparison | Metrics |
| --- | --- | --- |
| E1 — Authorization/security (necessity check) | Baseline vs Gateway | Unauthorized execution rate, prevention rate |
| E2 — ML contribution | Rules/policy vs Rules/policy + ML | Precision, recall, F1, false-positive rate; report separately for rule-catchable vs ML-only sequence cases (Section 10) |
| E3 — Performance | Direct vs Gateway path | Latency and added overhead |
| E4 — Attack scenarios | Normal vs suspicious/malicious requests | Detection/decision correctness |
| E5 — State enforcement | Allowed vs blocked/pending | Actual state changes vs prevented changes |
| E6 — Multi-step / TOCTOU | Single-action anomaly detection vs sliding-window (N = 5) detection; approval-only vs approval + TOCTOU revalidation | Staged-attack detection rate; approve-then-execute-gap prevention rate |

*New in Revision 6 — E6 trial design: Staged-Attack Detection Rate and Approve-then-Execute Gap Prevention Rate are rates, and a rate requires repeated trials, not a single scripted demo. E6 must run a generated set of staged-attack sequences (target: at least 25–30, varying action order, services touched, and timing within the N = 5 window) and a generated set of approve-then-execute gap scenarios (target: at least 15–20, varying which state field changes and the timing offset between approval and the concurrent change). Demo 9 and Demo 10 (Section 29) remain single-run, hand-picked illustrations for the viva/presentation; they are not the evaluation evidence themselves.*

Primary security metric: Unsafe Action Prevention Rate = unsafe requests prevented before MCP / total unsafe requests.

Production Protection Rate: unauthorized/abnormal production requests correctly blocked or escalated / total such requests.

State Enforcement Accuracy: percentage of state-changing operations whose mock-environment state transition matches the Gateway's final authorization outcome.

# 26. Key Metrics

| Metric | Meaning |
| --- | --- |
| Detection Rate / Recall | Unsafe requests detected |
| Precision | Flagged requests that are unsafe |
| F1 Score | Precision/recall balance |
| False Positive Rate | Normal requests incorrectly flagged |
| Unauthorized Execution Rate | Unsafe actions reaching MCP |
| Unsafe Action Prevention Rate | Unsafe requests prevented before MCP |
| Approval Routing Accuracy | Correct human-review routing |
| Gateway Latency | Time added by Gateway |
| Tool Prevention Rate | Dangerous requests stopped before MCP |
| Production Protection Rate | Unauthorized/abnormal production requests blocked or escalated |
| State Enforcement Accuracy | State changes occur only after permitted execution |
| Staged-Attack Detection Rate | Multi-step sequences (within the N = 5 window), measured across the repeated trial set defined in Section 25, correctly flagged vs. flagged only when evaluated action-by-action |
| Approve-then-Execute Gap Prevention Rate | Approved requests whose later, revalidated state no longer qualifies for execution, measured across the repeated trial set defined in Section 25, correctly re-blocked or re-escalated by TOCTOU revalidation |

# 27. Implementation Order Across Two Semesters [UPDATED in Revision 6]

*Team-size confirmation (Revision 6): the team is 3 members. Given that Semester 1 (Phases 1–12) is entirely deterministic system-building and Semester 2 (Phases 13–18) is ML/evaluation/hardening, a 3-person team can reasonably parallelize within a semester (e.g. one member on mock environment + MCP, one on Gateway/policy, one on agent + frontend/dashboard) without changing phase order or scope. No phases were added, removed, or reordered as a result of this confirmation.*

## Semester 1 — Build the complete deterministic system first

- Phase 1 — Project setup and repository structure.
- Phase 2 — PostgreSQL schema, SQLAlchemy models, Alembic migrations.
- Phase 3 — Stateful mock DevOps environment: 3 services x 2 environments, integer version counters (Section 13).
- Phase 4 — MCP server and five tools; verify state transitions.
- Phase 5 — Skeleton end-to-end path: one tool, ALLOW/BLOCK only, no ML.
- Phase 6 — Python LangChain DevOps agent + LLM integration.
- Phase 7 — Full Security Gateway and request IDs.
- Phase 8 — Authentication, identity, policy, ownership, environment checks.
- Phase 9 — Rule-based risk engine, including the fixed rule_risk_level assignment per condition and the enumerated rule-catchable sequence list (Section 10).
- Phase 10 — Start continuous synthetic behavior-event generation, logging the fields needed later for the N = 5 sliding window, version_change_delta and off_hours_flag so no backfill is needed in Semester 2.
- Phase 11 — Human approval workflow, including TOCTOU-style revalidation before MCP invocation, and implement the Section 11 decision-combination logic end to end (with ml_risk_level defaulted to LOW until Phase 14 calibration).
- Phase 12 — Security dashboard v1.

## Semester 2 — ML, attacks, evaluation and hardening

- Phase 13 — Dataset finalization and ML feature engineering, including the sliding-window, version_change_delta and off_hours_flag features and the multi-step/staged-attack category.
- Phase 14 — Isolation Forest training and calibration, including fixing the ml_risk_level thresholds used in Section 11 Step 2.
- Phase 15 — Decision thresholds and precedence validation, including which HIGH-risk actions map to APPROVAL_REQUIRED vs BLOCK (Section 11 Step 4).
- Phase 16 — Baseline and attack scenarios, including multi-step/staged attacks, generated per the E6 trial-count target (Section 25).
- Phase 17 — Security, ML, state-enforcement and performance evaluation, including E6 (multi-step / TOCTOU) with the repeated-trial design.
- Phase 18 — Hardening, documentation, final demo and reserved buffer weeks.

Reason for early data generation: behavior_events must accumulate during Semester 1 so ML work is not blocked by insufficient data in Semester 2. This includes the fields the Revision 5/6 features depend on.

# 28. Recommended Repository Structure

ai-devops-security-gateway/ — frontend/ (app/, components/, lib/) — backend/ (app/ (agent/ [prompts/, schemas/, langchain_agent/], gateway/ [auth/, validation/, identity/, policy/, risk/, decision/, logging/], mcp/, approvals/, database/, api/), mock_devops_env/ [services/, state/, logs/, metrics/], ml/ [data/, features/, training/, models/, evaluation/]) — tests/ — docs/ — README.md

# 29. Security Demonstration Scenarios [UPDATED in Revision 6]

- Demo 1 — Safe read: get_logs on assigned service -> LOW -> ALLOW -> MCP -> logs returned.
- Demo 2 — Safe state change: assigned staging restart -> ALLOW -> MCP -> mock state changes.
- Demo 3 — Unauthorized production action: junior developer deploys -> BLOCK -> no MCP -> state unchanged.
- Demo 4 — Human approval: senior production deploy -> APPROVAL_REQUIRED -> admin approves -> TOCTOU revalidation -> MCP -> version changes.
- Demo 5 — Abnormal behavior: restart burst -> anomaly -> BLOCK/APPROVAL_REQUIRED.
- Demo 6 — Ownership violation: developer not assigned to service -> BLOCK regardless of ML normality.
- Demo 7 — Lateral movement: one identity touches all three services quickly -> ML anomaly -> escalation/block.
- Demo 8 — Prompt injection: malicious simulated log content manipulates the agent into proposing an unsafe request -> Gateway independently evaluates and contains it.
- Demo 9 — Multi-step / staged attack: an identity performs a sequence of individually-plausible actions (read logs -> read metrics -> restart -> deploy -> rollback across two services) that only looks abnormal within the N = 5 sliding window -> BLOCK/APPROVAL_REQUIRED on the sequence, even though no single action alone would have triggered it. This is one illustrative run for the viva; the evaluation claim comes from the repeated-trial set in Section 25.
- Demo 10 — State-aware anomaly / approve-then-execute gap: a request is approved, the mock environment's state changes before execution (e.g. via a concurrent action), and TOCTOU-style revalidation catches the mismatch and re-blocks or re-escalates instead of executing against stale approval context. This is one illustrative run for the viva; the evaluation claim comes from the repeated-trial set in Section 25.

# 30. Security and Design Decisions to Keep Fixed

- Gateway mandatory for every tool execution.
- MCP is downstream of Gateway.
- Agent has no direct MCP access.
- Browser has no direct MCP access.
- LangChain is used for agent orchestration, not authorization.
- Policy authorization and ML anomaly detection remain separate inputs, combined only via the fixed Section 11 logic.
- Hard authorization/policy failures cannot be overridden by ML.
- final_risk_level = max(rule_risk_level, ml_risk_level); ML can only escalate, never de-escalate (Section 11).
- ALLOW means actual mock execution.
- BLOCK means no MCP call and no state mutation.
- APPROVAL_REQUIRED means no MCP call until approval and TOCTOU-style revalidation.
- Mock environment is stateful and auditable; versions are integer counters, not semver strings.
- Production/high-impact actions may require approval.
- Ownership and environment permission are independently checked, and apply to read tools as well as write tools.
- Unregistered/disabled tools cannot execute.
- Request IDs connect checks, risk, approval, execution and audit.
- Database stores evidence; application logic makes decisions.
- Scope remains one agent, five tools, three services, two environments, three team members.
- All execution targets only the mock environment.
- No claim of complete AI-security or perfect prompt-injection prevention.
- Rate-based evaluation metrics (Staged-Attack Detection Rate, Approve-then-Execute Gap Prevention Rate) are measured over repeated generated trials, not single demonstrations.

# 31. What Not to Overbuild

- Do not build a custom LLM.
- Do not replace LangChain with a custom agent framework unless necessary.
- Do not introduce deep learning without evaluation evidence.
- Do not create many microservices.
- Do not add Kubernetes or Kafka just for appearance.
- Do not build voice or mobile applications.
- Do not create dozens of tools; five carefully designed tools are sufficient.
- Do not integrate real AWS/GCP/Azure/Kubernetes infrastructure.
- Do not connect to real production.
- Do not add dynamic runtime service-ownership reassignment.
- Do not implement multi-agent orchestration.
- Do not implement real-time ML retraining.
- Do not claim perfect prompt-injection detection.
- Do not expand the sliding-window / state-aware features beyond N = 5, version_change_delta and off_hours_flag without new evaluation evidence that more features help.
- Do not change the Section 11 decision-combination logic (max-of-two, ML-can-only-escalate) mid-project without documented evaluation evidence that a different combination performs better — changing it late would invalidate earlier E2/E6 results.

# 32. Final Scope Snapshot

| Area | Final decision |
| --- | --- |
| Project | Security Gateway for Autonomous DevOps AI Agents |
| Team | 3 members |
| Agent | One autonomous DevOps AI agent |
| Agent framework | Python + LangChain + LLM |
| Tools | get_logs, get_metrics, restart_service, rollback_deployment, deploy_service |
| Environment | Stateful mock/sandbox DevOps environment |
| Services | 3 x 2: auth-service, payment-service, notification-service x staging/production |
| Roles | junior_developer, senior_developer, admin/SRE |
| Ownership | Service ownership + environment permission, applied to all five tools including reads |
| Security | Authentication + validation + authorization + policy + risk + decision + audit + TOCTOU-style revalidation |
| Decision logic | final_risk_level = max(rule_risk_level, ml_risk_level); ML can only escalate (Section 11) |
| ML | Isolation Forest behavioral anomaly detection over an N = 5 sliding window, plus version_change_delta (integer-based) and off_hours_flag |
| Human control | Admin/lead approval |
| Database | PostgreSQL |
| Backend | Python + FastAPI |
| Frontend | Next.js + TypeScript + Tailwind |
| Execution | MCP only after final authorization decision |
| Evaluation | Security + ML + latency + state enforcement + baseline (necessity check) + multi-step/TOCTOU (E6, repeated-trial design) |
| Primary contribution | Prevent/contain unsafe AI-agent DevOps actions, especially production actions, via combined authorization + behavioral anomaly control |

# 33. Implementation Readiness Checklist [UPDATED in Revision 6]

- DevOps-only project scope finalized.
- Customer-support terminology removed from the final project definition.
- Agent framework explicitly selected: Python + LangChain + LLM.
- LangChain's role separated from the Security Gateway's role.
- Browser -> Agent -> Gateway -> MCP trust boundary finalized.
- Decision precedence finalized, including the explicit rule-risk/ML-risk combination formula (Section 11).
- ALLOW/BLOCK/APPROVAL_REQUIRED semantics finalized.
- Stateful mock environment finalized, including integer version representation.
- 3 services x 2 environments finalized.
- Five MCP tools finalized; ownership check confirmed to apply to read tools as well as write tools.
- Database and audit evidence finalized.
- Identity, ownership, environment and policy checks finalized.
- Rule risk and ML anomaly responsibilities separated, including the rule-vs-ML sequence-detection division (Section 10).
- Isolation Forest selected.
- Human approval and TOCTOU-style revalidation finalized.
- Functional and non-functional requirements finalized.
- Threat/attack scenarios finalized, including multi-step/staged attacks and the approve-then-execute gap.
- Synthetic behavior-data generation starts in Semester 1, including fields needed for Revision 5/6 features.
- Evaluation metrics and baseline finalized, including E6 (multi-step / TOCTOU) with a repeated-trial design and E1 reframed as a necessity check.
- Implementation order finalized (phases unchanged from Revision 4/5; team size of 3 confirmed compatible).
- Out-of-scope boundaries finalized.
- No real infrastructure connection permitted.
- Synthetic-anomaly evaluation limitation documented for the final report.

# 34. Final Project Definition [UPDATED in Revision 6]

The final system is an autonomous DevOps AI agent implemented in Python using LangChain and an LLM, protected by a custom Security Gateway. The agent understands developer requests and generates structured DevOps tool requests. It never directly executes infrastructure tools. The Gateway independently authenticates, validates, checks role/service ownership/environment policy, evaluates deterministic and behavioral risk over a sliding window of the most recent N = 5 actions per identity/service/environment, and decides ALLOW, BLOCK, or APPROVAL_REQUIRED using a fixed combination rule: the final risk level is the higher of the deterministic rule-risk level and the ML anomaly-risk level, so behavioral ML can escalate a decision but never grant permission a policy denies.

Only an ALLOW decision, or an approval request that has been approved and then passed TOCTOU-style revalidation immediately before execution, can reach the internal MCP server. MCP performs the operation against a stateful mock DevOps environment. Therefore, safe approved state-changing actions visibly change the simulated environment, while blocked or pending actions cannot mutate it.

The project is evaluated against a sandboxed baseline (treated as a necessity check, not the headline result) using security, ML, latency, attack-detection, state-enforcement, and multi-step/TOCTOU metrics measured over repeated generated trials. The main research contribution is not the chatbot or LangChain itself; it is the security control architecture around autonomous DevOps tool execution — specifically the explicit, defensible combination of policy authorization and sliding-window behavioral anomaly detection, evaluated with a stated division of labor between rule-based and ML-based sequence detection, and including protection against staged, multi-step behavior and the approve-then-execute gap, without expanding the project's agent, tool, service, role, or team scope.
