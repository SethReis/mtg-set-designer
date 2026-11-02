# Voice

- **Sentence case** everywhere: "New card", "Tune checks", "Show reminder text". Never
  Title Case, and never uppercase except the data-table header.
- **Labels are nouns, buttons are verbs.**
  - Labels: "Mana cost", "Roles".
  - Buttons: "Create 5 cards", "Add archetype". Buttons that affect cards say how many.
- **Use Magic's words:** mana value, rules text, reminder text, ability word, signpost,
  commons. Avoid the program's words (no "entity", "record" or "item").
- **Helper text** is one line under the field in `--text-faint`, and says what the field
  does to the cards: "Shown in parentheses after the mechanic on cards."
- **Empty states** have a title that says what's missing ("No cycles yet") and a hint that
  says why you'd want one ("Dual lands, signposts, Dragonstorms: made once from a
  template").
- **Counts** read naturally: "1 card", "3 cards", "4 of 5 made", "Common · 23 / 20".
  Targets always come after a slash.
- **Errors** say what happened and what to do: "MSE couldn't draw this card. Check the
  rules text for unbalanced brackets." No codes and no stack traces in the UI.
- **No exclamation marks**, no "Oops" and no emoji.
