"""Tests for inbound SMS intent parsing."""

from workout_nudge.parse import Intent, parse_intent, parse_message
from workout_nudge import sms


def test_yes_variants():
    assert parse_intent("YES") is Intent.WORKOUT_YES
    assert parse_intent("yeah") is Intent.WORKOUT_YES
    assert parse_intent("yep") is Intent.WORKOUT_YES
    assert parse_intent("  Yes  ") is Intent.WORKOUT_YES


def test_no_variants():
    assert parse_intent("NO") is Intent.WORKOUT_NO
    assert parse_intent("nope") is Intent.WORKOUT_NO
    assert parse_intent("didn't") is Intent.WORKOUT_NO
    assert parse_intent("didnt") is Intent.WORKOUT_NO


def test_start_stop():
    assert parse_intent("START") is Intent.OPT_IN
    assert parse_intent("STOP") is Intent.OPT_OUT
    assert parse_intent("unstop") is Intent.OPT_IN
    assert parse_intent("CANCEL") is Intent.OPT_OUT
    assert parse_intent("unsubscribe") is Intent.OPT_OUT


def test_did_as_yes():
    assert parse_intent("did") is Intent.WORKOUT_YES


def test_train_variants():
    assert parse_intent("TRAIN") is Intent.TODAY_TRAIN
    assert parse_intent("train") is Intent.TODAY_TRAIN
    assert parse_intent("train day") is Intent.TODAY_TRAIN
    assert parse_intent("training") is Intent.TODAY_TRAIN
    assert parse_intent("train today") is Intent.TODAY_TRAIN


def test_rest_variants():
    assert parse_intent("REST") is Intent.TODAY_REST
    assert parse_intent("rest") is Intent.TODAY_REST
    assert parse_intent("rest day") is Intent.TODAY_REST
    assert parse_intent("resting") is Intent.TODAY_REST
    assert parse_intent("rest today") is Intent.TODAY_REST


def test_weekly_commit_lone_digits():
    for n in range(8):
        r = parse_message(str(n))
        assert r.intent is Intent.WEEKLY_COMMIT
        assert r.days == n
    assert parse_intent("8") is Intent.UNKNOWN
    assert parse_intent("9") is Intent.UNKNOWN


def test_weekly_commit_phrases():
    r = parse_message("4 days")
    assert r.intent is Intent.WEEKLY_COMMIT and r.days == 4
    r = parse_message("I'll do 5")
    assert r.intent is Intent.WEEKLY_COMMIT and r.days == 5
    r = parse_message("ill do 5")
    assert r.intent is Intent.WEEKLY_COMMIT and r.days == 5
    r = parse_message("commit 3")
    assert r.intent is Intent.WEEKLY_COMMIT and r.days == 3
    r = parse_message("0 days")
    assert r.intent is Intent.WEEKLY_COMMIT and r.days == 0
    r = parse_message("7 day")
    assert r.intent is Intent.WEEKLY_COMMIT and r.days == 7


def test_weekly_does_not_steal_keywords():
    assert parse_intent("yes") is Intent.WORKOUT_YES
    assert parse_intent("no") is Intent.WORKOUT_NO
    assert parse_intent("train") is Intent.TODAY_TRAIN
    assert parse_intent("rest") is Intent.TODAY_REST
    assert parse_intent("start") is Intent.OPT_IN
    assert parse_intent("stop") is Intent.OPT_OUT
    # "y" is YES, not a weekly digit path conflict (y is not 0-7)
    assert parse_intent("y") is Intent.WORKOUT_YES
    assert parse_intent("n") is Intent.WORKOUT_NO


def test_sms_brand_winter_rose():
    assert sms.BRAND == "Winter Rose"
    assert sms.msg_sync_ring().startswith("Winter Rose:")
    assert sms.msg_ask_yesterday().startswith("Winter Rose:")
    assert sms.msg_ask_b().startswith("Winter Rose:")
    assert sms.msg_weekly_ask().startswith("Winter Rose:")
    assert sms.msg_weekly_locked(4).startswith("Winter Rose:")
    assert "4 days" in sms.msg_weekly_locked(4)
    assert sms.msg_weekly_partner_commit(3, 5).startswith("Winter Rose:")
    assert sms.msg_weekly_recap(my_days=3, my_goal=5).startswith("Winter Rose:")
    assert sms.msg_partner_update(
        partner_trained_yesterday=True, partner_today_intent="rest"
    ).startswith("Winter Rose:")
    assert "trained yesterday" in sms.msg_partner_update(
        partner_trained_yesterday=True, partner_today_intent="rest"
    )
    assert "plans to rest today" in sms.msg_partner_update(
        partner_trained_yesterday=True, partner_today_intent="rest"
    )
    assert "Foqos" not in sms.msg_weekly_ask()
    assert "Foqos" not in sms.msg_sync_ring()
