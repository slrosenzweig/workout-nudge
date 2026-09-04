# Winter Rose — workout-nudge

Daily workout accountability SMS for two participants (America/New_York, 7 days a week).

Participant A has an Oura Ring. Participant B is SMS-only after `START` opt-in.

**Do not commit secrets, real phone numbers, Twilio SIDs, or Oura tokens.**

## Setup

```bash
cd workout-nudge
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with your credentials (never commit .env)
```

## Environment

See `.env.example`:

| Variable | Purpose |
|----------|---------|
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Twilio API |
| `TWILIO_MESSAGING_SERVICE_SID` | Preferred send path |
| `TWILIO_FROM_NUMBER` | Fallback From if no messaging service |
| `OURA_CLIENT_ID` / `OURA_CLIENT_SECRET` | Oura OAuth app |
| `OURA_REDIRECT_URI` | Default `http://localhost:8787/callback` |
| `OURA_TOKENS_PATH` | JSON token file (gitignored) |
| `PARTICIPANT_A_NUMBER` / `PARTICIPANT_B_NUMBER` | E.164 numbers |
| `TZ` | `America/New_York` |
| `DATABASE_PATH` | SQLite path |
| `WEBHOOK_HOST` / `WEBHOOK_PORT` | Inbound SMS server |

## Oura OAuth

Oura personal access tokens are deprecated. Use OAuth:

1. Create an Oura application (scopes: `daily workout session personal`).
2. Set redirect URI to `http://localhost:8787/callback` (or your tunnel URL for production refresh).
3. Run:

```bash
python scripts/oauth_login.py
```

This opens the authorize URL, catches the localhost callback, exchanges the code, and writes `tokens.json` (or `OURA_TOKENS_PATH`).

**Refresh tokens are single-use.** The client always persists the new `refresh_token` after each refresh.

Inspect a day:

```bash
python scripts/fetch_day.py
```

Prints JSON: `day`, `yesterday`, `readiness`, `sleep`, `activity`, `yesterday_workouts`, `yesterday_trained`, `yesterday_qualifying`.

## CLI

```bash
python -m workout_nudge nudge    # ~8:15 morning job
python -m workout_nudge compare  # 10:00 follow-up
python -m workout_nudge serve    # Twilio inbound webhook
```

### Morning job (`nudge`)

1. Fetch Oura for A (today readiness/sleep/activity; workouts yesterday..today).
2. Train if readiness ≥ 70 and sleep looks solid; else rest.
3. SMS A (train or rest). On train days, also SMS B if opted in.
4. If any yesterday workout qualifies → record A=yes (no YES/NO ask for A). Else ask A (and B if opted in).

### 10:00 job (`compare`)

- Both known + comparison already sent → no-op
- Both known + not sent → send partner comparison
- Only one known → tell that person the other hasn't answered; remind the other if appropriate
- Neither known → one YES/NO reminder (B only if opted in)

### Inbound webhook

`POST /webhooks/twilio/sms` — Twilio form params `From`, `To`, `Body`.

Validates `X-Twilio-Signature` when `TWILIO_AUTH_TOKEN` is set.

- `START` / `UNSTOP` → opt in
- `STOP` / `CANCEL` / … → opt out
- `YES` / `NO` (and variants) → yesterday workout status; when both known, send comparison

Point Twilio’s messaging webhook at your public HTTPS URL ending in `/webhooks/twilio/sms`.

## Cron (America/New_York)

```cron
15 8 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge nudge
0 10 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge compare
```

Use a timezone-aware cron (`CRON_TZ=America/New_York`) or run on a host set to that zone.

Keep `serve` running under systemd/supervisor (or a process manager) for inbound SMS.

## Workout qualification (locked)

See `src/workout_nudge/rules.py` — `qualifies_workout`. Manual entries always count; auto walking/housework/indoor_cycling do not; moderate/high ≥ 20 minutes (non-walking) does.

## Tests

```bash
pytest
```

## Layout

```
src/workout_nudge/   # package
scripts/             # oauth_login.py, fetch_day.py
tests/
```
