import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.models.system import NotificationRecord

logger = logging.getLogger(__name__)


class BrevoEmailAdapter:
    """Adapter for transactional email delivery via Brevo (Sendinblue) REST API."""

    def __init__(self):
        self.api_url = "https://api.brevo.com/v3/smtp/email"

    async def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not settings.BREVO_API_KEY:
            logger.info(
                f"[MOCK BREVO EMAIL] (No API key configured) To: {to_email} | Subject: {subject}"
            )
            return {
                "success": True,
                "message_id": f"mock-brevo-{uuid.uuid4()}",
                "provider": "brevo-mock",
            }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": settings.BREVO_API_KEY,
        }
        payload = {
            "sender": {
                "name": settings.BREVO_SENDER_NAME,
                "email": settings.BREVO_SENDER_EMAIL,
            },
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "htmlContent": html_content,
        }
        if text_content:
            payload["textContent"] = text_content

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                if resp.status_code in (200, 201, 202):
                    data = resp.json()
                    return {
                        "success": True,
                        "message_id": data.get("messageId", str(uuid.uuid4())),
                        "provider": "brevo",
                    }
                else:
                    logger.error(f"Brevo API error: {resp.status_code} - {resp.text}")
                    return {
                        "success": False,
                        "error": f"Brevo HTTP {resp.status_code}: {resp.text}",
                        "provider": "brevo",
                    }
        except Exception as exc:
            logger.exception("Brevo email dispatch failed")
            return {
                "success": False,
                "error": str(exc),
                "provider": "brevo",
            }


class WhatsAppBusinessAdapter:
    """Adapter for WhatsApp messaging via Meta Graph Cloud API."""

    async def send_message(
        self,
        to_phone: str,
        body_text: str,
        template_name: Optional[str] = None,
        template_params: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        token = settings.WHATSAPP_API_TOKEN
        phone_id = settings.WHATSAPP_PHONE_NUMBER_ID

        if not token or not phone_id:
            logger.info(
                f"[MOCK WHATSAPP] (Credentials missing) To: {to_phone} | Body: {body_text}"
            )
            return {
                "success": True,
                "message_id": f"mock-wa-{uuid.uuid4()}",
                "provider": "whatsapp-mock",
            }

        # Normalize phone (remove + or whitespace)
        cleaned_phone = "".join(filter(str.isdigit, to_phone))
        url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        if template_name:
            components = []
            if template_params:
                parameters = [{"type": "text", "text": p} for p in template_params]
                components.append({"type": "body", "parameters": parameters})
            payload = {
                "messaging_product": "whatsapp",
                "to": cleaned_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en"},
                    "components": components,
                },
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": cleaned_phone,
                "type": "text",
                "text": {"preview_url": False, "body": body_text},
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    msg_id = (
                        data.get("messages", [{}])[0].get("id")
                        if data.get("messages")
                        else str(uuid.uuid4())
                    )
                    return {
                        "success": True,
                        "message_id": msg_id,
                        "provider": "whatsapp",
                    }
                else:
                    logger.error(f"WhatsApp API error: {resp.status_code} - {resp.text}")
                    return {
                        "success": False,
                        "error": f"WhatsApp HTTP {resp.status_code}: {resp.text}",
                        "provider": "whatsapp",
                    }
        except Exception as exc:
            logger.exception("WhatsApp message dispatch failed")
            return {
                "success": False,
                "error": str(exc),
                "provider": "whatsapp",
            }


class NotificationService:
    """Central notification dispatcher coordinating Brevo Email and WhatsApp with database audit records."""

    def __init__(self):
        self.email_adapter = BrevoEmailAdapter()
        self.whatsapp_adapter = WhatsAppBusinessAdapter()

    async def log_record(
        self,
        db: AsyncSession,
        event_type: str,
        recipient: str,
        channel: str,
        status: str,
        payload_ref: Optional[str] = None,
        failure_code: Optional[str] = None,
    ) -> NotificationRecord:
        record = NotificationRecord(
            event_type=event_type,
            recipient_reference=recipient,
            channel=channel,
            status=status,
            payload_reference=payload_ref,
            sent_at=datetime.now(timezone.utc) if status == "DELIVERED" else None,
            failure_code=failure_code,
        )
        db.add(record)
        await db.flush()
        return record

    async def send_verification_email(
        self,
        db: AsyncSession,
        to_email: str,
        user_name: str,
        token: str,
    ) -> bool:
        if not settings.NOTIFICATIONS_ENABLED:
            return False

        from src.services.email_service import email_service
        result = await email_service.send_verification_email(
            to_email=to_email,
            user_name=user_name,
            token=token,
        )
        status_str = "DELIVERED" if result.get("success") else "FAILED"
        await self.log_record(
            db=db,
            event_type="EMAIL_VERIFICATION",
            recipient=to_email,
            channel="EMAIL",
            status=status_str,
            payload_ref=result.get("message_id"),
            failure_code=result.get("error"),
        )
        return result.get("success", False)

    async def send_password_reset(
        self,
        db: AsyncSession,
        to_email: str,
        user_name: str,
        token: str,
        to_phone: Optional[str] = None,
    ) -> bool:
        if not settings.NOTIFICATIONS_ENABLED:
            return False

        from src.services.email_service import email_service
        email_res = await email_service.send_password_reset_email(
            to_email=to_email,
            user_name=user_name,
            token=token,
        )
        await self.log_record(
            db=db,
            event_type="PASSWORD_RESET",
            recipient=to_email,
            channel="EMAIL",
            status="DELIVERED" if email_res.get("success") else "FAILED",
            payload_ref=email_res.get("message_id"),
            failure_code=email_res.get("error"),
        )

        if to_phone:
            wa_text = f"FUNDAMICS LMS: Your password reset code is {token}. Valid for 1 hour."
            wa_res = await self.whatsapp_adapter.send_message(
                to_phone=to_phone, body_text=wa_text
            )
            await self.log_record(
                db=db,
                event_type="PASSWORD_RESET",
                recipient=to_phone,
                channel="WHATSAPP",
                status="DELIVERED" if wa_res.get("success") else "FAILED",
                payload_ref=wa_res.get("message_id"),
                failure_code=wa_res.get("error"),
            )

        return email_res.get("success", False)

    async def send_approval_notification(
        self,
        db: AsyncSession,
        to_email: str,
        user_name: str,
        approved: bool,
        rejection_reason: Optional[str] = None,
        to_phone: Optional[str] = None,
    ) -> bool:
        if not settings.NOTIFICATIONS_ENABLED:
            return False

        if approved:
            subject = "FUNDAMICS LMS — Registration Approved!"
            html = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2>Welcome to FUNDAMICS!</h2>
                <p>Hello {user_name},</p>
                <p>Your student registration has been reviewed and approved by the administration. You can now log in to the portal and access your study materials, classes, and schedules.</p>
            </div>
            """
            wa_text = f"Congratulations {user_name}! Your FUNDAMICS LMS student registration is approved. You can now log in."
        else:
            subject = "FUNDAMICS LMS — Registration Update"
            reason_text = rejection_reason or "Requirements not met."
            html = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2>Registration Status Update</h2>
                <p>Hello {user_name},</p>
                <p>Your student registration could not be approved at this time. Reason: {reason_text}</p>
                <p>Please contact the coaching centre desk if you have questions.</p>
            </div>
            """
            wa_text = f"FUNDAMICS LMS: Your registration could not be approved. Reason: {reason_text}"

        # Use Hostinger SMTP (same as verification/reset emails) instead of Brevo adapter
        from src.services.email_service import email_service
        email_res = await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            text_content=wa_text,
        )
        await self.log_record(
            db=db,
            event_type="REGISTRATION_APPROVED" if approved else "REGISTRATION_REJECTED",
            recipient=to_email,
            channel="EMAIL",
            status="DELIVERED" if email_res.get("success") else "FAILED",
            payload_ref=email_res.get("message_id"),
            failure_code=email_res.get("error"),
        )

        if to_phone:
            wa_res = await self.whatsapp_adapter.send_message(
                to_phone=to_phone, body_text=wa_text
            )
            await self.log_record(
                db=db,
                event_type="REGISTRATION_APPROVED" if approved else "REGISTRATION_REJECTED",
                recipient=to_phone,
                channel="WHATSAPP",
                status="DELIVERED" if wa_res.get("success") else "FAILED",
                payload_ref=wa_res.get("message_id"),
                failure_code=wa_res.get("error"),
            )

        return True


notification_service = NotificationService()
