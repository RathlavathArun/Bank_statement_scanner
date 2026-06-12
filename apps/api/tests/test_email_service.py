import os

import pytest

from auth import email_service
from core.config import settings


@pytest.mark.asyncio
async def test_ses_provider_does_not_require_smtp_password(monkeypatch):
    calls = []

    async def fake_send_via_ses(to_email, subject, plain_text, html_body):
        calls.append((to_email, subject, plain_text, html_body))
        return True

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "ses")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "verified@example.com")
    monkeypatch.setattr(email_service, "_send_via_ses", fake_send_via_ses)
    monkeypatch.delenv("ECS_CONTAINER_METADATA_URI", raising=False)
    monkeypatch.delenv("ECS_CONTAINER_METADATA_URI_V4", raising=False)
    monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)

    assert await email_service.send_otp_email("user@example.com", "123456", "verify_email") is True
    assert calls
    assert calls[0][0] == "user@example.com"


@pytest.mark.asyncio
async def test_aws_runtime_uses_ses(monkeypatch):
    calls = []

    async def fake_send_via_ses(to_email, subject, plain_text, html_body):
        calls.append(to_email)
        return True

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "verified@example.com")
    monkeypatch.setattr(email_service, "_send_via_ses", fake_send_via_ses)
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")

    try:
        assert await email_service.send_otp_email("user@example.com", "123456", "reset_password") is True
        assert calls == ["user@example.com"]
    finally:
        os.environ.pop("AWS_EXECUTION_ENV", None)
