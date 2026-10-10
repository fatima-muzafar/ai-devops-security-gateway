"""
Phase 9 rule-risk constants (decisions.md #53, #56, #57, #62).

ONE module on purpose: these numbers are not from the planning doc and are uncalibrated.
Freeze them before Phase 16 data collection -- changing them afterwards invalidates E2.
"""
from datetime import timedelta

# #57 repeated denials: >= DENIAL_THRESHOLD Ownership/Policy BLOCKs in the window.
DENIAL_THRESHOLD = 3
DENIAL_WINDOW = timedelta(minutes=10)

# #56 S1 deploy -> rollback on one (user, service) row.
S1_WINDOW = timedelta(minutes=10)

# #56 / #62 S2 consecutive non-executed run across all of the user's requests.
S2_RUN_LENGTH = 3
S2_WINDOW = timedelta(minutes=10)

# #56 S3 identical destructive action: >= S3_PRIOR_EXECUTED prior executed, so the
# next one (the incoming request) is escalated.
S3_PRIOR_EXECUTED = 2
S3_WINDOW = timedelta(minutes=5)