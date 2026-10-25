import logging
import uuid
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, Optional
import aiosmtplib
from src.config import settings

logger = logging.getLogger(__name__)


def mask_email(email: Optional[str]) -> str:
    """Safely mask an email address for structured logging (e.g., a***n@fundamics.in)."""
    if not email or "@" not in email:
        return "<invalid-email>"
    parts = email.split("@", 1)
    name, domain = parts[0], parts[1]
    if len(name) <= 2:
        masked_name = name[0] + "*"
    else:
        masked_name = name[0] + "*" * (len(name) - 2) + name[-1]
    return f"{masked_name}@{domain}"


_UNSET = object()


class EmailService:
    """
    Reusable asynchronous email service providing transactional email delivery
    via Hostinger SMTP (or standard SMTP servers) using aiosmtplib.
    Configured via environment variables with safe error handling and sanitization.
    Supports port 587 (STARTTLS) and port 465 (direct SSL/TLS).
    """

    def __init__(
        self,
        host: Any = _UNSET,
        port: Any = _UNSET,
        use_tls: Any = _UNSET,
        username: Any = _UNSET,
        password: Any = _UNSET,
        mail_from: Any = _UNSET,
        mail_from_name: Any = _UNSET,
        timeout: float = 15.0,
    ):
        self._host = host
        self._port = port
        self._use_tls = use_tls
        self._username = username
        self._password = password
        self._mail_from = mail_from
        self._mail_from_name = mail_from_name
        self.timeout = timeout

    @property
    def host(self) -> str:
        return settings.SMTP_HOST if self._host is _UNSET else self._host

    @host.setter
    def host(self, value: str):
        self._host = value

    @property
    def port(self) -> int:
        val = settings.SMTP_PORT if self._port is _UNSET else self._port
        return int(val) if val is not None else 587

    @port.setter
    def port(self, value: int):
        self._port = int(value)

    @property
    def use_tls(self) -> bool:
        val = settings.SMTP_USE_TLS if self._use_tls is _UNSET else self._use_tls
        return bool(val)

    @use_tls.setter
    def use_tls(self, value: bool):
        self._use_tls = bool(value)

    @property
    def username(self) -> Optional[str]:
        return settings.SMTP_USERNAME if self._username is _UNSET else self._username

    @username.setter
    def username(self, value: Optional[str]):
        self._username = value

    @property
    def password(self) -> Optional[str]:
        return settings.SMTP_PASSWORD if self._password is _UNSET else self._password

    @password.setter
    def password(self, value: Optional[str]):
        self._password = value

    @property
    def mail_from(self) -> str:
        return settings.MAIL_FROM if self._mail_from is _UNSET else self._mail_from

    @mail_from.setter
    def mail_from(self, value: str):
        self._mail_from = value

    @property
    def mail_from_name(self) -> str:
        return settings.MAIL_FROM_NAME if self._mail_from_name is _UNSET else self._mail_from_name

    @mail_from_name.setter
    def mail_from_name(self, value: str):
        self._mail_from_name = value

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email asynchronously via SMTP.
        If SMTP credentials are not configured or notifications are disabled,
        operates in mock/dev mode to prevent crashing.
        Never leaks passwords or raw credentials in logs or errors.
        """
        if not settings.NOTIFICATIONS_ENABLED:
            logger.info("[NOTIFICATIONS_DISABLED] Globally disabled; skipping email to %s", mask_email(to_email))
            return {
                "success": False,
                "mocked": False,
                "disabled": True,
                "message_id": f"disabled-{uuid.uuid4()}",
                "provider": "disabled",
            }

        if not self.username or not self.password:
            logger.info(
                "[MOCK SMTP] No SMTP credentials configured. Mocking dispatch to %s | Subject: %s",
                mask_email(to_email),
                subject,
            )
            return {
                "success": True,
                "mocked": True,
                "message_id": f"mock-smtp-{uuid.uuid4()}",
                "provider": "mock-smtp",
            }

        # Build MIME EmailMessage
        message = EmailMessage()
        from_header = formataddr((self.mail_from_name, self.mail_from)) if self.mail_from_name else self.mail_from
        message["From"] = from_header
        message["To"] = to_email
        message["Subject"] = subject

        plain_text = text_content or "Please view this email in an HTML-compatible email client."
        message.set_content(plain_text)
        if html_content:
            message.add_alternative(html_content, subtype="html")

        # Determine TLS / SSL connection settings:
        # Port 465 is direct SSL/TLS; Port 587 (or explicit use_tls) uses STARTTLS
        if self.port == 465:
            use_direct_tls = True
            use_starttls = False
        elif self.port == 587 or self.use_tls:
            use_direct_tls = False
            use_starttls = True
        else:
            use_direct_tls = False
            use_starttls = False

        logger.info(
            "[SMTP DISPATCH] Connecting to %s:%s (direct_tls=%s, starttls=%s, mail_from=%s) for recipient=%s | Subject: '%s'",
            self.host,
            self.port,
            use_direct_tls,
            use_starttls,
            self.mail_from,
            mask_email(to_email),
            subject,
        )

        try:
            client_kwargs: Dict[str, Any] = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "password": self.password,
                "timeout": self.timeout,
                "use_tls": use_direct_tls,
                "start_tls": use_starttls,
            }

            await aiosmtplib.send(message, **client_kwargs)
            message_id = f"smtp-{uuid.uuid4()}"
            logger.info(
                "[SMTP SUCCESS] Dispatched email via %s:%s to %s (msg_id: %s)",
                self.host,
                self.port,
                mask_email(to_email),
                message_id,
            )
            return {
                "success": True,
                "mocked": False,
                "message_id": message_id,
                "provider": "hostinger-smtp",
            }
        except aiosmtplib.SMTPConnectTimeoutError as exc:
            logger.error(
                "[SMTP_ERROR:CONNECT_TIMEOUT] Connection timed out connecting to %s:%s (timeout=%ss). "
                "Cloud platforms (e.g. Render) frequently block port 465; ensure SMTP_PORT=587 (STARTTLS) is used. Recipient: %s",
                self.host,
                self.port,
                self.timeout,
                mask_email(to_email),
            )
            return {
                "success": False,
                "mocked": False,
                "error": "SMTP Error: SMTPConnectTimeoutError",
                "failure_category": "TCP_CONNECT_TIMEOUT_OR_BLOCKED_PORT",
                "provider": "hostinger-smtp",
            }
        except aiosmtplib.SMTPConnectError as exc:
            logger.error(
                "[SMTP_ERROR:CONNECT_FAILED] TCP connection to %s:%s failed. Recipient: %s. Error: %s",
                self.host,
                self.port,
                mask_email(to_email),
                type(exc).__name__,
            )
            return {
                "success": False,
                "mocked": False,
                "error": f"SMTP Error: {type(exc).__name__}",
                "failure_category": "TCP_CONNECT_FAILED",
                "provider": "hostinger-smtp",
            }
        except aiosmtplib.SMTPAuthenticationError as exc:
            logger.error(
                "[SMTP_ERROR:AUTH_FAILED] SMTP Authentication rejected for username '%s' at %s:%s",
                self.username,
                self.host,
                self.port,
            )
            return {
                "success": False,
                "mocked": False,
                "error": "SMTP Error: SMTPAuthenticationError",
                "failure_category": "AUTHENTICATION_FAILED",
                "provider": "hostinger-smtp",
            }
        except aiosmtplib.SMTPSenderRefused as exc:
            logger.error(
                "[SMTP_ERROR:SENDER_REFUSED] Sender address '%s' was rejected by %s:%s. Ensure MAIL_FROM matches authenticated mailbox '%s'.",
                self.mail_from,
                self.host,
                self.port,
                self.username,
            )
            return {
                "success": False,
                "mocked": False,
                "error": f"SMTP Error: SMTPSenderRefused",
                "failure_category": "SENDER_REJECTED",
                "provider": "hostinger-smtp",
            }
        except aiosmtplib.SMTPRecipientRefused as exc:
            logger.error(
                "[SMTP_ERROR:RECIPIENT_REFUSED] Recipient '%s' was rejected by server.",
                mask_email(to_email),
            )
            return {
                "success": False,
                "mocked": False,
                "error": "SMTP Error: SMTPRecipientRefused",
                "failure_category": "RECIPIENT_REJECTED",
                "provider": "hostinger-smtp",
            }
        except aiosmtplib.SMTPException as exc:
            logger.error(
                "[SMTP_ERROR:PROTOCOL] SMTP transmission failed for recipient %s [Error: %s: %s]",
                mask_email(to_email),
                type(exc).__name__,
                exc.message if hasattr(exc, "message") else str(exc),
            )
            return {
                "success": False,
                "mocked": False,
                "error": f"SMTP Error: {type(exc).__name__}",
                "failure_category": "SMTP_PROTOCOL_ERROR",
                "provider": "hostinger-smtp",
            }
        except Exception as exc:
            logger.error(
                "[SMTP_ERROR:UNEXPECTED] Unexpected failure during email dispatch to %s [Error: %s]",
                mask_email(to_email),
                type(exc).__name__,
            )
            return {
                "success": False,
                "mocked": False,
                "error": f"Email dispatch failed: {type(exc).__name__}",
                "failure_category": "UNEXPECTED_ERROR",
                "provider": "hostinger-smtp",
            }

    async def send_verification_email(
        self,
        to_email: str,
        user_name: str,
        token: str,
    ) -> Dict[str, Any]:
        """Send account email verification link and instructions."""
        base_url = settings.FRONTEND_BASE_URL.rstrip("/")
        verification_link = f"{base_url}/verify-email?token={token}"
        expiry_hours = settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS

        subject = "FUNDAMICS LMS — Verify Your Email Address"
        text_content = (
            f"Hello {user_name},\n\n"
            f"Thank you for registering with FUNDAMICS Coaching Centre LMS.\n"
            f"Please verify your email address by visiting the following link:\n"
            f"{verification_link}\n\n"
            f"Or enter your verification token: {token}\n\n"
            f"This link and token will expire in {expiry_hours} hours.\n"
            f"If you did not create an account, please ignore this email.\n\n"
            f"Regards,\nFUNDAMICS Education Team"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Verify Your Email</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
                .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0; }}
                .header {{ background: #1e3a8a; padding: 28px 32px; text-align: center; }}
                .header h1 {{ color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
                .content {{ padding: 32px; }}
                .greeting {{ font-size: 17px; font-weight: 600; margin-bottom: 16px; color: #0f172a; }}
                .body-text {{ font-size: 15px; line-height: 1.6; color: #334155; margin-bottom: 24px; }}
                .button-container {{ text-align: center; margin: 32px 0; }}
                .button {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2); }}
                .token-box {{ background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; text-align: center; margin: 24px 0; }}
                .token-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #64748b; margin-bottom: 6px; font-weight: 600; }}
                .token-code {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 18px; font-weight: 700; color: #0f172a; word-break: break-all; }}
                .footer {{ background: #f8fafc; padding: 20px 32px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #64748b; line-height: 1.5; }}
                .fallback-url {{ font-size: 12px; color: #64748b; word-break: break-all; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>FUNDAMICS COACHING LMS</h1>
                </div>
                <div class="content">
                    <div class="greeting">Hello {user_name},</div>
                    <p class="body-text">
                        Welcome to FUNDAMICS LMS. Please verify your email address to complete your registration and activate access to your courses, batches, and academic schedules.
                    </p>
                    <div class="button-container">
                        <a href="{verification_link}" class="button" target="_blank">Verify Email Address</a>
                    </div>
                    <div class="token-box">
                        <div class="token-label">Or use your verification token:</div>
                        <div class="token-code">{token}</div>
                    </div>
                    <p class="body-text" style="font-size: 13px; color: #64748b;">
                        This verification link and token will expire in <strong>{expiry_hours} hours</strong>. If you did not create this account, you can safely ignore this email.
                    </p>
                    <div class="fallback-url">
                        If the button above does not work, copy and paste this URL into your browser:<br>
                        <a href="{verification_link}" style="color: #2563eb;">{verification_link}</a>
                    </div>
                </div>
                <div class="footer">
                    &copy; FUNDAMICS Coaching Centre Management ERP. All rights reserved.
                </div>
            </div>
        </body>
        </html>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        token: str,
    ) -> Dict[str, Any]:
        """Send password reset link and single-use security token."""
        base_url = settings.FRONTEND_BASE_URL.rstrip("/")
        reset_link = f"{base_url}/reset-password?token={token}"
        expiry_minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES

        subject = "FUNDAMICS LMS — Password Reset Instructions"
        text_content = (
            f"Hello {user_name},\n\n"
            f"We received a request to reset your password for FUNDAMICS LMS.\n"
            f"To set a new password, please visit the following link:\n"
            f"{reset_link}\n\n"
            f"Or enter your reset token: {token}\n\n"
            f"This link and token are valid for {expiry_minutes} minutes only.\n"
            f"If you did not request a password reset, please disregard this email. Your password will remain unchanged.\n\n"
            f"Regards,\nFUNDAMICS Security Team"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Reset Your Password</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
                .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0; }}
                .header {{ background: #0f172a; padding: 28px 32px; text-align: center; }}
                .header h1 {{ color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
                .content {{ padding: 32px; }}
                .greeting {{ font-size: 17px; font-weight: 600; margin-bottom: 16px; color: #0f172a; }}
                .body-text {{ font-size: 15px; line-height: 1.6; color: #334155; margin-bottom: 24px; }}
                .button-container {{ text-align: center; margin: 32px 0; }}
                .button {{ display: inline-block; background-color: #dc2626; color: #ffffff !important; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600; box-shadow: 0 2px 4px rgba(220, 38, 38, 0.2); }}
                .token-box {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 16px; text-align: center; margin: 24px 0; }}
                .token-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #92400e; margin-bottom: 6px; font-weight: 600; }}
                .token-code {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 18px; font-weight: 700; color: #78350f; word-break: break-all; }}
                .footer {{ background: #f8fafc; padding: 20px 32px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #64748b; line-height: 1.5; }}
                .fallback-url {{ font-size: 12px; color: #64748b; word-break: break-all; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>FUNDAMICS COACHING LMS</h1>
                </div>
                <div class="content">
                    <div class="greeting">Hello {user_name},</div>
                    <p class="body-text">
                        We received a request to reset your password for your FUNDAMICS LMS account. Click the button below to choose a new, secure password:
                    </p>
                    <div class="button-container">
                        <a href="{reset_link}" class="button" target="_blank">Reset Password</a>
                    </div>
                    <div class="token-box">
                        <div class="token-label">Or use your single-use reset token:</div>
                        <div class="token-code">{token}</div>
                    </div>
                    <p class="body-text" style="font-size: 13px; color: #64748b;">
                        This token will expire in <strong>{expiry_minutes} minutes</strong> and can only be used once. If you did not request this change, please ignore this email and your password will remain unchanged.
                    </p>
                    <div class="fallback-url">
                        If the button does not work, copy and paste this URL into your browser:<br>
                        <a href="{reset_link}" style="color: #2563eb;">{reset_link}</a>
                    </div>
                </div>
                <div class="footer">
                    &copy; FUNDAMICS Coaching Centre Management ERP. All rights reserved.
                </div>
            </div>
        </body>
        </html>
        """
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )


email_service = EmailService()
