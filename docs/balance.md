# Balance

The **Balance** view (rail: the scales icon) estimates how strong each card is for its
cost, and how strong each archetype is for its deck. It works by reading rules text with
patterns, the same way Health finds removal and card draw. It needs no AI and no API key.
Every number is an estimate you can inspect and correct.

## How a card is scored

A card's **worth** is what its stats and effects add up to, in mana. Its **gap** is its
worth minus its mana value.

- **Creatures:**
  - the body counts (power + toughness) × 0.5, so a 2/2 is worth 2 and a 3/3 is worth 3;
  - lopsided bodies such as 5/1 count a little less;
  - bodies costing more than 4 get a small discount.
- **Noncreature spells** start at 0.5 and add their effects.
- **Keywords** add their value. For example, Flying adds 1 (only half on a 1-power
  creature), Deathtouch 0.5 and Vigilance 0.25.
- **Effects** that are recognized:
  - damage, destroy, exile, -N/-N, fight, bounce, counter;
  - draw, gain life, tokens, +1/+1 counters, pump;
  - Surveil, Scry, mana abilities.
  - An effect behind an activated ability ("{2}, {T}: Surveil 2.") counts 60%.
  - One behind a condition ("Whenever you cast a spell, …") counts 75%.
  - Effects when the card enters count fully.
- **Your own mechanics** count their **value** (default 0.5), which you set on the mechanic.
- **Lines the scorer doesn't understand** are listed under *Not scored*, so you always
  know when a worth is partial. If a line matters, give the card an **adjustment** (in
  mana, with a note) in its Balance panel.

Examples:

| Card | Worth | Cost | Verdict |
|---|---|---|---|
| 2/2 for {1}{W} | 2 | 2 | On curve |
| 2/2 Flying for {2}{U} | 2.75 | 3 | On curve |
| "Deal 3 damage to any target" for {R} | 2.5 | 1 | Above curve |
| 3/3 for {3}{G}, "When it enters, draw a card" | 4 | 4 | On curve |

## Verdicts and rarity

A card is flagged when its gap goes past its rarity's tolerance:

- **common:** ±1 mana;
- **uncommon:** ±1.5;
- **rare and mythic:** only above +2. Weak rares aren't flagged, because they're often
  built-around cards.

Each card also shows **vs. set**: its gap compared with your set's typical gap. If your
whole set runs a bit hot or cold, you can see which cards stand out from the rest of your
set as well as from the norms.

## Norms

The **Norms** tab lists every value scores use. Change one for this set and every score
follows. **Reset** puts the default back. Overrides are saved in the set's `set.json`
under `balance`.

## Archetypes

The **Archetypes** tab ranks archetypes by a 0–100 strength made of three parts:

- **Playables (40%):** cards tagged to the archetype against its targets. Without
  targets, they're compared with the set's typical archetype.
- **Power (30%):** the average gap of its cards, compared with the other archetypes.
- **Key roles (30%):** whether it has each role it needs. The default roles are
  removal, two-drops and card draw. Open an archetype's row to change its roles and see
  its curve.

## The editor and Health

- The card editor shows a **Balance** badge ("On curve", "+1.5 above"). It updates as
  you edit, and clicking it opens the card in Balance.
- Health has two checks you can tune:
  - **Cards off curve for their rarity;**
  - **Weak archetypes** (below a strength of 60, or missing a key role).
