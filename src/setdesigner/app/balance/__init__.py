"""Balance: how strong each card is for its cost, and each archetype for its deck.
Rule-based (patterns over the rules text), with norms a set can override."""
from .archetypes import DEFAULT_ROLES, ROLE_LABELS, ArchetypeStrength, archetype_strength, key_roles
from .norms import GROUPS, NORMS, defaults, norms
from .score import Score, score, scores, set_offset, similar

__all__ = ["DEFAULT_ROLES", "ROLE_LABELS", "ArchetypeStrength", "archetype_strength", "key_roles",
           "GROUPS", "NORMS", "defaults", "norms", "Score", "score", "scores", "set_offset", "similar"]
