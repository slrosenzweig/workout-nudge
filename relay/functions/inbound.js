/**
 * Twilio Function: forward inbound SMS to your workout-nudge webhook.
 *
 * Twilio posts application/x-www-form-urlencoded; this relay posts JSON
 * with an optional Bearer token. Set these on the Function's environment
 * (or Twilio Function context) — never hardcode URLs or secrets:
 *
 *   INBOUND_WEBHOOK_URL   Public URL of your webhook
 *                         (e.g. https://example.com/webhooks/twilio/sms)
 *   INBOUND_WEBHOOK_KEY   Optional Bearer token the receiver expects
 *
 * CURSOR_WEBHOOK_URL and WEBHOOK_KEY are also accepted as aliases.
 *
 * Deploy with the Twilio CLI, for example:
 *   twilio serverless:deploy --cwd relay
 * Then point the Messaging Service's inbound webhook at this Function.
 */
exports.handler = async function (context, event, callback) {
  const twiml = new Twilio.twiml.MessagingResponse();
  const webhookUrl =
    context.INBOUND_WEBHOOK_URL || context.CURSOR_WEBHOOK_URL;
  const key = context.INBOUND_WEBHOOK_KEY || context.WEBHOOK_KEY;

  if (!webhookUrl) {
    console.error("missing INBOUND_WEBHOOK_URL");
    return callback(null, twiml);
  }

  const payload = {
    From: event.From,
    To: event.To,
    Body: event.Body,
    MessageSid: event.MessageSid || event.SmsSid,
    SmsSid: event.SmsSid || event.MessageSid,
    AccountSid: event.AccountSid,
    MessagingServiceSid: event.MessagingServiceSid,
    NumMedia: event.NumMedia,
    SmsStatus: event.SmsStatus,
  };

  const headers = { "Content-Type": "application/json" };
  if (key) {
    headers.Authorization = `Bearer ${key}`;
  }

  try {
    const res = await fetch(webhookUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
    const text = await res.text();
    console.log("webhook_status", res.status, text.slice(0, 300));
  } catch (err) {
    console.error("relay_error", err && err.message ? err.message : err);
  }

  return callback(null, twiml);
};
