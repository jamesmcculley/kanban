"""Settings and rules, stored and applied.

Global: `.trellis.yml` (`settings`, `rules`). Per board: `board.md` (`settings`, `rules`).
The engine runs after a card is completed, un-checked, added or moved. Actions it takes never
trigger further rules (see rules.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import rules as R
from . import settings as S


class PreferencesMixin:
    # -- settings -------------------------------------------------------------

    def _write_meta(self, meta: dict) -> None:
        import yaml
        meta = {"format": 1, **{k: v for k, v in meta.items() if k != "format"}}
        self._meta_path().write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
                                     encoding="utf-8")

    @staticmethod
    def _tolerant_clean(values: dict, keys: tuple[str, ...]) -> dict:
        """Read stored settings, skipping any value a hand-edit made invalid."""
        out: dict = {}
        for key in keys:
            try:
                out.update(S.clean({key: (values or {}).get(key)}, (key,)))
            except ValueError:
                continue
        return out

    def global_settings(self) -> dict:
        return self._tolerant_clean(self._meta().get("settings") or {}, S.GLOBAL_KEYS)

    def save_global_settings(self, values: dict) -> dict:
        cleaned = S.clean(values, S.GLOBAL_KEYS)
        meta = self._meta()
        meta["settings"] = cleaned
        self._write_meta(meta)
        return cleaned

    def board_settings(self, slug: str) -> dict:
        return self._tolerant_clean(self.get_board(slug).settings, S.BOARD_KEYS)

    def save_board_settings(self, slug: str, values: dict) -> dict:
        board = self.get_board(slug)
        board.settings = S.clean(values, S.BOARD_KEYS)
        self._save_board(board)
        return board.settings

    def settings_for(self, slug: str) -> dict:
        """Defaults, then global, then this board's overrides."""
        return S.resolve(self.global_settings(), self.board_settings(slug))

    # -- rules ----------------------------------------------------------------

    def _rule_lists(self, scope: str | None) -> list[str] | None:
        if scope is None:
            return None
        board = self.get_board(scope)
        if board.kind != "kanban":
            raise ValueError("Only boards with lists can have rules")
        return board.columns

    def list_rules(self, scope: str | None = None) -> list[dict]:
        rules = self._meta().get("rules") if scope is None else self.get_board(scope).rules
        return [r for r in (rules or []) if isinstance(r, dict) and r.get("id")]

    def _store_rules(self, scope: str | None, rules: list[dict]) -> None:
        if scope is None:
            meta = self._meta()
            meta["rules"] = rules
            self._write_meta(meta)
        else:
            board = self.get_board(scope)
            board.rules = rules
            self._save_board(board)

    def add_rule(self, scope: str | None, raw: dict, index: int | None = None) -> dict:
        rules = self.list_rules(scope)
        if len(rules) >= R.MAX_RULES:
            raise ValueError(f"At most {R.MAX_RULES} rules")
        rule = R.clean_rule(raw, self._rule_lists(scope))
        rules.insert(len(rules) if index is None else max(0, min(index, len(rules))), rule)
        self._store_rules(scope, rules)
        return rule

    def toggle_rule(self, scope: str | None, rule_id: str, enabled: bool) -> None:
        rules = self.list_rules(scope)
        for rule in rules:
            if rule["id"] == rule_id:
                rule["enabled"] = enabled
                return self._store_rules(scope, rules)
        raise KeyError(rule_id)

    def delete_rule(self, scope: str | None, rule_id: str) -> tuple[int, dict]:
        rules = self.list_rules(scope)
        for i, rule in enumerate(rules):
            if rule["id"] == rule_id:
                del rules[i]
                self._store_rules(scope, rules)
                return i, rule
        raise KeyError(rule_id)

    def effective_rules(self, board) -> list[dict]:
        """Global rules (unless the board opts out) then the board's own, enabled ones only."""
        own = [r for r in self.list_rules(board.slug) if r.get("enabled", True)]
        if S.resolve(self.global_settings(), board.settings)["inherit_global_rules"]:
            return [r for r in self.list_rules(None) if r.get("enabled", True)] + own
        return own

    # -- engine ---------------------------------------------------------------

    def _run_rules(self, slug: str, event: str, card_id: str, now: datetime | None = None) -> list[str]:
        """Apply matching rules to a card. Returns what happened, e.g. ["moved to Done"]."""
        board = self.get_board(slug)
        if board.kind != "kanban":
            return []
        now = now or datetime.now()
        notes: list[str] = []
        for rule in self.effective_rules(board):
            try:
                card = self.get_card(slug, card_id)     # re-read: an earlier rule may have changed it
            except KeyError:
                break
            if R.matches(rule, event, card.column, card.tags):
                note = self._apply_rule(slug, board, card, rule, now)
                if note:
                    notes.append(note)
        return notes

    def _apply_rule(self, slug, board, card, rule: dict, now: datetime) -> str | None:
        do, arg = rule["do"], rule.get("arg")
        if do == "move":
            if arg not in board.columns or card.column == arg:
                return None
            self._move(slug, card.id, arg, 0)
            return f"moved to {arg}"
        if do == "complete":
            if card.done or card.repeat:
                return None
            self._set_done(slug, board, card, now)
            return "marked complete"
        if do == "uncomplete":
            if not card.done:
                return None
            self._unset_done(slug, card)
            return "marked not complete"
        if do == "add_tag":
            if arg in card.tags:
                return None
            card.tags = [*card.tags, arg]
            self._save(slug, card)
            return f"tagged #{arg}"
        if do == "remove_tag":
            if arg not in card.tags:
                return None
            card.tags = [t for t in card.tags if t != arg]
            self._save(slug, card)
            return f"removed #{arg}"
        if do == "archive":
            if card.archived:
                return None
            card.archived = True
            self._save(slug, card)
            self._reindex(slug)
            return "cleared from the list"
        return None

    # -- what a board shows ----------------------------------------------------------

    def view_columns(self, slug: str, now: datetime | None = None) -> tuple[dict[str, list], int]:
        """The lists as the board page shows them, honouring hide-completed settings and each
        card's own hidden flag (set_card_hidden -- a card hidden this way is left out of every
        card-listing view, not just this one; see that method's docstring). Returns (columns, how
        many *completed* cards are hidden -- individually hidden cards aren't counted here, they
        get their own badge from Store.hidden_cards). Never writes: hiding is a view."""
        settings = self.settings_for(slug)
        columns = self.cards_by_column(slug)
        days = settings["auto_hide_done_days"]
        cutoff = ((now or datetime.now()).date() - timedelta(days=days)).isoformat() if days else None
        hidden = 0
        for name, cards in columns.items():
            keep = []
            for card in cards:
                if card.hidden:
                    continue
                old = cutoff and card.completed and card.completed[:10] < cutoff
                if card.done and (settings["hide_done"] or old):
                    hidden += 1
                else:
                    keep.append(card)
            columns[name] = keep
        return columns, hidden
