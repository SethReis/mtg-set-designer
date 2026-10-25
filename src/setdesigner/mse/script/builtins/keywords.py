"""expand_keywords and keyword_usage (the engine is setdesigner/mse/keywords.py).

The keywords come from the `set` variable: a SetObject's environment knows the
game's keywords plus our project's mechanics. Without one, text is returned with
only old expansion output removed.
"""
from __future__ import annotations

from ..values import to_str
from .registry import builtin


@builtin("expand_keywords")
def expand_keywords(input, script, condition=None, default_expand=None, combine=None):
    from ...keywords import Expander, KeywordDatabase, remove_keyword_tags
    set_obj = script.var("set")
    env = getattr(set_obj, "env", None)
    if env is None:
        return remove_keyword_tags(to_str(input))
    db: KeywordDatabase = env.keyword_db()
    return Expander(db, script, condition, default_expand, combine).expand(to_str(input))


@builtin("keyword_usage")
def keyword_usage(script, unique=False):
    """MSE lists the keywords a card uses (from statistics we don't keep)."""
    return ""
