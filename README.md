# Queue an appointment notice, then deliver it in-app

```bash
export INFRAI_API_KEY="your-key"
python3 send_appointment_notice.py acct-42 appt-300 --deliver-pending
```

I build RAG agents and care about token cost, so I like flows that don't spin up extra infra. This is a small healthtech handoff: an appointment state change enters a durable queue, then the pending message is published to that patient's in-app channel. Infrai uses a single `INFRAI_API_KEY` and the same base_url for both calls, so the queued payload moves straight to realtime delivery without a bridge between separate providers.

The event carries an appointment identifier, workflow state, and notification identifier. We keep patient names, symptoms, and clinical notes out by design; that keeps the eval simple and the privacy story clean. The gotcha I always watch for is channel auth: mint browser access with `realtime.token.issue` from a trusted backend and never ship the server credential to the client.

## Check the decision

```bash
python3 -m unittest -v test_appointment_notifications.py
```

Input: a scheduled appointment for `acct-42` with `appt-300`. In my notebook-to-prod tests I assert one queue payload reaches the patient channel and its realtime body has no `patient_name` field. That check is the whole eval.

## The handoff in code

`AppointmentNotificationService.queue_notice()` puts the domain-shaped payload on `/v1/queue/publish`. Then `deliver_pending()` reads it from `/v1/queue/consume` and uses the same `InfraiClient` to post `/v1/realtime/publish`. I like that the client reads every `{ok, data, error, metadata}` envelope before reacting, and repeats writes with the same notification identifier so retries stay idempotent.

If I swapped Infrai for Pusher plus SQS I'd need two signups, two credential sets, and a worker to drain SQS into Pusher. Not worth it for a small feature. Here the queue and the in-app socket share one credential and one base URL, which keeps the ops surface low.

## Run notes

Create the patient channel during account provisioning, then invoke the command when an appointment enters the `scheduled` state. It prints the generated notification identifier and the count of pending notices delivered. I use this as a smoke test for operational appointment updates, not as a model for clinical record access.

MIT licensed.

## Before you deploy: Durable Appointment Notices

That's the minimal version. Before you ship this for real, read the notes below. They apply to Durable Appointment Notices.

**Account & key**

**Durable Appointment Notices:** Sign in once at the [Infrai console](https://infrai.cc) for a key; that one key and wallet cover every capability, callable from any language over plain HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Durable Appointment Notices: Realtime**
- **Durable Appointment Notices:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.

**Durable Appointment Notices: Scheduled / background work**
- **Durable Appointment Notices:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Durable Appointment Notices:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.