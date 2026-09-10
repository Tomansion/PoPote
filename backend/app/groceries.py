"""Turn an event's plan into one shopping list.

The arithmetic is the whole feature: a recipe written for four, cooked for
eleven, on three separate evenings, has to come out of this as one line with
one quantity. Everything else — the aisles, the ticking, the price estimate —
hangs off the list this module produces.
"""

import hashlib
import logging
import re
from typing import Optional

from .aisles import AISLES, detect_aisle
from .models import Event, EventPlan, GroceryItem, GrocerySource, Recipe, SLOTS

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


def _item_key(name: str, unit: str) -> str:
    """A short, URL-safe, stable id for one line of the list.

    It goes in the path of the public "tick this box" call, so it cannot be
    the ingredient name itself — names contain slashes, accents and spaces.
    Hashing name+unit also means regenerating the list keeps the same key for
    the same line, which is what preserves the boxes already ticked.
    """
    digest = hashlib.sha1(f"{_normalise(name)}|{_normalise(unit)}".encode("utf-8"))
    return digest.hexdigest()[:12]


def _aisle_rank(aisle: str) -> int:
    """Aisles sort in shopping order, not alphabetically — the table in
    aisles.py is written in roughly the order you walk a supermarket."""
    try:
        return AISLES.index(aisle)
    except ValueError:
        return len(AISLES)


def build_items(
    event: Event, plan: EventPlan, recipes_by_id: dict[str, Recipe]
) -> list[GroceryItem]:
    """Aggregate everything the plan calls for into one list of lines.

    A recipe that has since been deleted — or that belongs to a member who has
    left — is skipped rather than guessed at: the plan still remembers its
    name, but not what went into it.
    """
    accumulator: dict[str, GroceryItem] = {}

    for day in sorted(plan.days):
        for slot in SLOTS:
            meal = plan.days[day].get(slot)
            if meal is None or meal.skipped:
                continue

            for planned in meal.recipes:
                recipe = recipes_by_id.get(planned.recipe_id)
                if recipe is None:
                    logger.info(
                        "Skipping %r in the list for %s: recipe unavailable",
                        planned.name,
                        event.id,
                    )
                    continue

                # Quantities scale by the portions this dish is planned for,
                # never by the slot's headcount: the two differ whenever one
                # meal of three is only for the people who eat fish. The slot
                # headcount is the default the planner offers, and by the time
                # a meal is stored that choice has already been made.
                scale = planned.servings / (recipe.servings or 1)

                for ingredient in recipe.ingredients:
                    if not ingredient.name.strip():
                        continue
                    _add(
                        accumulator,
                        name=ingredient.name.strip(),
                        unit=ingredient.unit.strip(),
                        aisle=ingredient.aisle or detect_aisle(ingredient.name),
                        quantity=(
                            None
                            if ingredient.quantity is None
                            else ingredient.quantity * scale
                        ),
                        source=GrocerySource(
                            recipe_name=planned.name or recipe.name,
                            quantity=(
                                None
                                if ingredient.quantity is None
                                else round(ingredient.quantity * scale, 2)
                            ),
                            day=day,
                            slot=slot,
                        ),
                    )

    return sorted(
        accumulator.values(),
        key=lambda item: (_aisle_rank(item.aisle), _normalise(item.name)),
    )


def _add(
    accumulator: dict[str, GroceryItem],
    *,
    name: str,
    unit: str,
    aisle: str,
    quantity: Optional[float],
    source: GrocerySource,
) -> None:
    """Fold one ingredient into the running total for its line.

    Lines are keyed by name *and* unit, so "200 g de tomates" and "3 tomates"
    stay apart. Merging them would need a density table per ingredient to be
    anything but wrong, and two honest lines beat one invented one.
    """
    key = _item_key(name, unit)
    item = accumulator.get(key)

    if item is None:
        accumulator[key] = GroceryItem(
            key=key,
            name=name,
            quantity=None if quantity is None else round(quantity, 2),
            unit=unit,
            aisle=aisle or "autre",
            sources=[source],
        )
        return

    if quantity is not None:
        # An unquantified mention ("sel") leaves the total alone rather than
        # counting as zero, so one such line never blanks out a real quantity.
        item.quantity = round((item.quantity or 0) + quantity, 2)
    item.sources.append(source)
