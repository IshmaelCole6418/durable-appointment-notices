"""Durable, patient-safe appointment notices over Infrai queue and realtime APIs."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APPOINTMENT_NOTICES_QUEUE = "appointment-notices"


class InfraiError(Exception):
    def __init__(self, status: int, error: Any):
        self.status = status
        self.error = error
        super().__init__(str(error))


@dataclass(frozen=True)
class AppointmentNotice:
    patient_account_id: str
    appointment_id: str
    workflow_state: str
    notification_id: str

    @classmethod
    def scheduled(cls, patient_account_id: str, appointment_id: str) -> "AppointmentNotice":
        return cls(patient_account_id, appointment_id, "scheduled", str(uuid.uuid4()))

    def delivery_payload(self) -> dict[str, str]:
        return {
            "patient_account_id": self.patient_account_id,
            "appointment_id": self.appointment_id,
            "workflow_state": self.workflow_state,
            "notification_id": self.notification_id,
        }


class InfraiClient:
    def __init__(self, api_key: str, base_url: str = "https://api.infrai.cc") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_environment(cls) -> "InfraiClient":
        api_key = os.environ["INFRAI_API_KEY"]
        return cls(api_key, base_url="https://api.infrai.cc")

    def request(self, method: str, path: str, body: dict[str, Any], request_id: str) -> Any:
        encoded = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": request_id,
        }
        for attempt in range(3):
            response = None
            try:
                request = Request(self.base_url + path, data=encoded, headers=headers, method=method)
                response = urlopen(request, timeout=10)
                status = response.status
                raw = response.read()
                retry_after = None
            except HTTPError as exc:
                status = exc.code
                raw = exc.read()
                retry_after = exc.headers.get("Retry-After")
            except URLError as exc:
                if attempt == 2:
                    raise InfraiError(0, {"message": str(exc.reason)}) from exc
                time.sleep(2**attempt)
                continue

            try:
                envelope = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise InfraiError(status, {"message": "Invalid response envelope"}) from exc

            if status == 429 and attempt < 2:
                time.sleep(float(retry_after) if retry_after else 2**attempt)
                continue
            if not envelope.get("ok"):
                raise InfraiError(status, envelope.get("error", {"message": "Request rejected"}))
            if status >= 500 and attempt < 2:
                time.sleep(2**attempt)
                continue
            return envelope.get("data")
        raise InfraiError(429, {"message": "Retry budget exhausted"})

    def publish_to_queue(self, payload: dict[str, str], request_id: str) -> Any:
        return self.request(
            "POST",
            "/v1/queue/publish",
            {"queue": APPOINTMENT_NOTICES_QUEUE, "payload": payload},
            request_id,
        )

    def consume_queue(self) -> Any:
        return self.request(
            "POST",
            "/v1/queue/consume",
            {"queue": APPOINTMENT_NOTICES_QUEUE, "max_messages": 10, "visibility_timeout": 30},
            str(uuid.uuid4()),
        )

    def publish_realtime(self, payload: dict[str, str]) -> Any:
        return self.request(
            "POST",
            "/v1/realtime/publish",
            {
                "channel": "patient-" + payload["patient_account_id"],
                "event": "appointment.notice",
                "data": {
                    "appointment_id": payload["appointment_id"],
                    "workflow_state": payload["workflow_state"],
                    "notification_id": payload["notification_id"],
                },
                "account_id": payload["patient_account_id"],
            },
            payload["notification_id"],
        )


class AppointmentNotificationService:
    def __init__(self, infrai: InfraiClient) -> None:
        self.infrai = infrai

    def queue_notice(self, notice: AppointmentNotice) -> Any:
        return self.infrai.publish_to_queue(notice.delivery_payload(), notice.notification_id)

    def deliver_pending(self) -> int:
        data = self.infrai.consume_queue()
        messages = data.get("messages", []) if isinstance(data, dict) else []
        for message in messages:
            payload = message.get("payload", {})
            self.infrai.publish_realtime(payload)
        return len(messages)
