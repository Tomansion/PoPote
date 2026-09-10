from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

RecipeType = Literal[
    "Entrée", "Plat", "Dessert", "Petit-déj.", "Apéritif", "Sauce/Base"
]
Temperature = Literal["Chaud", "Froid"]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ingredient(BaseModel):
    # No min_length: drop_blank_ingredients below relies on being able to see
    # (and silently drop) a blank name rather than have the whole request
    # rejected — the create form always sends a couple of empty starter rows.
    name: str = Field(default="", max_length=200)
    quantity: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    unit: str = Field(default="", max_length=30)
    # Filled in by the server from `name` when the client leaves it empty,
    # but a client-supplied value always wins (the user can override it).
    aisle: str = Field(default="", max_length=60)


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
    # Capped list length and per-item length alike: an unbounded list (or an
    # unbounded string in it) is a cheap way to bloat a document — whether
    # from a client with too much time or a very enthusiastic import.
    ingredients: list[Ingredient] = Field(default_factory=list, max_length=200)
    steps: list[Annotated[str, Field(max_length=2000)]] = Field(
        default_factory=list, max_length=200
    )
    notes: str = Field(default="", max_length=4000)

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
    # Set by POST /recipes/{id}/image, separately from the recipe itself —
    # never part of RecipeCreate/RecipeUpdate, so a save can't wipe the photo.
    # The thumbnail is what the cards load; the full size is for the detail
    # page. Both are public URLs into the object store.
    image_url: str = ""
    image_thumb_url: str = ""

    @property
    def total_minutes(self) -> int:
        return self.prep_minutes + self.cook_minutes


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


class ProfilePrefs(BaseModel):
    """The ten answers on a member's page: what they eat, and who they are.

    Every one is optional and every one is free text, including the questions
    that look closed ("Le vin et moi"). Half the list only works if people can
    write their own answer, and one widget for ten short questions beats a
    form that switches between selects and text fields halfway down.

    An unanswered question is an empty string, and an empty string is never
    rendered on the public page — so a half-filled profile still looks
    deliberate rather than unfinished.
    """

    diet: str = Field(default="", max_length=200)
    allergies: str = Field(default="", max_length=200)
    dislikes: str = Field(default="", max_length=200)
    alcohol: str = Field(default="", max_length=200)
    spice: str = Field(default="", max_length=200)
    cheese: str = Field(default="", max_length=200)
    signature: str = Field(default="", max_length=200)
    guilty_pleasure: str = Field(default="", max_length=200)
    hated_veggie: str = Field(default="", max_length=200)
    last_meal: str = Field(default="", max_length=200)

    @field_validator("*")
    @classmethod
    def strip_answer(cls, v: str) -> str:
        return v.strip()


class UserProfile(UserPublic):
    """A user plus their answers.

    Returned for yourself, and for anyone you share an event with. The lean
    `UserPublic` is what event member lists carry, so ten extra strings are
    not repeated for every member of every event in the `hello` payload.
    """

    prefs: ProfilePrefs = Field(default_factory=ProfilePrefs)


class PublicProfile(BaseModel):
    """Someone else's page: who they are, and the recipes you may see."""

    user: UserProfile
    recipes: list[Recipe] = Field(default_factory=list)


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
    """Rename yourself, reroll the avatar, or answer the questions.

    All three are optional and independent: `prefs`, when present, replaces
    the whole set of answers, which is what the profile form submits.
    """

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    avatar_seed: Optional[int] = Field(default=None, ge=0, le=999_999_999)
    prefs: Optional[ProfilePrefs] = None

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
    user: UserProfile


# ------------------------------------------------------------------ events


class EventBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Plain calendar days (YYYY-MM-DD), which is what the pickers produce.
    starts_on: date
    ends_on: date
    # How many people the organiser expects at the table. Every meal slot
    # inherits it unless someone overrides that slot, so correcting the number
    # here fixes the whole plan at once.
    default_people: int = Field(default=4, ge=1, le=200)

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


# ----------------------------------------------------------------- planner

# The three parts of a day, in the order they are cooked and displayed.
SLOTS = ("matin", "midi", "soir")
SlotName = Literal["matin", "midi", "soir"]

# Days are keys in the plan document, so they are plain strings rather than
# `date` — Arango object keys are strings, and the client sends back exactly
# what it was given.
DayStr = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class PlannedRecipe(BaseModel):
    """One recipe planned for one part of one day.

    `name` and `owner_id` are denormalised on purpose. A plan has to stay
    readable after the recipe behind it is renamed or deleted, and after the
    member who owns it has left the event — at which point the viewer can no
    longer fetch it at all.
    """

    # Stable per planned meal, not per recipe: the same dish can appear twice
    # in one slot, and drag & drop needs to tell those two apart.
    uid: str = Field(min_length=1, max_length=40)
    recipe_id: str = Field(min_length=1, max_length=60)
    owner_id: str = Field(default="", max_length=60)
    name: str = Field(default="", max_length=200)
    servings: int = Field(default=1, ge=1, le=500)
    # Who has agreed to cook this one. Member ids, filtered against the event's
    # members on the way in — distinct from `owner_id`, which is whose recipe
    # book it came out of and says nothing about who is at the stove.
    cooks: list[Annotated[str, Field(max_length=60)]] = Field(
        default_factory=list, max_length=20
    )


class MealSlot(BaseModel):
    skipped: bool = False
    # None means "however many the event expects", so raising the event's
    # headcount updates every slot nobody has deliberately overridden.
    people: Optional[int] = Field(default=None, ge=0, le=500)
    recipes: list[PlannedRecipe] = Field(default_factory=list, max_length=30)

    @property
    def is_empty(self) -> bool:
        """Nothing decided here — distinct from `skipped`, which is a decision."""
        return not self.skipped and not self.recipes and self.people is None


class EventPlan(BaseModel):
    """Everything planned for one event, as one document.

    Nested day -> slot rather than a flat list, so a single slot can be
    patched in place by two people at once without either overwriting the
    other's day.
    """

    event_id: str
    days: dict[str, dict[str, MealSlot]] = Field(default_factory=dict)
    # day -> member ids on duty that day, whoever is cooking each dish. The
    # two levels answer different questions: "who runs Saturday" and "who is
    # making the tart". Kept beside `days` rather than inside it so that
    # writing a slot and writing a day's roster never touch the same subtree.
    day_cooks: dict[str, list[str]] = Field(default_factory=dict)
    updated_at: str = ""


class DayCooks(BaseModel):
    """Set (or clear) the members on duty for one day."""

    cooks: list[Annotated[str, Field(max_length=60)]] = Field(
        default_factory=list, max_length=20
    )


class PlanMoveItem(BaseModel):
    day: DayStr
    slot: SlotName
    uid: str = Field(min_length=1, max_length=40)


class PlanMove(BaseModel):
    """Drag & drop: move any number of planned meals into one target slot."""

    items: list[PlanMoveItem] = Field(min_length=1, max_length=50)
    to_day: DayStr
    to_slot: SlotName


# ----------------------------------------------------------- grocery list


class GrocerySource(BaseModel):
    """Which planned meal contributed to a line, and how much of it.

    Kept per item so the list can be flipped from "par rayon" to "par recette"
    without regenerating anything.
    """

    recipe_name: str = ""
    quantity: Optional[float] = None
    day: str = ""
    slot: str = ""


class GroceryItem(BaseModel):
    # Derived from the name and unit, so regenerating a list keeps the boxes
    # that were already ticked for lines that survived.
    key: str
    name: str
    quantity: Optional[float] = None
    unit: str = ""
    aisle: str = "autre"
    checked: bool = False
    # Filled in by the LLM estimate, in euros. None until someone asks for it.
    price: Optional[float] = None
    # Who said they would get this one. Member ids: the shared page renders
    # them from the list's own `members`, so a signed-out shopper still sees
    # who is fetching what without being able to change it.
    assignees: list[Annotated[str, Field(max_length=60)]] = Field(
        default_factory=list, max_length=20
    )
    sources: list[GrocerySource] = Field(default_factory=list)


class GroceryList(BaseModel):
    event_id: str
    event_name: str = ""
    # Its own code, separate from the event's invite code: handing someone the
    # shopping list must not also hand them a way into the event.
    share_code: str
    items: list[GroceryItem] = Field(default_factory=list)
    # Filled in from the event on the way out, never stored: a member who
    # joins after the list was generated still has a face on it. Present on
    # the public payload too — assignment is unreadable without it.
    members: list[UserPublic] = Field(default_factory=list)
    total_price: Optional[float] = None
    priced_at: str = ""
    generated_at: str = ""
    updated_at: str = ""


class GroceryListSummary(BaseModel):
    """One row of the "Liste de courses" index."""

    event_id: str
    event_name: str
    share_code: str
    item_count: int = 0
    checked_count: int = 0
    total_price: Optional[float] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    updated_at: str = ""


class GroceryCheck(BaseModel):
    checked: bool


class GroceryCheckMany(BaseModel):
    """Tick or untick several lines in one write — a whole rayon, or a whole
    recipe's worth, from the "check everything under this heading" box.

    A loop of single-item PATCHes would race: each one reads the whole item
    list, flips its own line, and writes the whole list back, so two such
    calls in flight at once can each write from a stale read and silently
    discard the other's tick. One call, one read-modify-write, avoids that
    the same way `GroceryAssign` already does for assignment.
    """

    keys: list[Annotated[str, Field(max_length=40)]] = Field(
        min_length=1, max_length=500
    )
    checked: bool


class GroceryAssign(BaseModel):
    """Put people on some lines of the list.

    Addressed by key rather than by rayon or recipe: the client already groups
    the list both ways on screen, so "assign this whole aisle" is the same
    call as "assign this line" with more keys in it. `assignees` replaces
    whatever was there, and an empty list clears it.
    """

    keys: list[Annotated[str, Field(max_length=40)]] = Field(
        min_length=1, max_length=500
    )
    assignees: list[Annotated[str, Field(max_length=60)]] = Field(
        default_factory=list, max_length=20
    )


class WSEvent(BaseModel):
    """Envelope sent to one user's connected clients.

    Fan-out is per user: a recipe event reaches only its owner, an event (and
    the plan or grocery list hanging off it) reaches every member. Nothing is
    broadcast to everyone.
    """

    type: Literal[
        "recipe.created",
        "recipe.updated",
        "recipe.deleted",
        "event.created",
        "event.updated",
        "event.deleted",
        "plan.updated",
        "grocery.updated",
        "hello",
    ]
    recipe: Optional[Recipe] = None
    recipe_id: Optional[str] = None
    recipes: Optional[list[Recipe]] = None
    event: Optional[Event] = None
    event_id: Optional[str] = None
    events: Optional[list[Event]] = None
    plan: Optional[EventPlan] = None
    grocery: Optional[GroceryList] = None
    at: str = Field(default_factory=utcnow_iso)
