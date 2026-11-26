# workout-nudge (SMS brand: Frank the Trainer)

Daily workout accountability SMS for two participants (America/New_York, 7 days a week).

Participant A has an Oura Ring. Participant B is SMS-only after `START` opt-in.

User-facing SMS are prefixed with **Frank the Trainer:** and end with **Reply STOP to opt out.** Address the person running the service by name in chat; Frank the Trainer is the SMS brand only.

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

See `.env.example` (loaded by `src/workout_nudge/config.py`):

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
| `SURPRISE_P_A` / `SURPRISE_P_B` | Optional surprise-text roll odds (default `0.30` / `0.15`) |
| `INBOUND_WEBHOOK_URL` / `INBOUND_WEBHOOK_KEY` | Twilio Function relay only (see `relay/`) |

## Oura OAuth

Oura personal access tokens are deprecated. Use OAuth:

1. Create an Oura application (scopes: `daily workout session personal`).
2. Set redirect URI to `http://localhost:8787/callback` (or your tunnel URL for production refresh).
3. Run:

```bash
python scripts/oauth_login.py
```

This prints the authorize URL (and tries to open a browser), catches the localhost callback, exchanges the code, and writes `tokens.json` (or `OURA_TOKENS_PATH`).

**Refresh tokens are single-use.** The client always persists the new `refresh_token` after each refresh.

Inspect a day (optional `YYYY-MM-DD` argument; default is today in `TZ`):

```bash
python scripts/fetch_day.py
python scripts/fetch_day.py 2026-11-26
```

Prints JSON: `day`, `yesterday`, `readiness`, `sleep`, `activity`, `yesterday_workouts`, `yesterday_trained`, `yesterday_qualifying` (qualifying workouts include minutes, source, intensity, and label). Token paths come from `OURA_TOKENS_PATH`.

List workouts in a range:

```bash
python scripts/fetch_workouts.py
python scripts/fetch_workouts.py 2026-11-01 2026-11-30
```

## CLI

```bash
python -m workout_nudge sync      # 8:00 — remind A to sync Oura ring
python -m workout_nudge report    # 8:30 — scores, today intent, yesterday ask; Mondays include last week’s scoreboard
python -m workout_nudge compare   # 10:00 — partner update or reminders
python -m workout_nudge weekly    # Sunday 11:00 — week recap + next-week commitment ask
python -m workout_nudge poll      # reply-poll backup (see cron)
python -m workout_nudge surprise  # occasional cheer / nudge (see cron)
python -m workout_nudge serve     # Twilio inbound webhook
```

`nudge` is a deprecated alias for `report`. `python scripts/send_weekly.py` is the same as `weekly` and reads numbers / Messaging Service SID from `.env`.

Jobs live in `src/workout_nudge/jobs.py`, `src/workout_nudge/inbound.py`, and `src/workout_nudge/surprise.py`, wired in `src/workout_nudge/cli.py`.

## Daily and weekly flow

The workout week is Monday–Sunday in `TZ` (default America/New_York). Weekly goals are stored under `week_of`, the Monday ISO date (`src/workout_nudge/store.py`).

### 8:00 job (`sync`)

SMS participant A only: open Oura and sync the ring. No scores. This CLI job always sends the reminder; it does not check whether today’s Oura data is already present.

Example: `Frank the Trainer: Good morning — open Oura and sync your ring so we can pull today’s scores. Reply STOP to opt out.`

### 8:30 job (`report`)

1. Fetch Oura for A (today readiness/sleep/activity; workouts yesterday..today).
2. `today_intent`: train if readiness ≥ 70 and sleep looks solid; else rest. Save in the store.
3. Yesterday: if any workout qualifies → record A=yes (no ask). Else SMS YES/NO ask (included in A’s report).
4. SMS A one report: readiness/activity, today intent, yesterday train/rest (or ask).
5. **Mondays only:** also include the closed week’s scoreboard (the Mon–Sun week that ended yesterday): days trained vs `weekly_goal` (met / missed / no goal). Never on Sunday.
6. If B opted in: SMS asking YES/NO for yesterday and/or TRAIN/REST for today, only for fields that are still unknown.
7. Does **not** send partner comparison.

### 10:00 job (`compare`)

- Both complete (yesterday + `today_intent` for A and B) and partner update not yet sent → SMS each the other’s yesterday **and** the other’s today intent; mark `partner_update_sent`.
- Else remind incomplete participants; tell the complete person the other hasn’t updated.
- Idempotent if partner update already sent (`partner_update_sent` in the SQLite store).

Partner example: `Frank the Trainer: Your partner trained yesterday and plans to rest today. Reply STOP to opt out.`

### Sunday 11:00 job (`weekly`)

1. Recap the week ending today (Sunday): for A (and B if opted in), SMS days trained vs goal (met / missed / no goal), and the partner’s stats if known. Days count as trained only when the store has `trained=1` for that date.
2. Ask each for next week’s commitment (0–7 days, Mon–Sun). Example: `Frank the Trainer: New week — how many days will you commit to working out (Mon–Sun)? Reply with a number 0–7. Reply STOP to opt out.`
3. Inbound replies like `4`, `4 days`, `I'll do 5`, or `commit 3` lock the goal for the upcoming (or most recently asked) `week_of`. Confirm: `Frank the Trainer: Locked in — N days this week. Reply STOP to opt out.`
4. When both A and B have goals for that `week_of`, SMS each the other’s commitment.

A Sunday reply is stored as the **next** Monday’s week. A reply on Monday–Saturday is stored as the Monday of the current week.

### Inbound webhook

`POST /webhooks/twilio/sms` — Twilio form params `From`, `To`, `Body`, `MessageSid`. Implemented in `src/workout_nudge/webhook.py`. Shared apply logic lives in `src/workout_nudge/inbound.py`. Parsing lives in `src/workout_nudge/parse.py`.

Validates `X-Twilio-Signature` when `TWILIO_AUTH_TOKEN` is set.

- `START` / `UNSTOP` → opt in
- `STOP` / `CANCEL` / … → opt out
- `YES` / `NO` (and variants) → yesterday workout status
- `TRAIN` / `REST` (and variants, e.g. `train day`, `rest day`) → today intent
- Lone `0`–`7`, `N days`, `I'll do N`, `commit N` → weekly commitment for the upcoming / most recently asked week
- Late path: if both complete, local time ≥ 10:00 in `TZ`, and partner update not sent → send partner updates
- `MessageSid` is recorded in `processed_inbound` so the poll backup will not confirm twice

Point Twilio’s messaging webhook at your public HTTPS URL ending in `/webhooks/twilio/sms`, or use the optional [relay](#inbound-sms-relay) if you need a Twilio Function in front.

### Reply-poll backup (`poll`)

If the inbound webhook is missed, `python -m workout_nudge poll` lists Twilio inbound messages since `last_poll_at` (stored in SQLite `meta`) and applies the same handler. Already-processed `MessageSid` values are skipped. A confirm SMS is sent only when the webhook has not already confirmed that message.

Suggested schedule: :27 and :57, 8 AM–10 PM in `TZ`.

### Surprise texts (`surprise`)

Occasional extra texts, checked around noon and 5 PM. The job rolls the dice (`SURPRISE_P_A` ≈ 30% for A, `SURPRISE_P_B` ≈ 15% for B) and only sends when a hook applies:

- A: hit the weekly goal, one workout away, a streak of 3+ trained days, or falling behind (needed days ≥ days left − 1, or zero train days midweek).
- B (if opted in): cheer reported progress, or a playful quiet invite if nothing is logged. Texts never include the other person’s details.

Caps and quiet hours (all in `src/workout_nudge/surprise.py`, recorded in `surprise_sent`):

- A: at most 3 per Mon–Sun week, never on back-to-back days.
- B: at most 1 per week.
- No sends between 9 PM and 9 AM local.
- Every text uses the Frank the Trainer prefix and `Reply STOP to opt out.`

## Cron (America/New_York)

```cron
CRON_TZ=America/New_York
0 8 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge sync
30 8 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge report
0 10 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge compare
0 11 * * 0 cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge weekly
27,57 8-21 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge poll
0 12,17 * * * cd /path/to/workout-nudge && .venv/bin/python -m workout_nudge surprise
```

Keep `serve` running under systemd/supervisor (or a process manager) for inbound SMS (including late TRAIN/REST / YES/NO replies and weekly commitment numbers). The poll cron is a backup, not a replacement for `serve`.

## Inbound SMS relay

`relay/` is an optional Twilio Function that forwards inbound SMS as JSON to your webhook. URLs and keys come from Function environment variables (`INBOUND_WEBHOOK_URL`, `INBOUND_WEBHOOK_KEY`) — nothing is hardcoded. See `relay/README.md` for deploy steps.

If you run `python -m workout_nudge serve` on a public HTTPS URL, you can point Twilio at `/webhooks/twilio/sms` and skip the relay.

## Workout qualification

See `src/workout_nudge/rules.py` — `qualifies_workout`. Manual Oura entries always count; auto-detected walking, housework, and indoor cycling do not; other auto-detected workouts count at moderate/high (or medium) intensity for 20+ minutes, or for 20+ minutes when the activity is not walking.

## Customizing

| What to change | Where |
|----------------|--------|
| SMS brand prefix (`BRAND`) and message wording | `src/workout_nudge/sms.py` — `BRAND` and the `msg_*` functions |
| Train/rest score cutoffs | `src/workout_nudge/rules.py` — `should_train` (readiness ≥ 70 **and** solid sleep) and `sleep_looks_solid` (sleep score ≥ 70) |
| What counts as a workout | `src/workout_nudge/rules.py` — `qualifies_workout` |
| Job behavior (sync / report / compare / weekly) | `src/workout_nudge/jobs.py` |
| Reply-poll backup | `src/workout_nudge/inbound.py` — `poll` |
| Surprise hooks, caps, quiet hours, odds | `src/workout_nudge/surprise.py`; odds also via `SURPRISE_P_A` / `SURPRISE_P_B` |
| Schedule | The cron block above; CLI entry points in `src/workout_nudge/cli.py` |
| Participants, Twilio, Oura, timezone, database, webhook bind | `.env` (start from `.env.example`); loaded in `src/workout_nudge/config.py` |
| Inbound reply phrases | `src/workout_nudge/parse.py` |
| How inbound SMS is handled | `src/workout_nudge/inbound.py` and `src/workout_nudge/webhook.py` |
| Twilio Function relay | `relay/functions/inbound.js` and `relay/README.md` |

After edits, run the tests (see below).

A hosted deployment may still write more personalized copy than the templates in `sms.py`; the templates are what this package sends.

## Tests

From the repo root, with the dev extra installed (`pip install -e ".[dev]"`):

```bash
pytest
```

Tests live in `tests/`. Pytest is configured in `pyproject.toml` (`testpaths = tests`, `pythonpath = src`).

## Layout

```
src/workout_nudge/   # package
scripts/             # oauth_login.py, fetch_day.py, fetch_workouts.py, send_weekly.py
relay/               # optional Twilio Function
tests/
.env.example
```
