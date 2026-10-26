"""Per-passage row settings are atomic display edits, independent of alignment."""

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from kara_align import service as S
from kara_align.lyrics.pairing import merge_lines, split_line
from kara_align.models import (
    AlignmentResult, AudioAsset, BackendInfo, InputSnapshot, Line, LineTiming, LyricsDoc,
    Project, Segment, UnitTiming,
)
from kara_align.reading.prepare import units_from_spec
from kara_align.web.server import create_app


@pytest.fixture
def handle(tmp_path, monkeypatch):
    monkeypatch.setenv("KARA_ALIGN_HOME", str(tmp_path / "home"))
    h = S.create_dir(tmp_path / "projects" / "rows", "Rows")
    for text, reading in [("歌", "うた"), ("空", "そら")]:
        h.project.lyrics.lines.append(Line(text=text, segments=[
            Segment(surface=text, reading=reading, units=units_from_spec(reading, None, "ja"))]))
    h.project.lyrics.lines += [Line(text="备注", kind="meta", sing=False), Line(text="不唱", sing=False)]
    original = AudioAsset(role="original", sha256="a" * 64, duration_ms=10000,
                          sample_rate=16000, channels=1, num_samples=160000)
    h.project.audio = [original]
    snapshot = InputSnapshot(mode="plain", lyrics_text_revision=h.project.lyrics.text_revision(),
        lyrics_reading_revision=h.project.lyrics.reading_revision(), audio_asset_id=original.id,
        audio_sha256=original.sha256, audio_role="original", line_ids=[ln.id for ln in h.project.lyrics.sung_lines()],
        config_hash=S.config_hash(h.project.config))
    times = []
    for index, line in enumerate(h.project.lyrics.sung_lines()):
        for offset, unit in enumerate(line.units()):
            times.append(UnitTiming(unit_id=unit.id, line_id=line.id, segment_id=line.segments[0].id,
                reading=unit.reading, start_ms=1000 + index * 3000 + offset * 400,
                end_ms=1400 + index * 3000 + offset * 400))
    result = AlignmentResult(mode="plain", backend=BackendInfo(name="test", model_id="test", profile="ja",
        sample_rate=16000), config=h.project.config.model_copy(deep=True), snapshot=snapshot, units=times,
        lines=[LineTiming(line_id=ln.id, start_ms=1000 + i * 3000, end_ms=2000 + i * 3000)
               for i, ln in enumerate(h.project.lyrics.sung_lines())],
        stats={"detail_revision": h.project.lyrics.detail_revision()})
    h.project.results, h.project.active_result_id = [result], result.id
    h.save()
    return h


@pytest.mark.parametrize("value", [True, False, 0, 3, -1, "1", 1.0])
def test_line_row_override_refuses_coercion_and_invalid_values(value):
    with pytest.raises(ValidationError):
        Line(text="旧歌词", karaoke_rows=value)


def test_old_projects_follow_global_and_override_survives_round_trip():
    project = Project.model_validate({"lyrics": {"lines": [{"text": "Old lyric"}]}})
    assert project.lyrics.lines[0].karaoke_rows is None
    for value in (None, 1, 2):
        project.lyrics.lines[0].karaoke_rows = value
        assert Project.model_validate_json(project.model_dump_json()).lyrics.lines[0].karaoke_rows == value


def test_batch_save_changes_only_display_rows_and_does_not_prepare_or_realign(handle, monkeypatch):
    h = handle
    lines = h.project.lyrics.sung_lines()
    ids = [ln.id for ln in lines]
    previous_results = [r.model_dump() for r in h.project.results]
    revisions = (h.project.lyrics.text_revision(), h.project.lyrics.reading_revision(),
                 h.project.lyrics.detail_revision(), h.project.lyrics.detail_revision("lrc"))
    original_lines = [ln.model_dump(exclude={"karaoke_rows"}) for ln in h.project.lyrics.lines]
    saved = []
    original_save = h.save

    def save():
        saved.append(True)
        original_save()

    monkeypatch.setattr(h, "save", save)
    S.set_karaoke_line_layout(h, [*ids, ids[0]], 2)
    assert saved == [True]
    assert [ln.karaoke_rows for ln in lines] == [2, 2]
    assert [ln.model_dump(exclude={"karaoke_rows"}) for ln in h.project.lyrics.lines] == original_lines
    assert [r.model_dump() for r in h.project.results] == previous_results
    assert S.staleness(h.project, h.project.result()) is None
    assert revisions == (h.project.lyrics.text_revision(), h.project.lyrics.reading_revision(),
                         h.project.lyrics.detail_revision(), h.project.lyrics.detail_revision("lrc"))
    assert [ln.karaoke_rows for ln in S.open_dir(h.dir).project.lyrics.sung_lines()] == [2, 2]
    S.set_karaoke_line_layout(h, [ids[0]], 1)
    S.set_karaoke_line_layout(h, [ids[1]], None)
    assert [ln.karaoke_rows for ln in h.project.lyrics.sung_lines()] == [1, None]
    assert h.project.karaoke.layout.lines == 2


@pytest.mark.parametrize("invalid", ["missing", "meta", "not_sung", "empty", "bool"])
def test_invalid_batch_is_atomic_in_memory_and_on_disk(handle, invalid):
    h = handle
    good, _, meta, not_sung = h.project.lyrics.lines
    ids, rows = [good.id], 2
    if invalid == "missing": ids.append("unknown-line")
    elif invalid == "meta": ids.append(meta.id)
    elif invalid == "not_sung": ids.append(not_sung.id)
    elif invalid == "empty": ids = []
    else: rows = True
    disk_before = (h.dir / "project.json").read_bytes()
    with pytest.raises(S.ServiceError):
        S.set_karaoke_line_layout(h, ids, rows)
    assert all(ln.karaoke_rows is None for ln in h.project.lyrics.lines)
    assert (h.dir / "project.json").read_bytes() == disk_before


def test_http_batch_returns_updated_project_and_null_restores_global(handle):
    h = handle
    ids = [ln.id for ln in h.project.lyrics.sung_lines()]
    with TestClient(create_app(h.dir.parent)) as client:
        url = f"/api/projects/{h.dir.name}/karaoke/line-layout"
        response = client.put(url, json={"line_ids": ids, "rows": 2})
        assert response.status_code == 200, response.text
        assert [ln["karaoke_rows"] for ln in response.json()["project"]["lyrics"]["lines"][:2]] == [2, 2]
        restored = client.put(url, json={"line_ids": ids, "rows": None})
        assert restored.status_code == 200
        assert [ln["karaoke_rows"] for ln in restored.json()["project"]["lyrics"]["lines"][:2]] == [None, None]
        for value in (True, False, 0, 3, "1", 1.0):
            assert client.put(url, json={"line_ids": ids, "rows": value}).status_code == 422
        assert client.put(url, json={"line_ids": [], "rows": 1}).status_code == 422
        assert client.put(url, json={"line_ids": ids}).status_code == 422
        assert client.put(url, json={"line_ids": [ids[0], "missing"], "rows": 1}).status_code == 400
    assert [ln.karaoke_rows for ln in S.open_dir(h.dir).project.lyrics.sung_lines()] == [None, None]


@pytest.mark.parametrize("rows", [None, 1, 2])
def test_merge_uses_first_line_and_both_split_parts_inherit_it(rows):
    first = Line(text="青", karaoke_rows=rows)
    second = Line(text="空", karaoke_rows=2 if rows != 2 else 1)
    document = LyricsDoc(lines=[first, second])
    merged = merge_lines(document, [first.id, second.id])
    assert merged.lines[0].karaoke_rows == rows
    split = split_line(merged, merged.lines[0].id, 1)
    assert [ln.text for ln in split.lines] == ["青", "空"]
    assert [ln.karaoke_rows for ln in split.lines] == [rows, rows]
