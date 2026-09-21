"""The theme files are the contract in engineering-standards/standards/12-themes.md:
twelve themes, every token defined, and every text token readable (WCAG AA) on every surface."""

import re
from pathlib import Path

import pytest

from kanban.themes import LIGHT_THEMES, TEXT_SIZES, THEME_NAMES, theme_cards

STATIC = Path(__file__).parent.parent / "src" / "kanban" / "static"
CSS = (STATIC / "themes.css").read_text()
APP = (STATIC / "app.css").read_text()
TOKENS = ["--bg", "--bg-surface", "--bg-card", "--bg-well", "--border", "--border-glow", "--text-primary",
          "--text-secondary", "--text-muted", "--text-subtle", "--nav-text", "--accent", "--accent-text",
          "--accent-dim", "--accent-hover", "--on-accent", "--text-glow", "--scanline-opacity", "--vignette-opacity"]


def blocks(css: str) -> dict[str, dict[str, str]]:
    found = {}
    for name, body in re.findall(r"\[data-theme=(\w+)\]\s*\{([^}]*)\}", css):
        found[name] = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", body))
        found[name]["color-scheme"] = re.search(r"color-scheme:\s*(\w+)", body)[1]
    return found


def rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    h = "".join(c * 2 for c in h[:3]) if len(h) in (3, 4) else h
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(h: str) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


THEMES = blocks(CSS)


def test_twelve_themes_in_the_documented_order():
    assert list(THEMES) == THEME_NAMES
    assert len(THEMES) == 12 and [c["name"] for c in theme_cards()] == THEME_NAMES
    assert TEXT_SIZES == ["small", "medium", "large"]


@pytest.mark.parametrize("name", THEME_NAMES)
def test_every_token_defined_and_scheme_matches(name):
    theme = THEMES[name]
    assert [t for t in TOKENS if t not in theme] == []
    assert theme["color-scheme"] == ("light" if name in LIGHT_THEMES else "dark")


@pytest.mark.parametrize("name", THEME_NAMES)
def test_text_tokens_meet_wcag_aa_on_every_surface(name):
    t = THEMES[name]
    surfaces = [t["--bg"], t["--bg-surface"], t["--bg-card"]]
    for token in ("--text-primary", "--text-secondary", "--text-subtle", "--accent-text"):
        worst = min(contrast(t[token], s) for s in surfaces)
        assert worst >= 4.5, f"{name} {token} is {worst:.2f}:1"
    assert contrast(t["--on-accent"], t["--accent"]) >= 4.5, f"{name} on-accent"


def test_raw_muted_is_known_to_fail_so_it_must_not_be_used_for_text():
    """Documents the finding in 12-themes.md; if a palette is ever fixed, drop --text-subtle."""
    assert all(min(contrast(t["--text-muted"], t["--bg"]), contrast(t["--text-muted"], t["--bg-card"])) < 4.5
               for t in THEMES.values())
    used = re.findall(r"color:\s*var\(--text-muted\)", APP)
    assert used == [], "app.css uses raw --text-muted for text; use --text-subtle"


def test_default_palettes_meet_aa():
    for scheme in ("light", "dark"):
        block = re.search(r":root:not\(\[data-theme\]\)\s*\{([^}]*)\}",
                          APP if scheme == "light" else APP[APP.index("prefers-color-scheme: dark"):])[1]
        t = dict(re.findall(r"(--[\w-]+):\s*([^;\s]+);", block))
        surfaces = [t["--bg"], t["--bg-surface"], t["--bg-card"], t["--bg-well"]]
        for token in ("--text-primary", "--text-secondary", "--text-subtle", "--accent-text"):
            assert min(contrast(t[token], s) for s in surfaces) >= 4.5, (scheme, token)
        assert contrast(t["--on-accent"], t["--accent"]) >= 4.5


def test_app_css_has_no_overlays_that_vanish_on_dark_themes():
    assert not re.search(r"background:\s*#000[12]\b", APP)
    assert "var(--side)" not in APP and "var(--card)" not in APP


def test_boot_script_and_stylesheet_order(tmp_path):
    from kanban import create_app
    page = create_app(tmp_path).test_client().get("/settings").text
    assert page.index("localStorage.getItem('theme')") < page.index("themes.css") < page.index("app.css")
    assert page.index("themes.css") < page.index("htmx.min.js")          # applied before first paint
    for name in THEME_NAMES:
        assert f'value="{name}"' in page and f'data-theme="{name}"' in page
    assert 'value="default"' in page
