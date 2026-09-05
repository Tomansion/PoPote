from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

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
    # Free-form grouping ("Asiatique", "Hiver", ...), shown as the mobile
    # carousel rows. Distinct from `type`, which drives the existing filters.
    category: str = Field(default="", max_length=60)
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
    # Defaulted so documents written before accounts existed still parse. They
    # match no user, so they are simply never listed. See "Known limits".
    owner_id: str = ""
    created_at: str
    updated_at: str
    # Set asynchronously by POST /recipes/{id}/image, well after creation —
    # never part of RecipeCreate/RecipeUpdate, so the edit form can't touch it.
    image_url: str = ""

    @property
    def total_minutes(self) -> int:
        return self.prep_minutes + self.cook_minutes


class RecipePrompt(BaseModel):
    """Free-text ask for POST /recipes/generate."""

    prompt: str = Field(min_length=1, max_length=2000)


class RecipeImagePrompt(BaseModel):
    """Optional steer for POST /recipes/{id}/image; falls back to the recipe
    itself (name + notes) when left blank."""

    prompt: str = ""


# ---------------------------------------------------------------- accounts


class UserPublic(BaseModel):
    """A user as anyone else in a shared event may see them.

    Deliberately excludes the email: event members see a name and an avatar,
    never each other's contact details.
    """

    id: str
    display_name: str
    avatar_seed: int
    created_at: str


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=60)
    avatar_seed: int = Field(default=0, ge=0, le=999_999_999)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("display_name must not be blank")
        return stripped


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    """Rename yourself, or reroll the avatar. Both are optional."""

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    avatar_seed: Optional[int] = Field(default=None, ge=0, le=999_999_999)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("display_name must not be blank")
        return stripped


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


# ------------------------------------------------------------------ events


class EventBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Plain calendar days (YYYY-MM-DD), which is what the pickers produce.
    starts_on: date
    ends_on: date

    @field_validator("name")
    @classmethod
    def strip_event_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped

    @model_validator(mode="after")
    def check_range(self) -> "EventBase":
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return self


class EventCreate(EventBase):
    pass


class EventUpdate(EventBase):
    pass


class Event(EventBase):
    id: str
    owner_id: str
    # Shared verbatim in the invite link; whoever holds it can join.
    invite_code: str
    member_ids: list[str] = Field(default_factory=list)
    members: list[UserPublic] = Field(default_factory=list)
    created_at: str
    updated_at: str


class EventPreview(BaseModel):
    """What an invite link shows before you commit to joining it."""

    id: str
    name: str
    starts_on: date
    ends_on: date
    owner_name: str
    member_count: int
    already_member: bool


class WSEvent(BaseModel):
    """Envelope sent to one user's connected clients.

    Fan-out is per user now: a recipe event reaches only its owner, an event
    reaches every member. Nothing is broadcast to everyone.
    """

    type: Literal[
        "recipe.created",
        "recipe.updated",
        "recipe.deleted",
        "event.created",
        "event.updated",
        "event.deleted",
        "hello",
    ]
    recipe: Optional[Recipe] = None
    recipe_id: Optional[str] = None
    recipes: Optional[list[Recipe]] = None
    event: Optional[Event] = None
    event_id: Optional[str] = None
    events: Optional[list[Event]] = None
    at: str = Field(default_factory=utcnow_iso)
