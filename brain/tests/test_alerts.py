import random

from fixtures import creeper, snap, zombie

from kindred.alerts import Alerts, ambient_mood


def alerts():
    return Alerts(rng=random.Random(1))


def test_creeper_close_behind_warns_with_direction():
    a = alerts().check(snap(hostiles=[creeper(5, "behind")]), now=0)
    assert a and a.kind == "creeper" and a.mood == "scared"
    assert "behind you" in a.text


def test_creeper_far_away_is_ignored():
    assert alerts().check(snap(hostiles=[creeper(15)]), now=0) is None


def test_creeper_warning_has_a_cooldown():
    al = alerts()
    s = snap(hostiles=[creeper(5)])
    assert al.check(s, now=0)
    assert al.check(s, now=5) is None
    assert al.check(s, now=Alerts.CREEPER_COOLDOWN + 0.1)


def test_low_health_warns_once_until_healed():
    al = alerts()
    low = snap(health=5.0)
    first = al.check(low, now=0)
    assert first and first.kind == "low_health" and "2.5 hearts" in first.text
    assert al.check(low, now=30) is None                      # still low: no nagging
    assert al.check(snap(health=14.0), now=40) is None        # healed: re-armed
    assert al.check(snap(health=4.0), now=50).kind == "low_health"


def test_low_health_reminds_after_a_long_time():
    al = alerts()
    al.check(snap(health=5.0), now=0)
    assert al.check(snap(health=5.0), now=Alerts.LOW_HEALTH_REMIND + 1)


def test_low_health_with_monsters_says_run():
    a = alerts().check(snap(health=4.0, hostiles=[zombie(6)]), now=0)
    assert "monsters" in a.text or "after you" in a.text


def test_creeper_beats_low_health_and_two_alerts_keep_a_gap():
    al = alerts()
    s = snap(health=4.0, hostiles=[creeper(3)])
    assert al.check(s, now=0).kind == "creeper"
    assert al.check(s, now=1) is None                          # MIN_GAP
    assert al.check(s, now=Alerts.MIN_GAP + 0.1).kind == "low_health"


def test_no_warnings_in_creative_or_when_dead():
    assert alerts().check(snap(gamemode="creative", hostiles=[creeper(2)]), now=0) is None
    assert alerts().check(snap(health=0.0), now=0) is None


def test_ambient_mood():
    assert ambient_mood(snap()) == "happy"
    assert ambient_mood(snap(hostiles=[zombie(8)])) == "worried"
    assert ambient_mood(snap(time={"day": 1, "timeOfDay": 15000})) == "calm"
