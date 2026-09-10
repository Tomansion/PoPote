"""The one place the app talks to an LLM: estimating what the shopping costs.

Recipe and image generation used to live here too. They were removed
deliberately — a generated recipe is somebody else's cooking and a generated
photo is of a dish nobody made, and neither is what this app is for. What is
left is the one job with no good offline answer: putting a plausible price on
a list of groceries.

Best-effort, like everything that leaves the process: a missing API key simply
disables the estimate (AIDisabled) rather than failing the request, and the
list is perfectly usable without one.
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
