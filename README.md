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

Jobs are implemented in `src/workout_nudge/jobs.py` and wired in `src/workout_nudge/cli.py`.

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
5. If B opted in: SMS asking YES/NO for yesterday and/or TRAIN/REST for today, only for fields that are still unknown.
6. Does **not** send partner comparison.

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

`POST /webhooks/twilio/sms` — Twilio form params `From`, `To`, `Body`. Implemented in `src/workout_nudge/webhook.py`. Parsing lives in `src/workout_nudge/parse.py`.

Validates `X-Twilio-Signature` when `TWILIO_AUTH_TOKEN` is set.

- `START` / `UNSTOP` → opt in
- `STOP` / `CANCEL` / … → opt out
- `YES` / `NO` (and variants) → yesterday workout status
- `TRAIN` / `REST` (and variants, e.g. `train day`, `rest day`) → today intent
- Lone `0`–`7`, `N days`, `I'll do N`, `commit N` → weekly commitment for the upcoming / most recently asked week
- Late path: if both complete, local time ≥ 10:00 in `TZ`, and partner update not sent → send partner updates

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

## What lives outside this repo

The original deployment also uses hosted routines and helper scripts that are **not** in this package. They are documented here so a self-hosted copy is not mistaken for that setup:

- **Conditional 8:00 sync.** The live sync routine can skip the SMS when today’s Oura readiness is already present. `python -m workout_nudge sync` always sends.
- **Monday scoreboard.** The live 8:30 report can include the closed week’s goal result on Mondays. The `report` job in this repo does not.
- **Reply-poll backup.** A hosted poller at :27 and :57, 8 AM–10 PM, can pick up inbound texts if the webhook is missed. It dedupes with `sms_sent` flags and `processed_inbound_sids`. Those flags and the poller are not in this codebase. This repo’s compare/weekly idempotency uses the SQLite `partner_update_sent` and `weekly_goal` tables instead.
- **Personalized copy.** Live texts are often written to name real workouts and weekly progress. The templates in `src/workout_nudge/sms.py` are the generic versions.
- **Standalone Oura helper and SMS relay.** A local Oura fetch script and a small Twilio Function that forwards inbound SMS to a hosted webhook may run beside this repo. Do not commit tokens, auth keys, or phone numbers from those helpers.

## Workout qualification

See `src/workout_nudge/rules.py` — `qualifies_workout`. Manual Oura entries always count; auto-detected walking, housework, and indoor cycling do not; other auto-detected workouts count at moderate/high (or medium) intensity for 20+ minutes, or for 20+ minutes when the activity is not walking.

## Customizing

| What to change | Where |
|----------------|--------|
| SMS brand prefix (`BRAND`) and message wording | `src/workout_nudge/sms.py` — `BRAND` and the `msg_*` functions |
| Train/rest score cutoffs | `src/workout_nudge/rules.py` — `should_train` (readiness ≥ 70 **and** solid sleep) and `sleep_looks_solid` (sleep score ≥ 70) |
| What counts as a workout | `src/workout_nudge/rules.py` — `qualifies_workout` |
| Job behavior (sync / report / compare / weekly) | `src/workout_nudge/jobs.py` |
| Schedule | The cron block above; CLI entry points in `src/workout_nudge/cli.py` |
| Participants, Twilio, Oura, timezone, database, webhook bind | `.env` (start from `.env.example`); loaded in `src/workout_nudge/config.py` |
| Inbound reply phrases | `src/workout_nudge/parse.py` |
| How inbound SMS is handled | `src/workout_nudge/webhook.py` |

After edits, run the tests (see below).

## Tests

From the repo root, with the dev extra installed (`pip install -e ".[dev]"`):

```bash
pytest
```

Tests live in `tests/test_parse.py`, `tests/test_rules.py`, and `tests/test_store_weekly.py`. Pytest is configured in `pyproject.toml` (`testpaths = tests`, `pythonpath = src`).

## Layout

```
src/workout_nudge/   # package
scripts/             # oauth_login.py, fetch_day.py
tests/
.env.example
```
