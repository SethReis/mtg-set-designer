"""What each card layout looks like, and validation of cards against it."""
from __future__ import annotations

from dataclasses import dataclass

from .card import Card, FaceRole, Layout


@dataclass(frozen=True)
class LayoutSpec:
    face_roles: tuple[FaceRole, ...]                 # one per face, in order
    # face index -> Face fields that must be empty (e.g. a transform back has no cost)
    forbidden: dict[int, tuple[str, ...]]
    # MSE relation each face has towards the other ("Front Face" / "Back Face")
    mse_relations: tuple[str, ...] = ()


LAYOUTS: dict[Layout, LayoutSpec] = {
    Layout.NORMAL: LayoutSpec((FaceRole.FRONT,), {}),
    Layout.TRANSFORM: LayoutSpec((FaceRole.FRONT, FaceRole.BACK), {1: ("mana_cost",)},
                                 ("Front Face", "Back Face")),
    Layout.MDFC: LayoutSpec((FaceRole.FRONT, FaceRole.BACK), {},
                            ("Front Face", "Back Face")),
}


def validate_card(card: Card) -> list[str]:
    """Problems with a card's structure, as readable messages (empty if fine)."""
    spec = LAYOUTS[card.layout]
    problems = []
    if len(card.faces) != len(spec.face_roles):
        problems.append(f"{card.layout.value} cards need {len(spec.face_roles)} face(s), "
                        f"this one has {len(card.faces)}")
    for index, face in card.iter_faces():
        label = f"face {index + 1}" if len(card.faces) > 1 else "card"
        if not face.name.strip():
            problems.append(f"{label} has no name")
        if index < len(spec.face_roles) and face.role != spec.face_roles[index]:
            problems.append(f"{label} should be the {spec.face_roles[index].value}, not the {face.role.value}")
        for field in spec.forbidden.get(index, ()):
            if getattr(face, field):
                problems.append(f"{label} ({face.role.value}) of a {card.layout.value} card "
                                f"should not have a {field.replace('_', ' ')}")
        if (face.power is None) != (face.toughness is None):
            problems.append(f"{label} has power or toughness but not both")
    return problems
