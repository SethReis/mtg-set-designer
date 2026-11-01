# Mechanics

A mechanic is defined once and every card follows the definition. Reminder text is drawn
from it, never stored on cards. Open the **Mechanics** page from the overview header.

## The definition (`model.Mechanic`)

| Field | Meaning |
| --- | --- |
| Name | "Want", "Bloodpact", "Landfall" |
| Kind | keyword (Flying, Cycling {2}), ability word (Landfall — …) or keyword action (Scry 2, Surveil 1) |
| Parameter | none, or MSE's cost / mana / number / name / action, e.g. "Cycling {2}" |
| Reminder text | shown in parentheses after the mechanic; `{cost}` (or `{param}`) stands for the parameter's value |
| Show reminder text | always, on commons only, on the first card of each color, or never |
| Word forms | other forms that also count: Wanted, Wants. **Add common forms** suggests them (`app/mechanics.suggest_forms`) |
| Roles | what the mechanic does for the Health page (evasion, removal, ...): every card with it counts toward these (`docs/health.md`) |
| Design intent | notes for yourself |

Fields save when you leave them. Mechanics are set-wide, so each save restarts the
renderer's script environment.

## Where it's used

A card uses a mechanic when its rules text has the name or a word form as a whole word
(`mse/mechanics.words_pattern`): "Wanted" counts for "Want", "Wantonly" doesn't. The page
lists those cards with the matching sentences highlighted and counts them by color and
rarity. The overview can group by **Mechanic** too, e.g. as a mechanic × rarity matrix.
`Card.mechanics` keeps the ids up to date whenever rules text or mechanics change.

Reminder text goes after the **first mention** on a card, whether that's the name or a
word form: "Want target creature (…)", and "if that creature is Wanted (…)" on a card that
never says "Want". Later mentions on the same card get none.
- Word forms are registered as MSE keywords of their own, with the same reminder text
  (`mse/mechanics.mechanic_keywords`).
- This only applies to mechanics without a parameter, because a form like "Wanted" has no
  value to fill in.

## Renaming

When the name changes and cards mention it, a dialog shows the rules-text changes. You can
update them or keep the card text. Forms follow the new name: Want → Hunt turns "Wanted" into
"Hunted". Capitalization is kept. (`app/mechanics.rename_plan`, `SetSession.rename_mechanic`.)

## Per-card reminder text

In the card editor, a **Mechanics** row has one control per mechanic on the card:
- *as policy*, the default;
- *show reminder*;
- *hide reminder*.

This is stored as `Card.reminders` and wins over the mechanic's policy
(`mse/mechanics.reminder_choices`). The choice becomes MSE's own per-mention `<kw-1>` /
`<kw-0>` switch, so the picture is exactly what MSE draws (tested with real MSE).

## Ability words: variants and shared phrases

Ability words (Flurry, Renew, Settled) have no reminder text. The name is set in italics
(MSE does this for the "pseudo" keyword mode), followed by a long dash and an ability whose
**throughline is shared** while the rest varies. For an ability word, the Mechanics page
shows two things in place of reminder text and policy:

- **Shared phrases**: wording written once, e.g. `condition` = "you control four or more
  lands that share a land type".
- **Variants**: the shapes the ability takes, as templates for the text after the dash.
  - `{effect}`, `{cost}`, `{trigger}` or any lowercase `{name}` is a **slot**, filled per
    card. Uppercase `{G}`, `{T}` and `{2}` stay symbols.
  - `{=condition}` inserts a shared phrase.

  Settled, for example:

  | Variant | Template |
  | --- | --- |
  | Activated | `{cost}: {effect}. Activate only if {=condition}.` |
  | Landfall | `Whenever a land you control enters, if {=shares}, {effect}` |
  | Trigger | `{trigger}, if {=condition}, {effect}` |

Cards keep their full text. Each line starting with "Settled —" (a typed `-` or `--` works)
is matched against the variants in order, and the first that fits wins
(`app/ability_words.parse_line`). The usage list shows each line's variant and slot
values. Amber badges mark **Doesn't follow any variant** and **Unfinished** (a `[slot]`
placeholder is still there). The editor's Mechanics row shows the same note.

**Changing a phrase or a variant** offers to update the cards
(`app/ability_words.definition_change_plan`):
- each card line is rebuilt from its own values with the new wording;
- only lines the change actually reaches are touched (a phrase edit leaves variants that
  don't use it alone);
- slots dropped from a variant are named in the dialog;
- lines that follow no variant are left as they are.

## Typing

In the rules text, typing the start of a mechanic suggests it. Mechanics with a parameter
come with a placeholder (`{1}` for cost or mana, `1` for a number). Each mechanic also has a
button in the symbol palette.

An ability word with variants is suggested once per variant ("Settled — Activated", …),
and its palette button opens a small menu. Choosing one inserts the whole line with its
phrases written in, and selects the first placeholder (`[cost]`), so you type straight over
it.
