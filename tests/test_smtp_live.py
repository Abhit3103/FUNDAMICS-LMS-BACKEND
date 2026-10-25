# -*- coding: utf-8 -*-
"""
Live SMTP connectivity and delivery tests for FUNDAMICS LMS backend.
Sends real emails via Hostinger SMTP using credentials from .env.

Usage (from project root with venv activated):
    pytest tests/test_smtp_live.py -v -s
OR run directly:
    python tests/test_smtp_live.py
"""

import asyncio
import sys
import os

# Ensure src is importable when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import aiosmtplib
import pytest

from src.config import settings
from src.services.email_service import EmailService


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def banner(msg: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print('=' * 60)


# ---------------------------------------------------------------------------
# Config sanity check (run before any network test)
# ---------------------------------------------------------------------------

def test_smtp_config_loaded():
    """Verify that SMTP settings are loaded from .env and are non-empty."""
    banner("SMTP Config Check")
    print(f"  SMTP_HOST      : {settings.SMTP_HOST}")
    print(f"  SMTP_PORT      : {settings.SMTP_PORT}")
    print(f"  SMTP_USE_TLS   : {settings.SMTP_USE_TLS}")
    print(f"  SMTP_USERNAME  : {settings.SMTP_USERNAME}")
    pw = settings.SMTP_PASSWORD or ""
    print(f"  SMTP_PASSWORD  : {'*' * len(pw)} ({len(pw)} chars)")
    print(f"  MAIL_FROM      : {settings.MAIL_FROM}")
    print(f"  MAIL_FROM_NAME : {settings.MAIL_FROM_NAME}")

    assert settings.SMTP_HOST, "SMTP_HOST must not be empty"
    assert settings.SMTP_PORT in (465, 587), f"Unexpected SMTP_PORT: {settings.SMTP_PORT}"
    assert settings.SMTP_USERNAME, (
        "SMTP_USERNAME is empty - set it in .env before running live tests"
    )
    assert settings.SMTP_PASSWORD, (
        "SMTP_PASSWORD is empty - set it in .env before running live tests"
    )
    print("\n  [OK]  Config OK")


# ---------------------------------------------------------------------------
# 1. Raw aiosmtplib connectivity (EHLO + AUTH only, no message sent)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smtp_raw_connection():
    """
    Open a raw SSL connection to the SMTP server, authenticate, then quit.
    Verifies credentials without sending any email.
    """
    banner("Raw SMTP Connection + Auth Test")

    smtp = aiosmtplib.SMTP(
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        use_tls=(settings.SMTP_PORT == 465),
        start_tls=False,
        timeout=20,
    )

    try:
        await smtp.connect()
        print(f"  Connected to {settings.SMTP_HOST}:{settings.SMTP_PORT}")

        if settings.SMTP_PORT == 587:
            await smtp.starttls()
            print("  STARTTLS upgrade successful")

        await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        print(f"  Authenticated as {settings.SMTP_USERNAME}")

        await smtp.quit()
        print("  [OK]  Connection test PASSED")

    except aiosmtplib.SMTPAuthenticationError as e:
        pytest.fail(
            f"[FAIL]  Authentication failed - check SMTP_USERNAME / SMTP_PASSWORD in .env\n"
            f"    Server said: {e}"
        )
    except aiosmtplib.SMTPConnectError as e:
        pytest.fail(
            f"[FAIL]  Could not connect to {settings.SMTP_HOST}:{settings.SMTP_PORT}\n"
            f"    Error: {e}\n"
            f"    Check firewall / VPN / host reachability."
        )
    except Exception as e:
        pytest.fail(f"[FAIL]  Unexpected SMTP error: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 2. Full email delivery via EmailService.send_email
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_email_service_live_delivery():
    """
    Send a real plain-text + HTML email via EmailService.send_email.
    To address defaults to SMTP_USERNAME (inbox round-trip check).
    Override by setting TEST_RECIPIENT_EMAIL env var.
    """
    banner("EmailService — Live Delivery Test")

    recipient = os.getenv("TEST_RECIPIENT_EMAIL", settings.SMTP_USERNAME)
    print(f"  Sending to: {recipient}")

    svc = EmailService()
    result = await svc.send_email(
        to_email=recipient,
        subject="[FUNDAMICS LMS] SMTP Live Test",
        html_content=(
            "<h2 style='color:#1e3a8a'>FUNDAMICS SMTP Live Test</h2>"
            "<p>This is an automated live delivery test from <code>test_smtp_live.py</code>.</p>"
            "<p>If you are reading this, SMTP delivery is working correctly.</p>"
        ),
        text_content=(
            "FUNDAMICS SMTP Live Test\n\n"
            "This is an automated live delivery test from test_smtp_live.py.\n"
            "If you are reading this, SMTP delivery is working correctly."
        ),
    )

    print(f"  Result: {result}")

    assert result["success"] is True, (
        f"[FAIL]  send_email returned success=False\n    Details: {result}"
    )
    assert result.get("provider") == "hostinger-smtp", (
        f"Expected provider=hostinger-smtp, got: {result.get('provider')}\n"
        "  -> SMTP_USERNAME/SMTP_PASSWORD may be unset, triggering mock mode."
    )
    print(f"  message_id : {result['message_id']}")
    print(f"  [OK]  Live delivery PASSED - check inbox at {recipient}")


# ---------------------------------------------------------------------------
# 3. Verification email template
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_verification_email_live():
    """Send a real verification email with the full HTML template."""
    banner("send_verification_email — Live Template Test")

    recipient = os.getenv("TEST_RECIPIENT_EMAIL", settings.SMTP_USERNAME)
    print(f"  Sending to: {recipient}")

    svc = EmailService()
    result = await svc.send_verification_email(
        to_email=recipient,
        user_name="Test Student",
        token="LIVE-TEST-TOKEN-ABC123XYZ",
    )

    print(f"  Result: {result}")
    assert result["success"] is True, f"[FAIL]  Verification email failed: {result}"
    print(f"  [OK]  Verification email sent - message_id: {result['message_id']}")


# ---------------------------------------------------------------------------
# 4. Password reset email template
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_password_reset_email_live():
    """Send a real password-reset email with the full HTML template."""
    banner("send_password_reset_email — Live Template Test")

    recipient = os.getenv("TEST_RECIPIENT_EMAIL", settings.SMTP_USERNAME)
    print(f"  Sending to: {recipient}")

    svc = EmailService()
    result = await svc.send_password_reset_email(
        to_email=recipient,
        user_name="Test Student",
        token="LIVE-RESET-TOKEN-XYZ789ABC",
    )

    print(f"  Result: {result}")
    assert result["success"] is True, f"[FAIL]  Password reset email failed: {result}"
    print(f"  [OK]  Password reset email sent - message_id: {result['message_id']}")


# ---------------------------------------------------------------------------
# Direct-run entry point (no pytest needed)
# ---------------------------------------------------------------------------

async def _run_all():
    print("\nRunning all SMTP live tests...\n")

    test_smtp_config_loaded()

    tests = [
        test_smtp_raw_connection,
        test_email_service_live_delivery,
        test_send_verification_email_live,
        test_send_password_reset_email_live,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            await t()
            passed += 1
        except Exception as e:
            print(f"\n  FAILED {t.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print('=' * 60)
    return failed


if __name__ == "__main__":
    exit_code = asyncio.run(_run_all())
    sys.exit(exit_code)
