"""Smoke tests for LifePass productionization extensions.

Run from project root:
    python tests/verify_production_extensions.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.application_review import create_application_case, list_application_cases, review_application_case
from core.auth_accounts import authenticate_user, get_user_by_token, register_user
from core.models import UserProfile
from core.notification_delivery import dispatch_pending_notifications, enqueue_notifications
from core.policy_store import evidence_links_for_benefits, list_policy_catalog, policy_store_summary, sync_source_to_store
from core.privacy_audit import audit_profile_access, record_consent, redact_profile_payload


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        policy_db = base / "policy.sqlite3"
        result = sync_source_to_store("local_city", path=policy_db)
        assert result["stored_count"] >= 1
        assert policy_store_summary(path=policy_db)["active"] >= 1
        policies = list_policy_catalog(path=policy_db)
        assert evidence_links_for_benefits([policies[0]["id"]], path=policy_db)

        auth_db = base / "auth.sqlite3"
        register_user("tester@example.com", "password123", "Tester", "counselor", path=auth_db)
        login = authenticate_user("tester@example.com", "password123", path=auth_db)
        assert get_user_by_token(login["access_token"], path=auth_db)["email"] == "tester@example.com"

        profile = UserProfile()
        case_db = base / "case.sqlite3"
        case = create_application_case(profile, policies[:1], submit=True, path=case_db)
        reviewed = review_application_case(case["case_id"], decision="approved", reviewer_email="reviewer@example.com", path=case_db)
        assert reviewed["status"] == "approved"
        assert list_application_cases(path=case_db)

        notification_db = base / "notification.sqlite3"
        enqueue_notifications([{"channel": "app", "trigger": "deadline", "message": "demo"}], path=notification_db)
        assert dispatch_pending_notifications(path=notification_db, dry_run=True)["processed"] == 1

        privacy_db = base / "privacy.sqlite3"
        consent = record_consent({"email": "tester@example.com"}, purpose="eligibility_screening", granted=True, scope=["age"], path=privacy_db)
        access = audit_profile_access(actor_id="tester", role="counselor", action="read:assigned", purpose="eligibility_screening", subject="tester", fields=["age"], path=privacy_db)
        redacted = redact_profile_payload({"age": 27, "email": "tester@example.com", "monthly_income": 0})
        assert consent["granted"] is True
        assert access["ok"] is True
        assert redacted["email"] == "[REDACTED]"
    print("ALL PRODUCTION EXTENSION CHECKS PASSED")


if __name__ == "__main__":
    main()
