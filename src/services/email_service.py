import logging
import uuid
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, Optional
import aiosmtplib
from src.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Reusable asynchronous email service providing transactional email delivery
    via Hostinger SMTP (or standard SMTP servers) using aiosmtplib.
    Configured via environment variables with safe error handling and sanitization.
    """

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.use_tls = settings.SMTP_USE_TLS
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.mail_from = settings.MAIL_FROM
        self.mail_from_name = settings.MAIL_FROM_NAME
        self.timeout = 15.0

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
            logger.info("Notifications are globally disabled; suppressing email to %s", to_email)
            return {"success": True, "message_id": f"disabled-{uuid.uuid4()}", "provider": "disabled"}

        if not self.username or not self.password:
            logger.info(
                "[DEV/MOCK SMTP] No SMTP credentials configured. Mocking dispatch to %s | Subject: %s",
                to_email,
                subject,
            )
            return {
                "success": True,
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

        # Determine TLS / SSL connection settings
        # Port 465 is standard SMTPS (direct SSL/TLS); port 587 is standard STARTTLS
        is_direct_ssl = (self.port == 465) or (self.use_tls and self.port != 587)
        is_starttls = (self.port == 587) or (self.use_tls and not is_direct_ssl)

        try:
            client_kwargs: Dict[str, Any] = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "password": self.password,
                "timeout": self.timeout,
            }
            if is_direct_ssl:
                client_kwargs["use_tls"] = True
                client_kwargs["start_tls"] = False
            elif is_starttls:
                client_kwargs["use_tls"] = False
                client_kwargs["start_tls"] = True
            else:
                client_kwargs["use_tls"] = False
                client_kwargs["start_tls"] = False

            await aiosmtplib.send(message, **client_kwargs)
            message_id = f"smtp-{uuid.uuid4()}"
            logger.info("Successfully dispatched email via Hostinger SMTP to %s (msg_id: %s)", to_email, message_id)
            return {
                "success": True,
                "message_id": message_id,
                "provider": "hostinger-smtp",
            }
        except aiosmtplib.SMTPException as exc:
            # Safe logging: log exception type and safe representation without secrets
            logger.error(
                "SMTP transmission failed for recipient %s [Error: %s: %s]",
                to_email,
                type(exc).__name__,
                exc.message if hasattr(exc, "message") else str(exc),
            )
            return {
                "success": False,
                "error": f"SMTP Error: {type(exc).__name__}",
                "provider": "hostinger-smtp",
            }
        except Exception as exc:
            logger.error(
                "Unexpected failure during email dispatch to %s [Error: %s]",
                to_email,
                type(exc).__name__,
            )
            return {
                "success": False,
                "error": f"Email dispatch failed: {type(exc).__name__}",
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
