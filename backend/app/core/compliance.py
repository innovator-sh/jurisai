"""Constants shared by the DPDP / CERT-In compliance features (Sprint 6).

CONSENT_VERSION identifies the exact text of the privacy notice a user agreed
to at signup. Bump it whenever the notice in templates/privacy.html changes
materially, so stored consents stay attributable to the wording they saw.
"""

from typing import Literal

CONSENT_VERSION = "2026-10-v1"

Role = Literal["citizen", "lawyer", "police"]

# CERT-In Directions 2022: security logs retained for 180 days, in India.
SECURITY_LOG_RETENTION_DAYS = 180
