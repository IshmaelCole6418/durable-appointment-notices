"""Run an appointment notification handoff with one Infrai credential."""

import argparse

from appointment_notifications import AppointmentNotice, AppointmentNotificationService, InfraiClient, InfraiError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patient_account_id")
    parser.add_argument("appointment_id")
    parser.add_argument("--deliver-pending", action="store_true")
    args = parser.parse_args()

    service = AppointmentNotificationService(InfraiClient.from_environment())
    try:
        notice = AppointmentNotice.scheduled(args.patient_account_id, args.appointment_id)
        service.queue_notice(notice)
        delivered = service.deliver_pending() if args.deliver_pending else 0
    except InfraiError as exc:
        print(f"Notification request rejected: {exc}")
        return 2

    print(f"Queued appointment notice {notice.notification_id}; delivered {delivered} pending notice(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
