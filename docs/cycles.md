# Cycles

A cycle is a family of similar cards across colors: dual lands, the five Dragonstorm
enchantments, Bloomburrow's Duos, uncommon signposts. Open the **Cycles** page from the
overview header, define the cycle once, and create its cards in one go. The cards stay
linked to the cycle (`Card.cycle`), and each stays an ordinary card you can edit freely.

## Defining a cycle

- **Colors** (`app/cycles.GROUPINGS`):
  - mono (W U B R G);
  - allied pairs (WU UB BR RG GW);
  - enemy pairs (WB UR BG RW GU);
  - all pairs;
  - shards (Bant, Esper, Grixis, Jund, Naya);
  - wedges (Abzan, Jeskai, Sultai, Mardu, Temur);
  - all three-color;
  - four-color;
  - **custom**: pick any combinations;
  - **numbered**: N colorless members.
- **Shared template:** name, mana cost, type line, rules text, flavor, power/toughness,
  rarity and frame, written once with color tokens. Optionally, each card is tagged with the
  archetype of exactly its colors (signposts).

| Token | Mono (W) | Pair (WU) | Three (WUB) |
| --- | --- | --- | --- |
| `{c}` | `{W}` | `{W}{U}` | `{W}{U}{B}` |
| `{c1}` `{c2}` … | each color's mana symbol | | |
| `{color}` / `{Color}` | white | white and blue | white, blue, and black |
| `{basic}` | Plains | Plains or Island | Plains, Island, or Swamp |
| `{basic1}` … | each basic land type | | |
| `{group}` | White | Azorius | Esper |
| `{n}` | the member's number | | |

Uppercase `{W}`, `{2}` and `{T}` stay mana and other symbols. For example, the template
"`{group} Crossing`", "`{T}: Add {c1} or {c2}.`" on allied pairs gives "Azorius Crossing —
{T}: Add {W} or {U}." and so on.

- **Members table:** before a member's card exists, you can give it its own text for any
  field, such as a unique name per Dragonstorm. That text overrides the template for that
  member, and its cell is tinted. **Use template** drops the overrides.

## Creating and keeping in step

- **Create N cards** makes a placeholder card (status "idea") for each member without one,
  in the cycle's color order, using the next collector numbers.
- If a member's card is deleted, the member shows as missing, and the button re-creates just
  that card.
- Changing the colors keeps members whose colors stay. Cards of dropped members stay in the
  set, unlinked.
- **Changing the template** once cards exist offers to update them
  (`app/cycles.template_change_plan`): each field that still matches what the old template
  produced follows the new one. A field you edited on a card stays as you wrote it. The
  table marks such cards with an amber **Edited: …** badge.
- Deleting a cycle keeps its cards and unlinks them.

The overview can group by **Cycle**, e.g. as a cycle × color matrix. A card's editor shows
a link back to its cycle.
