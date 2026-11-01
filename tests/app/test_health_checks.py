"""Set-health checks: thresholds, disabled checks, settings saved with the set."""
from setdesigner.app.health.checks import CHECKS, run_checks, threshold
from setdesigner.app.session import SetSession
from setdesigner.model import Card, CheckSetting, Face, Rarity, SetInfo, SetProject, load_project


def make(name, cost, types, text="", rarity=Rarity.COMMON) -> Card:
    return Card(id=name.lower(), rarity=rarity, faces=[Face(name=name, mana_cost=cost, type_line=types,
                                                            rules_text=text)])


def project(*cards, **info) -> SetProject:
    return SetProject(info=SetInfo(name="T", code="T", **info), cards=list(cards))


def ids(warnings, check_id):
    return [w for w in warnings if w.check_id == check_id]


def test_no_cards_no_warnings() -> None:
    assert run_checks(project()) == []


def test_common_removal_counts_per_color() -> None:
    p = project(make("Shock", "{R}", "Instant", "Shock deals 2 damage to any target."),
                make("Bolt", "{R}", "Instant", "Bolt deals 3 damage to any target."),
                make("Doom", "{B}", "Instant", "Destroy target creature."))
    found = ids(run_checks(p), "common_removal")
    messages = [w.message for w in found]
    assert not any(m.startswith("Red") for m in messages)
    black = next(w for w in found if w.message.startswith("Black"))
    assert black.message == "Black has 1 common removal (wanted ≥ 2)" and black.card_ids == ["doom"]
    p.info.health["common_removal"] = CheckSetting(threshold=1)
    assert [w.message.split()[0] for w in ids(run_checks(p), "common_removal")] == ["White", "Blue", "Green"]


def test_disabled_check_is_silent() -> None:
    p = project(make("Bear", "{1}{G}", "Creature"))
    assert ids(run_checks(p), "two_drops")
    p.info.health["two_drops"] = CheckSetting(enabled=False)
    assert not ids(run_checks(p), "two_drops")


def test_wordy_commons_threshold() -> None:
    long = " ".join(["word"] * 12)
    p = project(make("Long", "{U}", "Sorcery", long))
    p.info.health["wordy_commons"] = CheckSetting(threshold=12)
    assert not ids(run_checks(p), "wordy_commons")
    p.info.health["wordy_commons"] = CheckSetting(threshold=11)
    assert ids(run_checks(p), "wordy_commons")[0].card_ids == ["long"]


def test_rarity_slots_and_creature_share() -> None:
    p = project(make("Bear", "{1}{G}", "Creature"), make("Growth", "{G}", "Instant"),
                rarity_slots={Rarity.COMMON: 3})
    found = run_checks(p)
    assert ids(found, "rarity_slots")[0].message == "Common: 2 of 3 cards (1 short of the target)"
    share = ids(found, "creature_share")[0]
    assert share.message == "Green commons are 50% creatures (wanted ≥ 55%)" and share.card_ids == ["growth"]


def test_fixing_only_with_multicolor_cards() -> None:
    p = project(make("Bear", "{1}{G}", "Creature"))
    assert not ids(run_checks(p), "fixing")
    p.cards.append(make("Duo", "{R}{G}", "Creature", rarity=Rarity.UNCOMMON))
    assert ids(run_checks(p), "fixing")


def test_settings_round_trip(tmp_path) -> None:
    session = SetSession.create(tmp_path / "s", "S", "S", renderer_factory=lambda p: None)
    session.set_health_check("wordy_commons", True, 30)
    session.set_health_check("two_drops", False, None)
    reopened = load_project(tmp_path / "s")
    assert threshold(reopened, CHECKS["wordy_commons"]) == 30
    assert reopened.info.health["two_drops"].enabled is False
    assert threshold(reopened, CHECKS["two_drops"]) == 2


def test_role_overrides_are_saved(tmp_path) -> None:
    session = SetSession.create(tmp_path / "s", "S", "S", renderer_factory=lambda p: None)
    card = session.new_card("Bear")
    session.set_role(card, "removal", True)
    session.flush()
    assert load_project(tmp_path / "s").cards[0].role_overrides == {"removal": True}
    session.set_role(card, "removal", None)
    session.flush()
    assert load_project(tmp_path / "s").cards[0].role_overrides == {}


def test_mechanic_roles_fill_the_counts(tmp_path) -> None:
    session = SetSession.create(tmp_path / "s", "S", "S", renderer_factory=lambda p: None)
    hunt = session.new_mechanic("Hunt")
    for name in ("Stalker", "Tracker"):
        c = session.new_card(name)
        session.update(c, "mana_cost", "{B}")
        session.update(c, "rules_text", "Hunt")
    black = lambda: [w for w in run_checks(session.project)                     # noqa: E731
                     if w.check_id == "common_removal" and w.message.startswith("Black")]
    assert black()
    session.update_mechanic(hunt, roles=["removal", "nonsense"])
    assert hunt.roles == ["removal"]
    assert not black()
    assert load_project(tmp_path / "s").mechanics[0].roles == ["removal"]
