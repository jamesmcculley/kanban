"""Advanced-search narrowing -- see kanban/search.py."""

from dataclasses import dataclass, field

from kanban import search as S


@dataclass
class _Board:
    slug: str


@dataclass
class _Card:
    tags: list = field(default_factory=list)
    priority: str | None = None
    done: bool = False


def _pair(slug="a", tags=None, priority=None, done=False):
    return (_Board(slug), _Card(tags or [], priority, done))


def test_refine_with_nothing_set_matches_everything():
    results = [_pair(), _pair(done=True)]
    assert S.refine(results) == results


def test_refine_by_tags_is_any_of_the_checked_tags():
    results = [_pair(tags=["home"]), _pair(tags=["work"]), _pair(tags=[])]
    assert len(S.refine(results, tags=["home", "errand"])) == 1


def test_refine_by_priority_none_bucket():
    results = [_pair(priority="high"), _pair(priority=None)]
    assert len(S.refine(results, priorities=["none"])) == 1
    assert len(S.refine(results, priorities=["high"])) == 1


def test_refine_by_board():
    results = [_pair(slug="a"), _pair(slug="b")]
    assert [b.slug for b, c in S.refine(results, boards=["b"])] == ["b"]


def test_refine_by_status_open_or_done():
    results = [_pair(done=False), _pair(done=True)]
    assert len(S.refine(results, statuses=["open"])) == 1
    assert len(S.refine(results, statuses=["done"])) == 1
    # both or neither checked -> no narrowing, same as the export dialog's priority convention
    assert len(S.refine(results, statuses=["open", "done"])) == 2
    assert len(S.refine(results, statuses=[])) == 2


def test_refine_combines_all_filters_with_and():
    results = [_pair(slug="a", tags=["home"], priority="high", done=False),
              _pair(slug="a", tags=["home"], priority="low", done=False)]
    result = S.refine(results, tags=["home"], priorities=["high"], boards=["a"], statuses=["open"])
    assert len(result) == 1 and result[0][1].priority == "high"
