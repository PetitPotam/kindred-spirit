"""Her relationship with you, scenario by scenario (a fake clock; ranges, not exact numbers)."""
import random

from kindred.bonds import DAY, MINUTE, Bonds, fresh


def pip(a=50, t=50, f=40, temperament="default"):
    s = fresh(30, temperament, random.Random(1), now=0.0)
    s["temperament"] = dict(s["base_temperament"])  # no per-world jitter in tests
    s["a"], s["t"], s["f"], s["f_peak"] = float(a), float(t), float(f), float(f)
    return Bonds(s)


def play(b, now, minutes, step=1.0):
    """Time together, a minute at a time."""
    t = now
    while t < now + minutes * MINUTE:
        t += step * MINUTE
        b.advance(t)
    return t


def test_kind_for_an_hour_then_one_insult_is_shrugged_off():
    b, now = pip(50, 50), 0.0
    for _ in range(20):
        now = play(b, now, 3)
        b.impress("kind" if _ % 2 else "sweet", now)
    a0, t0 = b.s["a"], b.s["t"]
    assert 60 <= a0 <= 75 and t0 >= 52, (a0, t0)
    b.impress("rude", now, "you're annoying")
    assert b.sting(now) > 0.3
    assert -3.0 <= b.s["a"] - a0 <= -1.0 and b.s["t"] - t0 >= -0.8, "one slip from a friend: benefit of the doubt"
    assert b.s["g"] < 3
    b.apologize(now + 10, words="sorry")
    now = play(b, now, 30)
    assert b.s["g"] < 1 and b.stance(now) in ("warm", "easy")


def test_insults_every_day_hurt_far_more_than_the_same_in_one_evening():
    def evening(b, now):
        for kind in ("rude", "mean", "rude"):
            now = play(b, now, 8)
            b.impress(kind, now, "you're useless")
            b.apologize(now + 20, words="sorry")
        return play(b, now, 6)

    daily, now = pip(50, 50), 0.0
    credits = []
    for day in range(5):
        now = evening(daily, now)
        credits.append(daily.credit(now))
        now += DAY - 30 * MINUTE
    once, t = pip(50, 50), 0.0
    for _ in range(5):
        t = evening(once, t)  # the same 15 events, one evening
    t += 5 * DAY
    once.advance(t)
    daily.advance(now)
    assert daily.s["t"] < 30, daily.s["t"]
    assert daily.floor() >= 12, "a pattern over days leaves a scar"
    assert once.s["t"] < 30, "hollow apologies between hurts are betrayals: trust doesn't survive either"
    assert daily.stance(now) in ("wounded", "guarded", "cold", "bitter")
    assert once.s["g"] <= once.floor() + 5, "days apart soften the grudge, down to its scar"
    assert credits[-1] <= credits[0], "apologies are worth less and less"


def test_trust_doesnt_come_back_from_time_apart():
    b, now = pip(50, 50), 0.0
    b.impress("hit_deliberate", now)
    t_after = b.s["t"]
    b.advance(now + 10 * DAY)
    assert abs(b.s["t"] - t_after) < 0.01 and b.s["g"] < 2


def test_an_accident_between_friends_costs_no_trust():
    b, now = pip(70, 70), 0.0
    t0 = b.s["t"]
    b.impress("hit_accident", now)
    assert b.s["t"] == t0 and 0 < b.sting(now) < 0.3 and not b.open_incidents()


def test_hurt_again_during_probation_is_a_betrayal():
    b, now = pip(60, 60), 0.0
    first = b.impress("hit_deliberate", now)
    b.apologize(now + 5)
    sorry1 = b.credit(now + 5)
    second = b.impress("hit_deliberate", now + 60)
    assert second["t"] <= 2 * first["t"], (first, second)
    assert b.credit(now + 60) <= sorry1 / 2


def test_like_but_dont_trust():
    b, now = pip(50, 45), 0.0
    for session in range(4):
        for _ in range(8):
            now = play(b, now, 2)
            b.impress("sweet", now)
        b.impress("hit_deliberate", now)
        now = play(b, now, 5) + DAY
    assert b.s["a"] >= 55 and b.s["t"] < 40, (b.s["a"], b.s["t"])
    assert b.stance(now) in ("guarded", "wounded")


def test_trust_but_resent():
    b, now = pip(40, 50), 0.0
    for _ in range(12):
        now = play(b, now, 4)
        b.impress("favour", now)
        b.impress("rude", now, "you're so dumb")
        b.impress("dismissive", now + 5, "whatever")
    assert b.s["g"] >= 35, b.s["g"]
    assert b.stance(now) in ("reliant", "bitter", "cold", "wounded")


def test_earned_repair_heals_a_scar_but_she_remembers():
    b, now = pip(50, 60), 0.0
    for _ in range(6):
        now = play(b, now, 5)
        b.impress("mean", now, "you're worthless")
    assert b.floor() >= 12
    t_low = b.s["t"]
    b.apologize(now, real=True, words="I'm sorry I called you worthless, that was wrong")
    gesture = b.ask_gesture(random.Random(2), now)
    assert gesture
    from kindred.bonds import GESTURES
    word = GESTURES[gesture["kind"]][1][0]
    assert b.gesture_check(["placed a %s" % word], now)
    for _ in range(4):
        now = play(b, now, 30) + DAY
        b.session_start(now)
    assert b.floor() == 0 and b.healed_scars, "three calm sessions after a real apology and a gesture"
    assert t_low < b.s["t"] < 60, "trust rising, but not back to where it was"


def test_sweet_words_cant_buy_love():
    b, now = pip(40, 40), 0.0
    a0, t0 = b.s["a"], b.s["t"]
    for i in range(50):
        b.impress("sweet", now + i)
    assert b.s["t"] - t0 < 0.1, "words never raise trust (only a little calm time passed)"
    assert b.s["a"] - a0 < 60


def test_respect_follows_how_you_act():
    b, now = pip(50, 50), 0.0
    b.impress("killed_villager", now)
    assert b.s["r"] <= 45, "one: a little benefit of the doubt"
    b.impress("killed_villager", now + 60)
    b.impress("killed_villager", now + 120)
    b.impress("killed_villager", now + 180)
    assert "not impressed" in b.guidance(now + 180, "")
    low = b.s["r"]
    b.impress("feat", now, scale=2)
    assert b.s["r"] > low, "beating something big earns some back"
    after = b.s["r"]
    now = play(b, now, 600, step=5)
    assert b.s["r"] > after + 5, "and it drifts back toward neutral over a day of play"


def test_banter_and_the_old_bond_number():
    b = pip(60, 70, f=60)
    assert 0 < b.bond() <= 100
    b.set_bond(80)
    assert abs(b.bond() - 80) < 0.5, "old saves and imports still set the meter"
    assert b.explain(0)["stance"] and b.explain(0)["summary"]


def test_every_change_says_why():
    b, now = pip(50, 50), 0.0
    for _ in range(3):
        b.impress("mean", now, "you're useless")
        now += 3600
    line = b.s["log"][-1]["line"]
    assert line.startswith('mean "you\'re useless" — deliberate · pattern') and "trust -" in line
