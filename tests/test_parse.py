"""Tests for inbound SMS intent parsing."""

from workout_nudge.parse import Intent, parse_intent
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


def test_sms_brand_sarah():
    assert sms.msg_sync_ring().startswith("Sarah:")
    assert sms.msg_ask_yesterday().startswith("Sarah:")
    assert sms.msg_ask_b().startswith("Sarah:")
    assert sms.msg_partner_update(
        partner_trained_yesterday=True, partner_today_intent="rest"
    ).startswith("Sarah:")
    assert "trained yesterday" in sms.msg_partner_update(
        partner_trained_yesterday=True, partner_today_intent="rest"
    )
    assert "plans to rest today" in sms.msg_partner_update(
        partner_trained_yesterday=True, partner_today_intent="rest"
    )
    assert "Winter Rose" not in sms.msg_sync_ring()
