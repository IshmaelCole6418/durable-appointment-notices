import unittest

from appointment_notifications import AppointmentNotice, AppointmentNotificationService, InfraiClient


class RecordingInfrai:
    def __init__(self) -> None:
        self.queued = []
        self.published = []

    def publish_to_queue(self, payload, request_id):
        self.queued.append((payload, request_id))

    def consume_queue(self):
        return {"messages": [{"payload": self.queued[0][0]}]}

    def publish_realtime(self, payload):
        self.published.append(payload)


class CapturingClient(InfraiClient):
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, body, request_id):
        self.calls.append((method, path, body, request_id))


class AppointmentNotificationTests(unittest.TestCase):
    def test_queue_boundaries_include_the_required_queue(self):
        client = CapturingClient()

        client.publish_to_queue({"notification_id": "notice-1"}, "notice-1")
        client.consume_queue()

        publish = client.calls[0]
        consume = client.calls[1]
        self.assertEqual(publish[2], {
            "queue": "appointment-notices",
            "payload": {"notification_id": "notice-1"},
        })
        self.assertEqual(consume[2], {
            "queue": "appointment-notices",
            "max_messages": 10,
            "visibility_timeout": 30,
        })

    def test_scheduled_notice_is_queued_then_delivered_without_patient_details(self):
        gateway = RecordingInfrai()
        service = AppointmentNotificationService(gateway)
        notice = AppointmentNotice(
            patient_account_id="acct-42",
            appointment_id="appt-300",
            workflow_state="scheduled",
            notification_id="notice-1",
        )

        service.queue_notice(notice)
        delivered = service.deliver_pending()

        self.assertEqual(delivered, 1)
        self.assertEqual(gateway.published[0]["appointment_id"], "appt-300")
        self.assertNotIn("patient_name", gateway.published[0])

    def test_realtime_boundary_targets_the_patient_channel_with_minimum_payload(self):
        client = CapturingClient()
        notice = AppointmentNotice(
            patient_account_id="acct-42",
            appointment_id="appt-300",
            workflow_state="scheduled",
            notification_id="notice-1",
        )

        client.publish_realtime(notice.delivery_payload())

        method, path, body, request_id = client.calls[0]
        self.assertEqual((method, path, request_id), ("POST", "/v1/realtime/publish", "notice-1"))
        self.assertEqual(body["channel"], "patient-acct-42")
        self.assertEqual(body["data"], {
            "appointment_id": "appt-300",
            "workflow_state": "scheduled",
            "notification_id": "notice-1",
        })


if __name__ == "__main__":
    unittest.main()
