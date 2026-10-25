"""MSE's built-in functions.

Implemented built-ins live in the modules of this package and register themselves
with @builtin (see registry.py). Every other built-in the game and our target
styles use exists as a *placeholder* that fails when called, so the game scripts
still load (e.g. `x := masked_blend@(...)` needs the name to exist).

Behaviour follows MSE's src/script/functions/*.cpp and is checked against the real
program: tools/oracle_cases/builtins.txt -> tests/script/oracle/builtins.json.
"""
from __future__ import annotations

from ..values import HostFunction, ScriptError
from . import (choices, convert, editor, english, images, keywords, links, lists,  # noqa: F401
               patterns, tags, text)  # (importing a module registers its built-ins)
from .registry import IMPLEMENTED, builtin

__all__ = ["KNOWN_BUILTINS", "IMPLEMENTED", "builtin", "builtin_variables"]

# Every built-in the scripts call (from docs/script_survey.md), implemented or not.
KNOWN_BUILTINS = """
    add_drop_shadow add_link assert break_text check_spelling chosen combine_blend
    combined_editor contains count_chosen crop crop_image curly_quotes dimensions_of
    download_image drop_shadow english_number english_number_a english_number_multiple
    english_number_ordinal english_singular enlarge exclusive_choice exists_as_package
    exists_in_package expand_keywords fill_image filter_list filter_text flip_image
    flip_vertical forward_editor get_back_face get_card_from_uid get_card_styling
    get_cards_from_link get_front_face get_link_from_cards get_mse_dark_mode get_mse_path
    import_image import_script insert_image invert_image is_default keyword_usage length make_map
    masked_blend match match_text max min new_card new_uid nine_slice_image number_of_items
    position process_english_hints recolor_image regex_escape remove_choice remove_tag
    remove_tags replace replace_text require_choice require_exclusive_choice resize_image
    reverse rgb rgba set_alpha set_combine set_mask sort_list sort_text split_text substring
    symbol_variation tag_contents to_card_image to_color to_image to_int to_lower to_number
    to_real to_string to_text to_upper trace trim type_name version_is_older width_of
""".split()


def _placeholder(name: str) -> HostFunction:
    def not_implemented():
        raise ScriptError(f"built-in '{name}' is not implemented yet")
    return HostFunction(not_implemented, [], name)


def builtin_variables() -> dict[str, HostFunction]:
    """Every known built-in, as variables to seed a script context with."""
    out = {name: _placeholder(name) for name in KNOWN_BUILTINS}
    out.update(IMPLEMENTED)
    return out
