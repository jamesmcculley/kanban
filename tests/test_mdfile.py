from kanban.mdfile import read_md, write_md


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "card.md"
    write_md(path, {"id": "abc", "title": "x"}, "notes here")
    meta, body = read_md(path)
    assert meta == {"id": "abc", "title": "x"} and body == "notes here"


def test_write_leaves_no_stray_temp_file(tmp_path):
    path = tmp_path / "card.md"
    write_md(path, {"id": "abc"})
    assert not (tmp_path / "card.md.tmp").exists()
    assert path.exists()


def test_overwrite_replaces_cleanly(tmp_path):
    path = tmp_path / "card.md"
    write_md(path, {"id": "abc", "title": "first"})
    write_md(path, {"id": "abc", "title": "second"})
    meta, _ = read_md(path)
    assert meta["title"] == "second"
    assert not (tmp_path / "card.md.tmp").exists()
