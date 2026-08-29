"""Guess the supermarket aisle ("rayon") an ingredient belongs to.

Deliberately a plain keyword table: it is transparent, instant, works offline
and is trivial to extend. The frontend shows the guess as "rayon détecté" and
lets the user override it, so a wrong guess is never a dead end.
"""

AISLES = [
    "viande",
    "poisson",
    "f&l",
    "laitier",
    "épicerie",
    "boulangerie",
    "surgelé",
    "boisson",
    "autre",
]

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "viande": (
        "boeuf", "bœuf", "poulet", "porc", "veau", "agneau", "dinde", "canard",
        "lardon", "jambon", "saucisse", "steak", "viande", "merguez", "chorizo",
        "bacon", "rôti", "escalope", "côte", "magret",
    ),
    "poisson": (
        "poisson", "saumon", "thon", "cabillaud", "colin", "crevette", "moule",
        "huître", "calamar", "sardine", "maquereau", "truite", "bar", "lieu",
        "anchois", "crabe", "homard", "st-jacques", "saint-jacques",
    ),
    "f&l": (
        "tomate", "carotte", "oignon", "ail", "échalote", "pomme de terre",
        "courgette", "aubergine", "poivron", "salade", "laitue", "épinard",
        "brocoli", "chou", "haricot", "petit pois", "champignon", "poireau",
        "céleri", "navet", "betterave", "concombre", "radis", "fenouil",
        "pomme", "poire", "banane", "orange", "citron", "fraise", "framboise",
        "raisin", "pêche", "abricot", "mangue", "ananas", "melon", "avocat",
        "persil", "basilic", "coriandre", "menthe", "thym", "romarin", "ciboulette",
        "gingembre", "courge", "potiron", "patate douce",
    ),
    "laitier": (
        "lait", "crème", "beurre", "yaourt", "fromage", "gruyère", "emmental",
        "parmesan", "mozzarella", "comté", "chèvre", "ricotta", "mascarpone",
        "feta", "roquefort", "cheddar", "oeuf", "œuf",
    ),
    "épicerie": (
        "farine", "sucre", "sel", "poivre", "huile", "vinaigre", "riz", "pâte",
        "pâtes", "lentille", "pois chiche", "quinoa", "semoule", "couscous",
        "conserve", "concentré", "bouillon", "moutarde", "mayonnaise", "ketchup",
        "sauce soja", "miel", "confiture", "chocolat", "levure", "vanille",
        "cannelle", "curry", "paprika", "cumin", "curcuma", "noix", "amande",
        "raisin sec", "olive", "câpre", "maïs", "coulis", "sirop", "polenta",
    ),
    "boulangerie": (
        "pain", "baguette", "brioche", "croissant", "biscotte", "pita",
        "tortilla", "wrap", "chapelure", "pâte feuilletée", "pâte brisée",
        "pâte sablée",
    ),
    "surgelé": ("surgelé", "surgelée", "glace", "sorbet", "glaçon"),
    "boisson": (
        "eau", "vin", "bière", "jus", "soda", "café", "thé", "cidre", "rhum",
        "cognac", "whisky", "vodka", "limonade",
    ),
}


def detect_aisle(ingredient_name: str) -> str:
    """Return the best-matching aisle for an ingredient name, or "autre"."""
    if not ingredient_name:
        return "autre"

    name = ingredient_name.strip().lower()

    # Longest keyword wins, so "patate douce" beats "pomme de terre"-style
    # partial overlaps and "sauce soja" beats "sauce".
    best_aisle = "autre"
    best_length = 0
    for aisle, keywords in _KEYWORDS.items():
        for keyword in keywords:
            if keyword in name and len(keyword) > best_length:
                best_aisle = aisle
                best_length = len(keyword)

    return best_aisle
