# MSE script interpreter: proposed build order

Drawn from `docs/script_survey.md` (regenerate with `python tools/survey_scripts.py`).
Each stage is testable on its own, using real snippets from the packages as test cases.

## Key findings

- **The retro styles need nothing beyond M15.** All four reach 29–30 built-ins, every one of
  which M15 also needs. The one exception is `set_combine` (magic-old-abu only, a single image op).
  Once M15 renders, the retro frames really are a small step, as the handoff guessed.
- M15 Main reaches **62 built-ins** and **about 560 game-script functions**. The retro styles reach
  about 110–140 game functions.
- The language is small. Script is expression-oriented: `if/then/else` (about 2,800),
  `:=` (about 4,000), closures `{ ... }` (about 3,900), member access `a.b` (about 3,200),
  partial application `f@(named: args)` (about 1,000), indexing `x[...]` and `x.0`,
  list/map literals `[a, b]` / `[k: v]`, `for x from a to b do` (129), `for each x in xs do` (31),
  string interpolation `"..{expr}.."` (140), `case ... of` (5), `and/or/not/xor`, `mod`, `or else`.
- The `match` / `filter_text` / `replace` counts are inflated by `magic.mse-game/language_map`
  (616 of the 628 `match@(` uses), which holds per-language regex tables. For English only, we
  still have to parse that file but rarely evaluate most of it.
- **Regex dialect matters.** Patterns use `(?i)` and POSIX classes like `[[:space:]]`, which
  Python's `re` doesn't support. We need a small translation layer, or the `regex` package.
- **Tagged text** (`<sym>`, `<soft>`, `<atom-sep>`, `<word-list-...>`, `<error-spelling>`) runs
  through the text functions (`remove_tag`, `tag_contents`, ...). It's the biggest semantic area
  after images, and it's needed for rules text and type lines.
- `+` is overloaded: it adds numbers, concatenates strings and lists, merges maps, and **composes
  functions** (`remove_tags + trim + replace@(...)`).

## Stages

**A. Core expressions. DONE** (`src/setdesigner/mse/script/`). The tokenizer and parser cover
the **whole** language; the grammar mirrors MSE's own `src/script/parser.cpp`. All 2,172 real
snippets parse (`python tools/check_script_parse.py`, `tests/script/test_corpus.py`). The
evaluator handles literals, interpolation, `:=`, sequences, `if`, `case`, boolean/arithmetic/
comparison operators, `or else`, member/index reads, list/map literals and calls to host
(Python) functions. Things learned from the corpus:
- Operators are checked *before* the "new line = new statement" rule, so lines starting
  with `and` / `or` / `+` continue the previous expression, even inside `( )` and `{ }`.
- A `{ ... }` property value is a *template*: it's parsed like the inside of a string, and a lone
  `{expr}` keeps the expression's type (so `top: { 30 + x }` is a number).
- `add cards script:` / `update cards script:` are key containers (`name:`, `script:`), not code.
**B. Functions and data. DONE.** Value rules are now **verified against real MSE**:
`tools/mse_oracle.py` runs `tools/oracle_cases/*.txt` through `magicseteditor.com --cli --raw`,
and `tests/script/test_oracle.py` checks the recorded results in `tests/script/oracle/*.json`.
Re-run the oracle after adding cases.
- Runtime model as in MSE's `context.cpp`: one variable table with scope levels. Calls open a scope,
  `:=` inside a call is undone on return, and reads are *dynamic* (callees see the caller's variables).
- `{ ... }` functions, `f(args)` (only the first unnamed argument is used, as `input`), `f@(...)`
  defaults (they apply only when the call didn't pass that argument), `f + g` composition,
  `for each` / `for from to` (inclusive; results `+`-accumulated from nil), calling nil returns
  `input`, a 500-level depth limit.
- Python functions are wrapped as `HostFunction`s, which read their parameters from script
  variables by name, like MSE's built-ins.
- Missing members are delayed `ErrorValue`s. `or else` replaces those only: not nil, and not
  raised errors (`unset_var or else 1` is still an error in MSE).
- Surprises the oracle caught: numbers never convert to booleans (`if 1` is an error);
  `a and b` / `a or b` return `b` itself; `/` is always a double (printed with `%g`); `<` is numeric
  only; `==` never converts between types (`1 == "1"` and `nil == ""` are false) and ignores map keys;
  `\<` in strings is a special "escaped <" character.
- `game.load_game(root, style)` loads `magic.mse-game`'s init script and then a style's (about
  1,800–2,000 definitions in 0.5 s), with `set` seeded from the game's `set_fields` defaults and
  `card` = nil. All five target styles load. The only failures are 3 game definitions that call
  `replace` / `length` at load time; they need stage C.
- All built-ins exist as placeholders in `builtins.py` (`KNOWN_BUILTINS`) that fail when called;
  stage C fills `IMPLEMENTED`.
- **Known deviation:** maps are Python dicts, so `[a: 1] + [a: 2]` can't keep the duplicate key
  (MSE prints `["a":1,"a":2]`; lookups agree, since the first map wins). Mixed lists like
  `[1, a: 2]` aren't supported yet.

**C. Text built-ins. DONE** (`src/setdesigner/mse/script/builtins/`). About 220 oracle cases in
`tools/oracle_cases/builtins.txt` all match real MSE, the game's own `unit_tests` pass
(`tests/script/test_unit_tests.py`), and the game plus all 5 styles load with **0** failures.
- Implemented: conversions (`to_int/real/number/string/boolean/code/text`, `type_name`), strings
  (`to_upper/lower/title`, `trim`, `substring`, `contains`, `reverse`, `regex_escape`, `trace`),
  `sort_text` with MSE's full order-spec language (`spec_sort.py`, a port of `util/spec_sort.cpp`:
  `(WUBRG)` color-wheel cycles, `<...>`, `[...]`, `in_place`, `pattern`, ...), regex functions
  (`match`, `filter_text`, `break_text`, `split_text`, `replace` with sed-style `\1`/`&` or a
  function, `in_context`, `recursive`), tags (`remove_tag(s)`, `tag_contents`), lists (`length`,
  `number_of_items`, `position`, `filter_list`, `sort_list`), multiple choice (`chosen`,
  `count_chosen`, `require/exclusive/require_exclusive/remove_choice`), English (`english_number*`,
  `english_singular`), and the keyword-like `min`, `max`, `assert` (special forms in the evaluator).
- Regex: the `regex` package with MULTILINE | DOTALL, matching boost's defaults (checked).
- Host functions can take a `script` parameter (a `Caller`) to call script functions back, read
  variables (`choice1`, `choice2`, ...) and record warnings (`ctx.warnings`).
- Composition `f + g` runs each half in its own scope (found by the oracle: otherwise one
  `replace@(...)`'s bindings leak into the next).
- Simplifications: choice functions ignore `last_change` (no live editor; the first listed choice
  wins); `english_*` don't yet handle `<param-...>` keyword tags; `to_string` ignores `format`.

Originally planned for stage C: `match`, `contains`, `replace`, `filter_text`,
`break_text`, `split_text`, `sort_text`, `trim`, `to_upper/lower`, `substring`, `length`,
`to_int/to_number/to_text`, `english_number`, `remove_tag(s)`, `tag_contents`, `max/min`,
`number_of_items`, `type_name`, `reverse`, plus the regex dialect shim.

**D. Context objects. DONE.** See `docs/data_model.md`. `card`, `set`, `styling`, `extra_card`
and `stylesheet` are objects (`mse/objects.py`) whose fields are computed lazily by the game's and
style's own field scripts, run by `mse/environment.py` (`ScriptEnvironment`). The fixture set is
loaded into real MSE, and all 69 recorded card/set/link cases (`tools/oracle_cases/cards.txt`)
match: card color, cmc, tagged type line, P/T, color identity, card numbers, links
(`get_front_face`, `get_back_face`, `get_cards_from_link`, `get_link_from_cards`,
`get_card_from_uid`). Also added: `combined_editor` (read side), `curly_quotes`, `is_default`,
`check_spelling` (identity), sets usable as card collections in `length` / `number_of_items` /
`position(order_by, filter)`, and calling a delayed error returns it (MSE).
- Field scripts run in an *isolated* scope (`Context.open_isolated_scope`), so computing one
  card's field from inside another card's script can't see that script's local variables
  (MSE reads stored values there; our values are computed lazily, so this keeps them identical).
- A field script that fails falls back to the unscripted value with a warning
  (`card.warnings`). Remaining causes: `expand_keywords` (rules text, stage F) and `rgb` /
  colors (stage E).
- Deviations: field values are plain strings, not MSE "value" objects (`type_name` says
  "value" in MSE); `is_default` is always true; `last_change` is "".

**E. Colors and images. DONE** (`script/images.py`, `script/builtins/images.py`). Images are
lazy recipes (MSE's "generated images") turned into pixels at a requested size; the pixel math
is MSE's own integer formulas in numpy. A `Raster` is RGB plus an *optional* alpha, as in MSE.
- Implemented: `rgb` / `rgba` (special forms), `to_color`, `to_image`, `linear_blend`,
  `masked_blend`, `combine_blend` (all 24 modes), `set_mask`, `set_alpha`, `set_combine`,
  `saturate`, `invert_image`, `recolor_image` (1- and 4-color), `enlarge`, `crop`, `crop_image`,
  `flip_horizontal/vertical`, `flip_image`, `rotate`, `drop_shadow`, `add_drop_shadow`,
  `insert_image`, `resize_image`, `fill_image`, `nine_slice_image`, `import_image`,
  `exists_in_package`, `dimensions_of`, `width_of`, `height_of`, `get_mse_path`.
- **Verified against real MSE**: `tools/oracle_cases/images.txt` (`#! images` mode) has MSE write
  each image with `write_image_file`; `tests/script/test_image_oracle.py` compares pixels.
  Point-wise operations match exactly, including M15's real `card_background()` for green,
  hybrid, multicolor and artifact cards (within 1/255). Resampling (resize, conform, nine-slice)
  uses Pillow's Hamming filter, the closest to MSE's own (max 13, mean ≤ 0.6 per channel);
  shadows use a separable Gaussian (max 11, mean 0.1).
- `env.style_value(card, "card color", "image")` runs a stylesheet entry's script for a card;
  `tools/render_frames.py OUT` renders the frame of every card face for eyeballing.
- Found while recording: MSE crashes on `drop_shadow(..., blur_radius: 0)`.
- Differences on purpose: blends of images of different sizes resample instead of failing.
  Still placeholders: `symbol_variation` and `built_in_image` (symbol files belong with the
  renderer), `to_card_image`, `download_image`.
- `write_image_file(input: card)` in the CLI renders a whole card: the oracle for the renderer.

**F. Keywords and rules text. DONE** (`mse/keywords.py`, `script/builtins/keywords.py`,
`mse/mechanics.py`). A port of MSE's `data/keyword.cpp`: keyword regexes from `match` strings
(`<atom-param>` groups, separator eating, whole words, case-insensitive), candidates sorted by
position, then keywords with parameters before plain ones (verified: the game's `<prefix>walk`
beats a plain "Shroudwalk"), then longer; `<atom>` protection; `<kw-0/1/a/A>` handling;
`param1…` objects; and the game's own `condition` / `default_expand` / `combine` scripts. Plus
`process_english_hints` and the `<param-…>` / `<hint-…>` forms of `english_number*`.
- **Verified against real MSE**: `tools/oracle_cases/keywords.txt` loads
  `tests/fixtures/keyword_project.py` (18 cards: core / expert / action / pseudo keywords, dash
  separators, lower case, non-matches, CARDNAME, and our mechanics under every reminder policy).
  `rule text` and `text` match exactly, except one card where MSE's spellchecker marks a made-up
  word (we don't spellcheck).
- Our `Mechanic`s are the set's own keywords; reminder policies become `<kw-1>`/`<kw-0>` tags,
  which MSE honors too (see `docs/data_model.md`). Rules-text mana `{2}{W}` is mapped to MSE's
  `<sym>2W</sym>`.
- **No field script falls back any more** on any fixture card.
- Not done: keyword usage statistics (`keyword_usage` returns ""), spellchecking.

**Renderer. DONE**: see `docs/renderer.md`. Whole cards match MSE's own renders (16 cards
checked region by region); also added the `lightmap relative` combine mode (formula matched
exactly against MSE) and `symbol_variation` (our own SVG/PNG set symbol).

**G. Rarely needed or stub-able:** `check_spelling` (identity), `curly_quotes`, `expand_keywords` /
`process_english_hints` (these overlap with our own mechanics system), `new_card` / `new_uid` /
`combined_editor` (editor-only), `get_mse_path`, `trace`.
