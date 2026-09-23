import enum


class Role(str, enum.Enum):
    JUNIOR_DEVELOPER = "junior_developer"
    SENIOR_DEVELOPER = "senior_developer"
    ADMIN = "admin"


class Environment(str, enum.Enum):
    STAGING = "staging"
    PRODUCTION = "production"


class Sensitivity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Decision(str, enum.Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EventOutcome(str, enum.Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    PENDING = "pending"
