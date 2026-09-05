"""OpenAI-backed recipe generation.

Two independent calls: a tool-call that turns a free-text prompt into a
structured recipe, and an image generation call for its picture. Both are
best-effort — a missing API key simply disables the feature (AIDisabled)
rather than crashing the request, since this whole area is optional flavor
on top of the core CRUD.
"""

import base64
import json

from openai import OpenAI

from .config import settings
from .models import RecipeCreate, RecipeType

_client: OpenAI | None = None


class AIDisabled(Exception):
    """No OpenAI API key is configured."""


def _get_client() -> OpenAI | None:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# Mirrors RecipeCreate: the model fills this in and we hand the arguments
# straight to the pydantic model, so anything it gets wrong (a bad enum
# value, a missing name) surfaces as a normal validation error upstream.
_SUBMIT_RECIPE_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_recipe",
        "description": "Submit the generated recipe, in French.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": list(RecipeType.__args__)},
                "category": {
                    "type": "string",
                    "description": (
                        "Free-form grouping, e.g. Asiatique, Hiver, Été, "
                        "Franchouillard. Empty string if none fits."
                    ),
                },
                "servings": {"type": "integer", "minimum": 1, "maximum": 100},
                "prep_minutes": {"type": "integer", "minimum": 0},
                "cook_minutes": {"type": "integer", "minimum": 0},
                "temperature": {"type": "string", "enum": ["Chaud", "Froid"]},
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
                "steps": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["name", "type", "ingredients", "steps"],
        },
    },
}


def generate_recipe(prompt: str) -> RecipeCreate:
    client = _get_client()
    if client is None:
        raise AIDisabled

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un assistant culinaire. Réponds uniquement en "
                    "français, en appelant l'outil submit_recipe avec une "
                    "recette complète et réaliste."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        tools=[_SUBMIT_RECIPE_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_recipe"}},
    )

    call = response.choices[0].message.tool_calls[0]
    data = json.loads(call.function.arguments)
    return RecipeCreate(**data)


def generate_recipe_image(recipe_name: str, notes: str = "") -> bytes:
    client = _get_client()
    if client is None:
        raise AIDisabled

    prompt = f"Photo culinaire appétissante et réaliste de : {recipe_name}."
    if notes:
        prompt += f" {notes}"

    response = client.images.generate(
        model=settings.openai_image_model,
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    return base64.b64decode(response.data[0].b64_json)
