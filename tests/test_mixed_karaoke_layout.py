"""Mixed one-/two-row passages retain fixed baselines and never lose sung words."""
import io
import re
import shutil

import numpy as np
from PIL import Image
import pytest

from kara_align.karaoke import ass as A
from kara_align.karaoke.render import preview_png
from kara_align.models import AlignmentResult, Coverage, KaraokeStyle, Line, Project, Segment, UnitTiming
from kara_align.reading.prepare import units_from_spec


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KARA_ALIGN_HOME", str(tmp_path / "home"))


def fixture():
    project = Project(name="Mixed rows")
    units = []
    for (text, reading), start, rows in zip(
            [("春風", "はるかぜ"), ("夏空", "なつぞら"), ("秋雨", "あきさめ"), ("冬雪", "ふゆゆき")],
            [1000, 3500, 5000, 7500], [None, 2, 2, None]):
        segment = Segment(surface=text, reading=reading, units=units_from_spec(reading, None, "ja"))
        line = Line(text=text, segments=[segment], karaoke_rows=rows, translation="Translation " + str(start))
        project.lyrics.lines.append(line)
        for i, unit in enumerate(segment.units):
            units.append(UnitTiming(unit_id=unit.id, line_id=line.id, segment_id=segment.id, reading=unit.reading,
                start_ms=start + i * 250, end_ms=start + (i + 1) * 250))
    result = AlignmentResult.model_construct(units=units, coverage=Coverage(), lines=[])
    style = KaraokeStyle()
    style.layout.lines, style.layout.arrangement, style.layout.wrap = 1, "center", "off"
    style.layout.margin_v, style.layout.line_spacing = 40, 24
    style.timing.advance_ms = style.timing.fade_in_ms = style.timing.fade_out_ms = 0
    style.countdown.intro = style.countdown.interlude = False
    return project, result, style


def main_rows(text, lyric):
    return [line.split(",", 9) for line in text.splitlines() if line.startswith("Dialogue: ")
            and line.split(",", 9)[3] == "KMain" and lyric in line.split(",", 9)[9]]


def position(row):
    return tuple(map(float, re.search(r"\\pos\(([-\d.]+),([-\d.]+)\)", row[9]).groups()))


def ms(time):
    h, m, s = time.split(":")
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


@pytest.mark.parametrize("size", [(1920, 1080), (1080, 1920)])
@pytest.mark.parametrize("translation", [False, True])
def test_single_baseline_matches_lower_double_row_and_double_rows_are_upper_left_lower_right(size, translation):
    project, result, style = fixture()
    style.translation.enabled, style.translation.position = translation, "line"
    text, _ = A.build_ass(project, result, style, size=size)
    rows = [main_rows(text, line.text)[0] for line in project.lyrics.lines]
    points = [position(row) for row in rows]
    assert points[0][1] == points[3][1] == points[2][1]
    assert points[1][1] < points[2][1]
    assert points[0][0] == points[3][0] == size[0] / 2
    assert points[1][0] < size[0] / 2 < points[2][0]
    # Next-line look-ahead is retained inside the selected double-row passage.
    assert ms(rows[1][1]) <= 4000 < ms(rows[1][2])
    assert ms(rows[2][1]) <= 4000 < ms(rows[2][2])
    # Early show / hold never leaks a single-row passage into its two-row neighbour.
    assert ms(rows[0][2]) <= ms(rows[1][1])
    assert max(ms(row[2]) for row in rows[1:3]) <= ms(rows[3][1])


def test_block_translation_tracks_each_passages_own_height():
    project, result, style = fixture()
    style.translation.enabled, style.translation.position = True, "block"
    text, _ = A.build_ass(project, result, style)
    rows = [line.split(",", 9) for line in text.splitlines()
            if line.startswith("Dialogue: ") and line.split(",", 9)[3] == "KTrans"]
    positions = {int(row[9].split("Translation ")[1]): position(row)[1] for row in rows}
    assert positions[1000] == positions[7500]
    assert positions[3500] == positions[5000] < positions[1000]


def test_overlapping_singing_gets_safe_extra_rows_and_is_never_cut_by_a_layout_change():
    style = KaraokeStyle()
    style.layout.lines = 1
    laid = [A.LaidLine(Line(text=str(i), karaoke_rows=rows), [], start, end)
            for i, (start, end, rows) in enumerate([(1000, 6000, 1), (3000, 7000, 2),
                                                   (4000, 6500, 2), (4500, 6500, 1)])]
    assert A.schedule(laid, style) == 2
    for line in laid:
        assert line.show_from <= line.start < line.end <= line.show_to
    # Logical slots change with passage size, but occupied physical baselines do not.
    physical = [A.lyric_rows(line, style) - 1 - line.slot for line in laid]
    assert len(set(physical)) == len(physical)


def test_wrapped_line_translation_outlives_its_first_piece_across_another_passage():
    style = KaraokeStyle()
    style.layout.lines = 1
    original = Line(text="A long wrapped line", karaoke_rows=2)
    first = A.LaidLine(original, [], 1000, 2000, translation="Whole translation", trans_until=8000)
    middle = A.LaidLine(Line(text="Another voice", karaoke_rows=1), [], 3000, 4000)
    last = A.LaidLine(original, [], 6000, 8000)
    laid = [first, middle, last]
    A.schedule(laid, style)
    windows = A.translation_windows(laid, style)
    assert len(windows) == 1 and windows[0][2] >= 8000


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs libass")
def test_libass_preview_shows_two_rows_only_inside_the_selected_passage():
    project, result, style = fixture()
    size = (960, 540)
    text, _ = A.build_ass(project, result, style, size=size)
    upper = position(main_rows(text, "夏空")[0])[1]
    # Split inside the actual gap, not halfway between baselines (the lower
    # line's ruby extends above that midpoint).
    cut = round(upper + style.layout.line_spacing * size[0] / A.REF_WIDTH / 2)
    def image(t):
        return np.asarray(Image.open(io.BytesIO(preview_png(text, t, size))).convert("RGB"))
    single, double = image(1500), image(4000)
    assert single[:cut].sum() == 0 and single[cut:].sum() > 0
    assert double[:cut].sum() > 0 and double[cut:].sum() > 0
