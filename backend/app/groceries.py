"""Turn an event's plan into one shopping list.

The arithmetic is the whole feature: a recipe written for four, cooked for
eleven, on three separate evenings, has to come out of this as one line with
one quantity. Everything else — the aisles, the ticking, the price estimate —
hangs off the list this module produces.

Merging happens in two passes. The first is mechanical and always runs: units
are converted to one base per family (kg into g, cl into ml) and names are
compared with case, accents and plurals ignored, so "Oignon · 1 u." and
"oignons · 4 unités" are one line of five before anything clever happens. The
second pass is the model's (see `ai.fuse_ingredients`) and catches what a
table cannot — "blancs de poulet" beside "poulet", "huile d'olive vierge
extra" beside "huile d'olive". It is optional: with no API key, or a failed
call, the list is simply the first pass's.
"""

import hashlib
import logging
import re
import unicodedata
from collections import Counter
from typing import Iterable, Optional

from .aisles import AISLES, detect_aisle
from .models import Event, EventPlan, GroceryItem, GrocerySource, Recipe, SLOTS

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")

# Written the way people type them, read back as one. The empty string maps to
# "u." only when there is a number in front of it — "sel" with no quantity has
# no unit at all, and printing "u." after it would be nonsense.
_UNIT_SYNONYMS = {
    "u": "u.", "u.": "u.", "unite": "u.", "unites": "u.", "unit": "u.",
    "piece": "u.", "pieces": "u.", "pc": "u.", "pcs": "u.", "pce": "u.",
    "g": "g", "gr": "g", "gramme": "g", "grammes": "g",
    "kg": "kg", "kilo": "kg", "kilos": "kg",
    "kilogramme": "kg", "kilogrammes": "kg",
    "mg": "mg", "milligramme": "mg", "milligrammes": "mg",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml",
    "cl": "cl", "centilitre": "cl", "centilitres": "cl",
    "dl": "dl", "decilitre": "dl", "decilitres": "dl",
    "l": "l", "litre": "l", "litres": "l",
    "cas": "c. à s.", "c a s": "c. à s.", "c. a s.": "c. à s.",
    "cuillere a soupe": "c. à s.", "cuilleres a soupe": "c. à s.",
    "cac": "c. à c.", "c a c": "c. à c.", "c. a c.": "c. à c.",
    "cuillere a cafe": "c. à c.", "cuilleres a cafe": "c. à c.",
    "pincee": "pincée", "pincees": "pincée",
    "sachet": "sachet", "sachets": "sachet",
    "boite": "boîte", "boites": "boîte",
    "gousse": "gousse", "gousses": "gousse",
    "tranche": "tranche", "tranches": "tranche",
    "botte": "botte", "bottes": "botte",
    "brin": "brin", "brins": "brin",
}

# Only within a family. Grams and units are never added together: that needs a
# density per ingredient to be anything but wrong, so they stay two lines.
_UNIT_BASE = {
    "mg": ("g", 0.001),
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "cl": ("ml", 10.0),
    "dl": ("ml", 100.0),
    "l": ("ml", 1000.0),
}


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


def _fold(text: str) -> str:
    """Lowercase, unaccented, ligature-free — for comparing, never for showing."""
    lowered = _normalise(text).replace("œ", "oe").replace("æ", "ae")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _singular(word: str) -> str:
    """Drop a French plural ending, for matching only.

    Crude on purpose: it is applied to both sides of every comparison, so a
    word it mangles ("ananas" -> "anana") is mangled identically each time and
    still matches itself. Short words are left alone, which keeps "des", "aux"
    and "ail" intact.
    """
    if len(word) > 3 and word[-1] in "sx" and not word.endswith("ss"):
        return word[:-1]
    return word


def _name_key(name: str) -> str:
    """The form two ingredient names have to share to count as one line."""
    return " ".join(_singular(word) for word in _fold(name).split())


def canonical_unit(unit: str, has_quantity: bool) -> str:
    """The unit as it will be stored: one spelling per unit, base of its family."""
    folded = _fold(unit).replace(".", "").strip()
    if not folded:
        return "u." if has_quantity else ""
    named = _UNIT_SYNONYMS.get(folded, _normalise(unit))
    base, _ = _UNIT_BASE.get(named, (named, 1.0))
    return base


def _to_base(quantity: Optional[float], unit: str) -> tuple[Optional[float], str]:
    """Convert one measurement into its family's base unit (kg -> g, l -> ml)."""
    folded = _fold(unit).replace(".", "").strip()
    named = _UNIT_SYNONYMS.get(folded, _normalise(unit)) if folded else ""
    base, factor = _UNIT_BASE.get(named, (named, 1.0))

    if not base:
        base = "u." if quantity is not None else ""
    if quantity is None:
        return None, base
    return round(quantity * factor, 4), base


def _display_name(name: str) -> str:
    """The line as it will be written on the list.

    Only the first letter, and only when it is not already a capital: a
    shopping list of "citron / Oignon / Sel" reads like three different
    people wrote it, which is exactly what happened.
    """
    stripped = name.strip()
    return stripped[:1].upper() + stripped[1:] if stripped else stripped


def _item_key(name: str, unit: str) -> str:
    """A short, URL-safe, stable id for one line of the list.

    It goes in the path of the public "tick this box" call, so it cannot be
    the ingredient name itself — names contain slashes, accents and spaces.
    Hashing the *comparison* forms of name and unit also means regenerating
    the list keeps the same key for the same line, which is what preserves the
    boxes already ticked and the people already assigned to them.
    """
    digest = hashlib.sha1(f"{_name_key(name)}|{_fold(unit)}".encode("utf-8"))
    return digest.hexdigest()[:12]


def _aisle_rank(aisle: str) -> int:
    """Aisles sort in shopping order, not alphabetically — the table in
    aisles.py is written in roughly the order you walk a supermarket."""
    try:
        return AISLES.index(aisle)
    except ValueError:
        return len(AISLES)


def _sorted(items: Iterable[GroceryItem]) -> list[GroceryItem]:
    return sorted(
        items, key=lambda item: (_aisle_rank(item.aisle), _name_key(item.name))
    )


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
                    scaled = (
                        None
                        if ingredient.quantity is None
                        else ingredient.quantity * scale
                    )
                    quantity, unit = _to_base(scaled, ingredient.unit)
                    _add(
                        accumulator,
                        name=ingredient.name.strip(),
                        unit=unit,
                        aisle=ingredient.aisle or detect_aisle(ingredient.name),
                        quantity=quantity,
                        source=GrocerySource(
                            recipe_name=planned.name or recipe.name,
                            quantity=None if quantity is None else round(quantity, 2),
                            day=day,
                            slot=slot,
                        ),
                    )

    return _sorted(accumulator.values())


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

    Lines are keyed by name *and* unit — both in their comparison form — so
    "Oignon" and "oignons" are one line while "200 g de tomates" and "3
    tomates" stay two. The second pair would need a density per ingredient to
    merge, and two honest lines beat one invented one.
    """
    key = _item_key(name, unit)
    item = accumulator.get(key)

    if item is None:
        accumulator[key] = GroceryItem(
            key=key,
            name=_display_name(name),
            quantity=None if quantity is None else round(quantity, 2),
            unit=unit,
            aisle=aisle or "autre",
            sources=[source],
        )
        return

    # Variants that merge here differ only in case, accents and plural — that
    # is what made them one line. The longest is the plural, which is the right
    # heading for a line that now holds five of something.
    if len(name) > len(item.name):
        item.name = _display_name(name)

    if quantity is not None:
        # An unquantified mention ("sel") leaves the total alone rather than
        # counting as zero, so one such line never blanks out a real quantity.
        item.quantity = round((item.quantity or 0) + quantity, 2)
    item.sources.append(source)


# ------------------------------------------------------- the model's pass

# Words that make one product a different product. If two lines the model
# wants to merge disagree on any of these, the merge is refused whatever it
# says — asked the same question twice, it will happily merge "citrons" with
# "citrons verts" once and refuse the next time, and the cost of the two
# answers is not the same. An extra line is untidy; a missing line means
# standing in the shop with no limes.
_DISTINGUISHING = frozenset(
    """
    vert verte rouge jaune blanc blanche noir noire rose brun brune
    complet complete entier entiere demi ecreme ecremee
    sale salee sucre sucree vanille vanillee
    fume fumee seche sec frais fraiche doux douce
    cerise coco rape rapee concentre concentree poudre glace glacee
    liquide epais epaisse cru crue cuit cuite surgele surgelee
    bio allege allegee light zero sans
    """.split()
)


def _mergeable(names: list[str]) -> bool:
    """Whether these names may be one line, whatever the model decided.

    Compares what the names disagree on, not what they contain: "huile
    d'olive" and "huile d'olive vierge extra" differ by words that describe
    the same bottle, while "farine" and "farine complète" differ by one that
    sends you to another shelf.
    """
    words = [set(_name_key(name).split()) for name in names]
    shared = set.intersection(*words) if words else set()
    difference = set.union(*words) - shared if words else set()
    return not (difference & _DISTINGUISHING)



def apply_fusion(
    items: list[GroceryItem], groups: list[dict]
) -> list[GroceryItem]:
    """Merge the lines the model says are the same ingredient.

    It only ever decides *which* lines belong together and what to call the
    result; the arithmetic stays here. A group spanning two unit families is
    split back into one line per family — the model saying that "300 g de
    tomates" and "4 tomates" are both tomatoes is true and still not a reason
    to invent a single number.

    Anything unrecognised is dropped rather than trusted: unknown keys, keys
    claimed by two groups, groups of one. What is left of a mangled answer is
    the first pass's list, which was already correct.
    """
    by_key = {item.key: item for item in items}
    claimed: set[str] = set()
    lines: list[GroceryItem] = []

    for group in groups:
        name = str(group.get("name") or "").strip()[:200]
        keys = [
            key
            for key in dict.fromkeys(group.get("keys") or [])
            if key in by_key and key not in claimed
        ]
        if not name or len(keys) < 2:
            continue

        members = [by_key[key] for key in keys]
        if not _mergeable([name] + [member.name for member in members]):
            logger.info(
                "Refusing to merge %s: they are not the same product",
                [member.name for member in members],
            )
            continue

        claimed.update(keys)
        lines.extend(_merge(name, members))

    if not claimed:
        return items

    fused = len(lines)
    lines.extend(item for item in items if item.key not in claimed)
    logger.info("Fusion: %d lines merged into %d", len(claimed), fused)

    # Folded once more: a fused name can land on a line the model left alone
    # ("Citrons" beside an existing "citron"), and that is one line too.
    merged: dict[str, GroceryItem] = {}
    for line in lines:
        existing = merged.get(line.key)
        if existing is None:
            merged[line.key] = line
            continue
        if line.quantity is not None:
            existing.quantity = round((existing.quantity or 0) + line.quantity, 2)
        existing.sources.extend(line.sources)

    return _sorted(merged.values())


def _merge(name: str, members: list[GroceryItem]) -> list[GroceryItem]:
    """One group of lines the model matched, as one line per unit family.

    A family holding a single line is left exactly as it was, name and key
    included. Renaming it would produce two lines called the same thing with
    incompatible units — "Poulet 600 g" above "Poulet 1 u." — which reads as a
    bug rather than as the two real products it is. Merging is the only thing
    that earns a new name.
    """
    families: dict[str, list[GroceryItem]] = {}
    # A mention with neither a number nor a unit ("sel", "poivre") describes no
    # amount at all, so it can join whichever line the group settles on rather
    # than becoming one of its own.
    loose = [m for m in members if m.quantity is None and not m.unit]
    for member in members:
        if member in loose:
            continue
        families.setdefault(member.unit, []).append(member)

    if not families:
        families[""] = loose
        loose = []

    biggest = max(families, key=lambda unit: len(families[unit]))
    families[biggest].extend(loose)

    return [
        _one_line(name, unit, group) if len(group) > 1 else group[0]
        for unit, group in families.items()
    ]


def _one_line(name: str, unit: str, members: list[GroceryItem]) -> GroceryItem:
    quantities = [m.quantity for m in members if m.quantity is not None]
    sources: list[GrocerySource] = []
    for member in members:
        sources.extend(member.sources)

    # The aisle the most lines agreed on, ignoring the ones that never got
    # further than "autre" — one unrecognised name should not drag a group of
    # four out of the vegetables.
    votes = Counter(m.aisle for m in members if m.aisle and m.aisle != "autre")
    aisle = votes.most_common(1)[0][0] if votes else "autre"

    return GroceryItem(
        key=_item_key(name, unit),
        name=_display_name(name),
        quantity=round(sum(quantities), 2) if quantities else None,
        unit=unit,
        aisle=aisle,
        sources=sources,
    )
