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
| Design intent | notes for yourself |

Fields save when you leave them. Mechanics are set-wide, so each save restarts the
renderer's script environment.

## Where it's used

A card uses a mechanic when its rules text has the name or a word form as a whole word
(`mse/mechanics.words_pattern`): "Wanted" counts for "Want", "Wantonly" doesn't. The page
lists those cards with the matching sentences highlighted and counts them by color and
rarity. The overview can group by **Mechanic** too, e.g. as a mechanic × rarity matrix.
`Card.mechanics` keeps the ids up to date whenever rules text or mechanics change.

Reminder text is drawn after the **name** only, as on real cards. "Want target creature
(…)" gets it; "a Wanted creature" doesn't.

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

## Typing

In the rules text, typing the start of a mechanic suggests it. Mechanics with a parameter
come with a placeholder (`{1}` for cost or mana, `1` for a number). Each mechanic also has a
button in the symbol palette.
