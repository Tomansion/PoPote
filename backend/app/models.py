from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

RecipeType = Literal[
    "Entrée", "Plat", "Dessert", "Petit-déj.", "Apéritif", "Sauce/Base"
]
Temperature = Literal["Chaud", "Froid"]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ingredient(BaseModel):
    name: str
    quantity: Optional[float] = None
    unit: str = ""
    # Filled in by the server from `name` when the client leaves it empty,
    # but a client-supplied value always wins (the user can override it).
    aisle: str = ""


class RecipeBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: RecipeType = "Plat"
    servings: int = Field(default=4, ge=1, le=100)
    prep_minutes: int = Field(default=0, ge=0, le=6000)
    cook_minutes: int = Field(default=0, ge=0, le=6000)
    temperature: Temperature = "Chaud"
    favorite: bool = False
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @field_validator("steps")
    @classmethod
    def drop_blank_steps(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s.strip()]

    @field_validator("ingredients")
    @classmethod
    def drop_blank_ingredients(cls, v: list[Ingredient]) -> list[Ingredient]:
        return [i for i in v if i.name.strip()]


class RecipeCreate(RecipeBase):
    pass


class RecipeUpdate(RecipeBase):
    pass


class Recipe(RecipeBase):
    id: str
    created_at: str
    updated_at: str

    @property
    def total_minutes(self) -> int:
        return self.prep_minutes + self.cook_minutes


class WSEvent(BaseModel):
    """Envelope broadcast to every connected client."""

    type: Literal["recipe.created", "recipe.updated", "recipe.deleted", "hello"]
    recipe: Optional[Recipe] = None
    recipe_id: Optional[str] = None
    recipes: Optional[list[Recipe]] = None
    at: str = Field(default_factory=utcnow_iso)
