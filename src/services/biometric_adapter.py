"""
Biometric Transport Adapter Layer for FUNDAMICS LMS.

Provides an abstraction between physical biometric devices (e.g., Secureye S-B8CB)
and the core attendance business logic (BiometricService).

Supports:
1. Native Webhook Push (Direct device HTTP/HTTPS POST to /api/v1/integrations/biometric/secureye/events).
2. Local LAN Bridge Service (Local daemon pulling punches from S-B8CB via TCP/SDK and forwarding to the API).
"""

import abc
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from src.schemas.teacher_attendance import BiometricEventWebhookPayload
from src.models.teacher_attendance import BiometricEventType


class BaseBiometricAdapter(abc.ABC):
    """Abstract adapter defining standard normalization from device wire format to domain payload."""

    @abc.abstractmethod
    def normalize_event(self, raw_data: Dict[str, Any], device_id: str) -> BiometricEventWebhookPayload:
        """Parse a single raw hardware punch into a validated BiometricEventWebhookPayload."""
        pass

    def normalize_batch(self, raw_events: List[Dict[str, Any]], device_id: str) -> List[BiometricEventWebhookPayload]:
        """Normalize a batch of raw events."""
        return [self.normalize_event(ev, device_id) for ev in raw_events]


class SecureyeNativeWebhookAdapter(BaseBiometricAdapter):
    """
    Adapter for devices capable of direct HTTP/HTTPS push.
    Expects standard JSON fields matching BiometricEventWebhookPayload.
    """

    def normalize_event(self, raw_data: Dict[str, Any], device_id: str) -> BiometricEventWebhookPayload:
        event_time = raw_data.get("event_at_utc")
        if isinstance(event_time, str):
            dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        elif isinstance(event_time, datetime):
            dt = event_time
        else:
            dt = datetime.now(timezone.utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        raw_type = str(raw_data.get("event_type", "IN")).upper()
        event_type = BiometricEventType.OUT if raw_type == "OUT" else BiometricEventType.IN

        return BiometricEventWebhookPayload(
            device_id=device_id,
            external_event_id=str(raw_data.get("external_event_id") or raw_data.get("log_id") or ""),
            employee_identifier=str(raw_data.get("employee_identifier") or raw_data.get("user_id") or "").strip(),
            event_type=event_type,
            event_at_utc=dt,
            raw_reference=raw_data.get("raw_reference"),
        )


class SecureyeSB8CBLocalBridgeAdapter(BaseBiometricAdapter):
    """
    Adapter for Secureye S-B8CB when accessed via local LAN bridge agent.

    Secureye S-B8CB standard firmware exports logs with:
    - EnrollNumber / UserID (int or string)
    - Time / Date (local timestamp in YYYY-MM-DD HH:MM:SS)
    - InOutMode / VerifyState (0 = Check In, 1 = Check Out)
    - LogIndex / RecordID (integer sequence)
    """

    def __init__(self, local_timezone_offset_hours: float = 5.5):
        self.offset_hours = local_timezone_offset_hours

    def normalize_event(self, raw_data: Dict[str, Any], device_id: str) -> BiometricEventWebhookPayload:
        # 1. Parse hardware record ID
        rec_id = raw_data.get("RecordID") or raw_data.get("LogIndex") or raw_data.get("id") or str(uuid.uuid4())
        external_event_id = f"SB8CB-{device_id}-{rec_id}"

        # 2. Parse employee identifier
        enroll_id = str(raw_data.get("EnrollNumber") or raw_data.get("UserID") or raw_data.get("employee_identifier", "")).strip()

        # 3. Parse punch direction (0 = IN, 1 = OUT or explicit string)
        mode = raw_data.get("InOutMode", 0)
        if str(mode) in ("1", "OUT", "out"):
            event_type = BiometricEventType.OUT
        else:
            event_type = BiometricEventType.IN

        # 4. Parse punch timestamp
        raw_time = raw_data.get("Time") or raw_data.get("DateTime") or raw_data.get("event_at_utc")
        if isinstance(raw_time, datetime):
            dt = raw_time
        elif isinstance(raw_time, str):
            try:
                dt = datetime.fromisoformat(raw_time)
            except ValueError:
                dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.now(timezone.utc)

        if dt.tzinfo is None:
            # Assume local time offset (e.g. Asia/Kolkata +05:30) and convert to UTC
            from datetime import timedelta
            tz_offset = timezone(timedelta(hours=self.offset_hours))
            dt = dt.replace(tzinfo=tz_offset).astimezone(timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return BiometricEventWebhookPayload(
            device_id=device_id,
            external_event_id=external_event_id,
            employee_identifier=enroll_id,
            event_type=event_type,
            event_at_utc=dt,
            raw_reference=str(raw_data.get("raw") or raw_data),
        )
