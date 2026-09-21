"""Automation rules ("when X happens, do Y"), Trello-Butler style but small (pure: no I/O).

A rule is a plain dict so it can live in YAML:

    {id, when, in?, tag?, do, arg?, enabled}

    when   completed | uncompleted | added | moved     (`moved` means moved INTO the list `in`)
    in     only when the card is in this list          (required for `moved`)
    tag    only when the card has this tag
    do     move | complete | uncomplete | add_tag | remove_tag | archive
    arg    the list for `move`, the tag for add_tag / remove_tag

Rules never trigger other rules, so a rule cannot loop.
"""

from __future__ import annotations

import uuid

from .tags import parse_tags

TRIGGERS = {
    "completed": "a card is completed",
    "uncompleted": "a card is un-checked",
    "added": "a card is added",
    "moved": "a card is moved into a list",
}
ACTIONS = {
    "move": "Move it to a list",
    "complete": "Mark it complete",
    "uncomplete": "Mark it not complete",
    "add_tag": "Add a tag",
    "remove_tag": "Remove a tag",
    "archive": "Clear it from the list",
}
MAX_RULES = 50


def _name(value) -> str | None:
    name = " ".join(str(value or "").split())
    return name or None


def clean_rule(raw: dict, lists: list[str] | None = None, rule_id: str | None = None) -> dict:
    """Validate and normalise a rule. `lists` are the board's list names (None for a global rule,
    which may name lists that only some boards have). Raises ValueError with a user-facing message."""
    when = raw.get("when")
    if when not in TRIGGERS:
        raise ValueError("Choose when the rule should run")
    where = _name(raw.get("in"))
    if when == "moved" and not where:
        raise ValueError("Say which list the card is moved into")
    if where and lists is not None and where not in lists:
        raise ValueError(f"This board has no list called “{where}”")
    tag = next(iter(parse_tags(raw.get("tag") or "")), None)
    if raw.get("tag") and not tag:
        raise ValueError("A tag is letters, digits, - or _, starting with a letter")

    do = raw.get("do")
    if do not in ACTIONS:
        raise ValueError("Choose what the rule should do")
    arg = None
    if do == "move":
        arg = _name(raw.get("arg"))
        if not arg:
            raise ValueError("Choose the list to move the card to")
        if lists is not None and arg not in lists:
            raise ValueError(f"This board has no list called “{arg}”")
    elif do in ("add_tag", "remove_tag"):
        arg = next(iter(parse_tags(raw.get("arg") or "")), None)
        if not arg:
            raise ValueError("Give the tag to add or remove, such as #urgent")

    rule = {"id": rule_id or raw.get("id") or uuid.uuid4().hex[:8], "when": when, "do": do,
            "enabled": raw.get("enabled", True) not in (False, "0", 0, "false")}
    for key, value in (("in", where), ("tag", tag), ("arg", arg)):
        if value:
            rule[key] = value
    return rule


def matches(rule: dict, event: str, column: str, tags: list[str]) -> bool:
    """Does `rule` fire for `event` on a card now in `column` with `tags`?"""
    if not rule.get("enabled", True) or rule.get("when") != event:
        return False
    if rule.get("in") and rule["in"] != column:
        return False
    return not (rule.get("tag") and rule["tag"] not in tags)


def describe(rule: dict) -> str:
    """'When a card is completed in Todo, tagged #home, move it to Done.'"""
    when, where = rule["when"], rule.get("in")
    trigger = {"completed": "a card is completed", "uncompleted": "a card is un-checked",
               "added": "a card is added", "moved": f"a card is moved into {where}"}[when]
    if where and when in ("completed", "uncompleted"):
        trigger += f" in {where}"
    elif where and when == "added":
        trigger += f" to {where}"
    if rule.get("tag"):
        trigger += f", tagged #{rule['tag']}"
    arg = rule.get("arg")
    action = {"move": f"move it to {arg}", "complete": "mark it complete",
              "uncomplete": "mark it not complete", "add_tag": f"add the tag #{arg}",
              "remove_tag": f"remove the tag #{arg}", "archive": "clear it from the list"}[rule["do"]]
    return f"When {trigger}, {action}."
