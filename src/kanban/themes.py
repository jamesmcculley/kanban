"""The colour themes every app shares. Definitions live in static/themes.css (a copy of
engineering-standards/templates/themes.css); this module is just the names and descriptions."""

THEME_NAMES = ["dark", "dim", "light", "fog", "warm", "terminal", "amber", "nord", "rose", "slate",
               "paper", "midnight"]
LIGHT_THEMES = {"light", "fog", "warm", "paper"}
BLURBS = {
    "dark": "Neutral charcoal, white accent",
    "dim": "Blue-grey, mint-green accent",
    "light": "Clean white-grey, green accent",
    "fog": "Cool grey, blue accent",
    "warm": "Cream, brass accent",
    "terminal": "Black, phosphor green",
    "amber": "Black, amber CRT",
    "nord": "The Nord palette, frost cyan",
    "rose": "Near-black plum, pink",
    "slate": "Deep navy, sky blue",
    "paper": "Warm paper, rust",
    "midnight": "Deep violet, purple",
}
TEXT_SIZES = ["small", "medium", "large"]


def theme_cards() -> list[dict]:
    return [{"name": n, "label": n.capitalize(), "blurb": BLURBS[n],
             "scheme": "light" if n in LIGHT_THEMES else "dark"} for n in THEME_NAMES]
