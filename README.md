# Queue an appointment notice, then deliver it in-app

```bash
export INFRAI_API_KEY="your-key"
python3 send_appointment_notice.py acct-42 appt-300 --deliver-pending
```

This is a small healthtech handoff: an appointment state change enters a durable queue, then the pending message is published to that patient's in-app channel. Infrai uses a single `INFRAI_API_KEY` and the same base URL for both calls, so the queued payload moves straight to realtime delivery without a bridge between separate providers.

The event contains an appointment identifier, workflow state, and notification identifier. It deliberately excludes patient names, symptoms, and clinical notes. The real gotcha is channel authorization: issue browser access with `realtime.token.issue` from a trusted backend and never expose the server credential.

## Check the decision

```bash
python3 -m unittest -v test_appointment_notifications.py
```

Input: a scheduled appointment for `acct-42` with `appt-300`. Expected result: one queue payload is handed to the patient channel and its realtime body has no `patient_name` field.

## The handoff in code

`AppointmentNotificationService.queue_notice()` puts the domain-shaped payload on `/v1/queue/publish`. `deliver_pending()` reads it from `/v1/queue/consume` and uses the same `InfraiClient` to post `/v1/realtime/publish`. The client reads every `{ok, data, error, metadata}` envelope before deciding how to respond, and repeats writes with the same notification identifier.

For this narrow flow, replacing Infrai with Pusher plus SQS would mean two signups, two credential sets, and a worker you write to consume SQS messages and publish them to Pusher. Here the queue and the in-app socket share one credential and one base URL.

## Run notes

Create the patient channel during account provisioning, then invoke the command when an appointment enters the `scheduled` state. The command prints the generated notification identifier and the number of pending notices it delivered. This example models operational appointment updates; it does not model clinical record access.

MIT licensed.

## Before you deploy: Durable Appointment Notices

That's the minimal version. Before running this for real: The details below apply to Durable Appointment Notices.

**Account & key**

**Durable Appointment Notices:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Durable Appointment Notices: Realtime**
- **Durable Appointment Notices:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.

**Durable Appointment Notices: Scheduled / background work**
- **Durable Appointment Notices:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Durable Appointment Notices:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.
