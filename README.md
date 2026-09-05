# workout-nudge (SMS brand: Winter Rose)

Daily workout accountability SMS for two participants (America/New_York, 7 days a week).

Participant A has an Oura Ring. Participant B is SMS-only after `START` opt-in.

User-facing SMS are prefixed with **Winter Rose:**. Address the person running the service as Sarah in chat; Winter Rose is the SMS brand only.

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
python -m workout_nudge sync     # 8:00 — remind A to sync Oura ring
python -m workout_nudge report   # 8:30 — scores, today intent, yesterday ask
python -m workout_nudge compare  # 10:00 — partner update or reminders
python -m workout_nudge weekly   # Sunday 11:00 — week recap + next-week commitment ask
python -m workout_nudge serve    # Twilio inbound webhook
```

`nudge` is a deprecated alias for `report`.

### 8:00 job (`sync`)

SMS participant A only: open Oura and sync the ring. No scores.

Example: `Winter Rose: Good morning — open Oura and sync your ring so we can pull today’s scores. Reply STOP to opt out.`

### 8:30 job (`report`)

1. Fetch Oura for A (today readiness/sleep/activity; workouts yesterday..today).
2. `today_intent`: train if readiness ≥ 70 and sleep looks solid; else rest. Save in store.
3. Yesterday: if any workout qualifies → record A=yes (no ask). Else SMS YES/NO ask (included in A’s report).
4. SMS A one report: readiness/activity, today intent, yesterday train/rest (or ask).
5. If B opted in: SMS asking YES/NO for yesterday **and** TRAIN/REST for today.
6. Does **not** send partner comparison.

### 10:00 job (`compare`)

- Both complete (yesterday + `today_intent` for A and B) and partner update not yet sent → SMS each the other’s yesterday **and** the other’s today intent; mark `partner_update_sent`.
- Else remind incomplete participants; tell the complete person the other hasn’t updated.
- Idempotent if partner update already sent.

Partner example: `Winter Rose: Your partner trained yesterday and plans to rest today. Reply STOP to opt out.`


### Sunday 11:00 job (`weekly`)

Goal week = Monday–Sunday (America/New_York). Store key `week_of` = that Monday’s ISO date.

1. Recap the week ending today (Sunday): for A (and B if opted in), SMS days trained vs goal (met / missed / no goal), and partner’s if known.
2. Ask each for next week’s commitment (0–7 days, Mon–Sun). Example: `Winter Rose: New week — how many days will you commit to working out (Mon–Sun)? Reply with a number 0–7. Reply STOP to opt out.`
3. Inbound replies like `4`, `4 days`, `I'll do 5`, or `commit 3` lock the goal for the upcoming (or most recently asked) `week_of`. Confirm: `Winter Rose: Locked in — N days this week. Reply STOP to opt out.`
4. When both A and B have goals for that `week_of`, SMS each the other’s commitment.

### Inbound webhook

`POST /webhooks/twilio/sms` — Twilio form params `From`, `To`, `Body`.

Validates `X-Twilio-Signature` when `TWILIO_AUTH_TOKEN` is set.

- `START` / `UNSTOP` → opt in
- `STOP` / `CANCEL` / … → opt out
- `YES` / `NO` (and variants) → yesterday workout status
- `TRAIN` / `REST` (and variants, e.g. `train day`, `rest day`) → today intent
- Lone `0`–`7`, `N days`, `I'll do N`, `commit N` → weekly commitment for the upcoming / most recently asked week
- Late path: if both complete, local time ≥ 10:00 America/New_York, and partner update not sent → send partner updates

Point Twilio’s messaging webhook at your public HTTPS URL ending in `/webhooks/twilio/sms`.

## Cron (America/New_York)

```cron
CRON_TZ=America/New_York
0 8 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge sync
30 8 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge report
0 10 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge compare
0 11 * * 0 cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge weekly
```

Keep `serve` running under systemd/supervisor (or a process manager) for inbound SMS (including late TRAIN/REST / YES/NO replies and weekly commitment numbers).

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
