"""What the app asks a model: what the shopping costs, and what is the same thing twice.

Recipe and image generation used to live here too. They were removed
deliberately — a generated recipe is somebody else's cooking and a generated
photo is of a dish nobody made, and neither is what this app is for. What is
left are the two jobs with no good offline answer: putting a plausible price
on a list of groceries, and deciding that "blancs de poulet" and "poulet" are
one line of the list. Both take a whole list in one call and both hand back
data, never prose — the model answers by calling a tool.

Best-effort, like everything that leaves the process: a missing API key simply
disables the feature (AIDisabled) rather than failing the request, and both
the list and its arithmetic are correct without one.
"""

import json
import logging
from typing import Iterable, Optional

from openai import OpenAI

from .config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

# One call covers a whole list. A long event can produce a lot of lines, and
# the estimate is a nice-to-have, so the tail is dropped rather than paged
# through several requests.
MAX_ITEMS = 150


class AIDisabled(Exception):
    """No OpenAI API key is configured."""


def is_enabled() -> bool:
    return bool(settings.openai_api_key)


def _get_client() -> OpenAI | None:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# The model answers by calling this, so the reply is a list of numbers rather
# than prose with numbers in it. Anything it gets wrong (a missing key, a
# price as a string) is dropped by the caller instead of failing the request.
_SUBMIT_PRICES_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_prices",
        "description": (
            "Submit an estimated price in euros for every line of the "
            "shopping list."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "The line's key, copied verbatim.",
                            },
                            "price": {
                                "type": "number",
                                "description": (
                                    "Estimated price in euros for the whole "
                                    "quantity of that line."
                                ),
                            },
                        },
                        "required": ["key", "price"],
                    },
                }
            },
            "required": ["prices"],
        },
    },
}

# Same shape as the prices tool, and for the same reason: a list of groups is
# something to validate, where a paragraph explaining the groups is something
# to parse. Quantities are deliberately absent — the model decides what goes
# together and what to call it, the caller does the arithmetic.
_SUBMIT_GROUPS_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_groups",
        "description": (
            "Submit the groups of lines that refer to the same ingredient."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "groups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "keys": {
                                "type": "array",
                                "description": (
                                    "At least two line keys, copied verbatim."
                                ),
                                "items": {"type": "string"},
                            },
                            "name": {
                                "type": "string",
                                "description": (
                                    "The name to give the merged line, in "
                                    "French, plural, no quantity in it."
                                ),
                            },
                        },
                        "required": ["keys", "name"],
                    },
                }
            },
            "required": ["groups"],
        },
    },
}

_FUSE_SYSTEM = (
    "Tu nettoies une liste de courses. Regroupe uniquement les lignes qui "
    "désignent exactement le même produit à acheter : différences de casse, "
    "d'accents, de singulier/pluriel, fautes de frappe, abréviations, ou une "
    "précision qui ne change pas ce qu'on met dans le panier (« huile "
    "d'olive vierge extra » et « huile d'olive », « gousses d'ail » et "
    "« ail »).\n"
    "Règle absolue : si au magasin tu prendrais deux produits différents, ne "
    "les regroupe pas. Jamais de regroupement entre tomate et tomate cerise, "
    "citron et citron vert, crème liquide et crème épaisse, lait et lait de "
    "coco, farine et farine complète, sucre et sucre vanillé, oignon et "
    "oignon rouge, chocolat noir et chocolat au lait, poulet entier et "
    "blancs de poulet, pomme et pomme de terre.\n"
    "Dans le doute, laisse les lignes séparées : deux lignes justes valent "
    "mieux qu'une ligne fausse. Ne renvoie que les groupes d'au moins deux "
    "lignes, chaque ligne dans un seul groupe, et donne à chaque groupe le "
    "nom le plus simple et le plus courant du produit, sans quantité ni "
    "unité : au pluriel si le produit se compte (citrons, oignons), au "
    "singulier s'il ne se compte pas (farine, crème liquide, parmesan, "
    "huile d'olive)."
)


def fuse_ingredients(items: Iterable[dict]) -> list[dict]:
    """Find the lines that are the same ingredient. Returns [{keys, name}].

    `items` are dicts with `key`, `name`, `quantity` and `unit`. The units are
    shown to the model as context — the same product bought by weight and by
    the piece is still one group — but it is never asked to convert anything.

    A model that finds nothing to merge returns an empty list, which is a
    perfectly good answer and the common one for a short, tidy list.
    """
    client = _get_client()
    if client is None:
        raise AIDisabled

    lines = list(items)[:MAX_ITEMS]
    # Nothing to compare a single line against.
    if len(lines) < 2:
        return []

    listing = "\n".join(
        f"- {line['key']} : {line.get('name', '')} "
        f"{_format_quantity(line.get('quantity'))}{line.get('unit', '')}".rstrip()
        for line in lines
    )

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _FUSE_SYSTEM},
            {"role": "user", "content": f"Liste de courses :\n{listing}"},
        ],
        tools=[_SUBMIT_GROUPS_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_groups"}},
    )

    calls = response.choices[0].message.tool_calls or []
    if not calls:
        return []

    data = json.loads(calls[0].function.arguments)
    wanted = {line["key"] for line in lines}

    groups: list[dict] = []
    for entry in data.get("groups", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        keys = entry.get("keys")
        if not isinstance(name, str) or not isinstance(keys, list):
            continue
        # Keys are echoed back by the model, so an invented one is possible;
        # only lines we actually asked about survive.
        kept = [key for key in keys if isinstance(key, str) and key in wanted]
        if len(kept) >= 2 and name.strip():
            groups.append({"keys": kept, "name": name.strip()})
    return groups


_SYSTEM = (
    "Tu estimes le coût de courses dans un supermarché français de taille "
    "moyenne, aux prix actuels. Pour chaque ligne, donne le prix en euros de "
    "la quantité demandée — pas le prix au kilo, et pas le prix du "
    "conditionnement entier si la recette n'en utilise qu'une partie. Une "
    "estimation raisonnable vaut mieux qu'aucune réponse : renseigne toutes "
    "les lignes, même les plus vagues."
)


def estimate_prices(items: Iterable[dict]) -> dict[str, float]:
    """Estimate a price per line. Returns {key: euros}, possibly partial.

    `items` are dicts with `key`, `name`, `quantity` and `unit`. Lines the
    model skips or mangles are simply absent from the result, which the
    caller shows as "pas d'estimation" rather than as zero.
    """
    client = _get_client()
    if client is None:
        raise AIDisabled

    lines = list(items)[:MAX_ITEMS]
    if not lines:
        return {}

    listing = "\n".join(
        f"- {line['key']} : {line.get('name', '')} "
        f"{_format_quantity(line.get('quantity'))}{line.get('unit', '')}".rstrip()
        for line in lines
    )

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Liste de courses :\n{listing}"},
        ],
        tools=[_SUBMIT_PRICES_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_prices"}},
    )

    calls = response.choices[0].message.tool_calls or []
    if not calls:
        return {}

    data = json.loads(calls[0].function.arguments)
    wanted = {line["key"] for line in lines}

    prices: dict[str, float] = {}
    for entry in data.get("prices", []):
        key = entry.get("key")
        price = _as_price(entry.get("price"))
        # Keys are echoed back by the model, so an invented one is possible;
        # only lines we actually asked about are kept.
        if key in wanted and price is not None:
            prices[key] = price
    return prices


def _format_quantity(quantity) -> str:
    if quantity is None:
        return ""
    if float(quantity).is_integer():
        return f"{int(quantity)} "
    return f"{round(float(quantity), 2)} "


def _as_price(value) -> Optional[float]:
    try:
        price = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    # A negative or absurd price is a hallucination, not a bargain.
    if price < 0 or price > 10_000:
        return None
    return price
