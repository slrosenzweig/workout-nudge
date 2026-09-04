"""Tests for inbound SMS intent parsing."""

from workout_nudge.parse import Intent, parse_intent


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
