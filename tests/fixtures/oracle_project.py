"""A small set covering the card shapes the MSE mapping must handle. Used by the
model tests and as the set loaded into real MSE for tools/oracle_cases/cards.txt."""
from setdesigner.model import Card, Face, FaceRole, Layout, Rarity, SetInfo, SetProject


def oracle_project() -> SetProject:
    return SetProject(
        info=SetInfo(name="Oracle Test Set", code="ORC", artist="Set Artist"),
        cards=[
            Card(id="grizzly-bears", rarity=Rarity.COMMON, faces=[Face(
                name="Grizzly Bears", mana_cost="{1}{G}", type_line="Creature — Bear",
                power="2", toughness="2", flavor_text="Don't feed them.", artist="Jeff A. Menges")]),
            Card(id="boros-guildmage", rarity=Rarity.UNCOMMON, faces=[Face(
                name="Boros Guildmage", mana_cost="{R/W}{R/W}", type_line="Creature — Human Wizard",
                rules_text="{1}{R}: Target creature gains haste until end of turn.",
                power="2", toughness="2")]),
            Card(id="lightning-helix", rarity=Rarity.UNCOMMON, faces=[Face(
                name="Lightning Helix", mana_cost="{R}{W}", type_line="Instant",
                rules_text="Lightning Helix deals 3 damage to any target and you gain 3 life.")]),
            Card(id="steel-overseer", rarity=Rarity.RARE, faces=[Face(
                name="Steel Overseer", mana_cost="{2}", type_line="Legendary Artifact Creature — Construct",
                rules_text="{T}: Put a +1/+1 counter on each artifact creature you control.",
                power="1", toughness="1")]),
            Card(id="forest", rarity=Rarity.COMMON, faces=[Face(
                name="Forest", type_line="Basic Land — Forest")]),
            Card(id="ajani-goldmane", rarity=Rarity.MYTHIC, faces=[Face(
                name="Ajani Goldmane", mana_cost="{2}{W}{W}", type_line="Legendary Planeswalker — Ajani",
                loyalty="4")]),
            Card(id="delver", layout=Layout.TRANSFORM, rarity=Rarity.COMMON, faces=[
                Face(name="Delver of Secrets", mana_cost="{U}", type_line="Creature — Human Wizard",
                     power="1", toughness="1"),
                Face(name="Insectile Aberration", role=FaceRole.BACK, color_indicator="blue",
                     type_line="Creature — Human Insect", rules_text="Flying",
                     power="3", toughness="2"),
            ]),
        ],
    )
