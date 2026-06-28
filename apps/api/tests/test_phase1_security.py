from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from auth.dependencies import _authenticate_user
from auth.service import create_access_token, decode_token
from db.rls import apply_rls_policies


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, user, membership):
        self.results = iter([_Result(user), _Result(membership)])

    async def execute(self, _statement):
        return next(self.results)


class _CaptureConnection:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))


@pytest.mark.asyncio
async def test_rls_policy_is_fail_closed_and_checks_writes():
    connection = _CaptureConnection()
    await apply_rls_policies(connection)
    policy_sql = "\n".join(connection.statements)

    assert "FORCE ROW LEVEL SECURITY" in policy_sql
    assert "WITH CHECK" in policy_sql
    assert "current_setting('app.current_firm_id', true) = ''" not in policy_sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("totp_enabled", "totp_ok", "expected_code"),
    [
        (False, False, "MFA_SETUP_REQUIRED"),
        (True, False, "MFA_REQUIRED"),
    ],
)
async def test_owner_access_is_blocked_until_mfa(totp_enabled, totp_ok, expected_code):
    user = SimpleNamespace(id="user-1", email_verified=True, totp_enabled=totp_enabled)
    membership = SimpleNamespace(firm_id="firm-1", role="owner")
    db = _FakeDb(user, membership)
    credentials = SimpleNamespace(credentials="pending-token")
    payload = {"type": "access", "sub": user.id, "firm_id": membership.firm_id, "totp_ok": totp_ok}

    with (
        patch("auth.dependencies.decode_token", return_value=payload),
        patch("auth.dependencies.set_rls_context", new=AsyncMock()),
        pytest.raises(HTTPException) as raised,
    ):
        await _authenticate_user(credentials, db, enforce_mfa=True)

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == expected_code


def test_validated_access_token_carries_totp_claim():
    token = create_access_token("user-1", "firm-1", totp_ok=True)
    assert decode_token(token)["totp_ok"] is True
