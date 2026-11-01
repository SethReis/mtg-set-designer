# Set health

The **Health** page (`/set/health`) shows where the set is lopsided. To open it, click the
chip in the overview header. The chip reads "N warnings" in amber, or "Healthy" in green.
Everything is computed when the page opens, from the cards' **front faces**.

The code is in `src/setdesigner/app/health/` (pure, tested) and `ui/health_page.py`.

## Warnings

Built-in checks (`app/health/checks.CHECKS`) each produce warnings. A warning that names
cards opens to show them as chips, and clicking a chip opens the card in the editor.

| Check | Default |
| --- | --- |
| Common removal per color | ≥ 2 |
| Removal per color at common or uncommon | ≥ 1 |
| Creatures among each color's commons | ≥ 55 % |
| Common two-drop creatures per color | ≥ 2 |
| Commons balanced across colors | within 2 of the average |
| Cards per rarity against the set's targets (Set panel) | — |
| Wordy commons | over 40 words |
| Complex commons | over 3 abilities |
| Each mechanic on enough commons | ≥ 3 |
| Archetypes against their targets | — |
| Cycles with missing members | — |
| Ability-word lines that follow a variant | — |
| Fixing at common/uncommon, when the set has multicolor cards | ≥ 5 |

**Tune checks** switches checks off and changes thresholds. The settings are saved in
`set.json` under `health` (check id → `enabled`, `threshold`). Leave a threshold empty to
use the default. A set without cards shows no warnings.

## Roles

Some checks and the roles table need to know what a card *does*. Roles are detected from
the rules text, with reminder text left out and the card's name read as "this"
(`app/health/roles.py`):

| Role | Detected from (examples) |
| --- | --- |
| Removal | destroy/exile target …, deals N damage to any target, gets -N/-N, fights, bounce, "can't attack or block" auras |
| Counterspell | counter target … spell |
| Card draw | draw a card / N cards, investigate, connive |
| Ramp | search for a basic land onto the battlefield; `{T}: Add` on nonland cards |
| Fixing | one mana of any color, Add {X} or {Y}, land searches, lands that make two colors |
| Evasion | flying, menace, trample, skulk, shadow …, can't be blocked |
| Combat trick | an instant (or flash card) giving +N/+N or protection to target creature |
| Makes tokens | create … token |
| Lifegain | gain N life, lifelink |

Your own mechanics aren't real Magic templating, so give them roles on the Mechanics page
(**Roles**, `Mechanic.roles`). For example, tag a "Skyward" keyword with Evasion, or a "Hunt"
keyword action that fights with Removal. Every card using the mechanic then counts toward
those roles. In the editor, these roles show a mechanic icon and "From Skyward".

Detection knows common templating, not every card. When it gets a card wrong, correct it
in the editor's **Roles** row, under the rules text:
- **×** on a detected role removes it; it stays visible, struck through, so a click
  restores it.
- **+** adds a role that wasn't detected. Added roles are marked with a person icon.

These corrections are saved on the card as `role_overrides` (role → true/false).

## Sections

- **Mana curve:** a stacked bar per mana value by color, filtered by rarity. Lands aren't
  counted.
- **Cards per color and rarity**, with rarity totals against the Set panel's targets. Also
  the share of creatures among each color's commons, and the average common creature
  (power/toughness) per mana value.
- **Roles per color:** a color × role table at a chosen rarity. Click a number to list the
  cards. Colors with no removal are highlighted.
- **Mechanics, archetypes and cycles:**
  - each mechanic's cards by color and rarity;
  - archetype counts against their targets;
  - cycles made / total, with the members still missing;
  - ability-word lines that follow none of the variants.
- **Complexity:** average words and abilities per rarity, and the wordiest commons. Words
  are counted on rules text without reminder text, and abilities are non-empty lines.
