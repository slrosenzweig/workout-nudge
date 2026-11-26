# Inbound SMS relay (Twilio Functions)

Optional helper for deployments that need Twilio to POST inbound SMS to a
JSON webhook (for example a hosted automation URL) instead of directly to
`POST /webhooks/twilio/sms`.

## Configure

Set these on the Function environment. Do not commit real values.

| Context variable | Purpose |
|------------------|---------|
| `INBOUND_WEBHOOK_URL` | Destination webhook URL (required) |
| `INBOUND_WEBHOOK_KEY` | Optional `Authorization: Bearer` token |

`CURSOR_WEBHOOK_URL` and `WEBHOOK_KEY` work as aliases.

## Deploy

From the repo root, with the [Twilio CLI](https://www.twilio.com/docs/twilio-cli) and the serverless plugin:

```bash
# set secrets in the Twilio console or a local .env that is gitignored
twilio serverless:deploy --cwd relay
```

Then set your Messaging Service (or phone number) inbound webhook to the
deployed `/inbound` Function URL. The Function replies with empty TwiML;
the destination webhook is responsible for any confirm SMS.

If you run `python -m workout_nudge serve` yourself, you can skip this
relay and point Twilio straight at `https://your-host/webhooks/twilio/sms`.
