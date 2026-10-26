"""Production credits must describe the actual render and stay out of the outro."""
from pydantic import ValidationError
import pytest

from kara_align.karaoke.info import info_events, production_lines
from kara_align.models import AlignmentResult, AudioAsset, AudioSource, BackendInfo, KaraokeStyle, Project


def project_and_result():
    project = Project(name="Demo")
    original = AudioAsset.model_construct(role="original", sha256="a" * 64, duration_ms=30000)
    vocals = AudioAsset.model_construct(role="vocals", sha256="b" * 64, duration_ms=30000,
        source=AudioSource(model="actual-separation.ckpt", parent_sha256=original.sha256, kind="separation"))
    instrumental = AudioAsset.model_construct(role="instrumental", sha256="c" * 64, duration_ms=30000,
        source=AudioSource(model="actual-separation.ckpt", parent_sha256=original.sha256, kind="separation"))
    project.audio = [original, vocals, instrumental]
    result = AlignmentResult.model_construct(backend=BackendInfo(name="mms-ja", model_id="actual-aligner",
        profile="ja", sample_rate=16000))
    return project, result


def test_auto_credits_use_current_stems_and_resolved_deduplicated_fonts():
    project, result = project_and_result()
    style = KaraokeStyle()
    style.info.credits_enabled, style.info.creator = True, "  My Creator  "
    style.text.font = "An unavailable requested font"
    lines = production_lines(project, style, result=result, font_families=["Resolved JP", "Resolved JP", "Resolved SC"])
    assert lines == ["视频制作者：My Creator", "分离模型：actual-separation.ckpt",
                     "字幕字体：Resolved JP / Resolved SC"]
    project.asset("original").sha256 = "d" * 64
    assert not any("actual-separation" in line for line in production_lines(project, style, result=result))


def test_custom_text_switches_and_legacy_style_round_trip():
    project, result = project_and_result()
    assert production_lines(project, KaraokeStyle(), result=result, font_families=["font"]) == []
    style = KaraokeStyle.model_validate({"info": {"credits_enabled": True, "creator": "Name",
        "model_text": "Custom model", "font_text": "Custom font"}}, context={"strict": True})
    assert production_lines(project, style, result=result, font_families=["font"]) == [
        "视频制作者：Name", "分离模型：Custom model", "字幕字体：Custom font"]
    style.info.show_models = style.info.show_fonts = False
    assert production_lines(project, style, result=result) == ["视频制作者：Name"]
    with pytest.raises(ValidationError):
        KaraokeStyle.model_validate({"info": {"creator": "x" * 121}}, context={"strict": True})
    assert KaraokeStyle.model_validate(style.model_dump()).info.creator == "Name"


def test_credits_are_independent_of_song_switch_and_opening_only():
    project, result = project_and_result()
    style = KaraokeStyle()
    style.info.credits_enabled, style.info.creator = True, "My Creator"
    style.info.start_ms, style.info.duration_ms, style.info.outro_duration_ms = 0, 5000, 5000
    events = info_events(project, style, 1920, 1080, 1, "Noto Sans CJK JP", 0,
                         result=result, font_families=["Noto Sans CJK JP"], end_ms=30000)
    assert any("视频制作者：My Creator" in line for line in events)
    assert all(float(line.split(",")[1].split(":")[-1]) < 6 for line in events)
    # The existing custom song card still appears in the outro, without production credits.
    style.info.enabled = True
    project.song_info_text = "Custom song title"
    events = info_events(project, style, 1920, 1080, 1, "Noto Sans CJK JP", 0,
                         result=result, font_families=["Noto Sans CJK JP"], end_ms=30000)
    outro = [line for line in events if float(line.split(",")[1].split(":")[-1]) >= 25]
    assert any("Custom song title" in line for line in outro)
    assert not any("My Creator" in line or "actual-separation" in line or "字幕字体" in line for line in outro)


def test_new_task_credits_defaults_also_apply_with_an_older_saved_style(monkeypatch):
    from kara_align.settings import SimpleSettings, TaskStyleOptions
    from kara_align.pipeline import resolve_task_style
    from kara_align.karaoke import styles

    simple = SimpleSettings()
    simple.karaoke.info.credits_enabled = True
    simple.karaoke.info.creator = "My Team"
    simple.karaoke.info.credits_layout = "single-line"
    simple.karaoke.info.duration_ms = 5000
    simple.karaoke.info.opacity = 65
    saved = KaraokeStyle()
    saved.text.font = "Saved Subtitle Font"
    saved.info.enabled = True
    monkeypatch.setattr(styles, "get_style", lambda _id: saved.model_copy(deep=True))
    resolved, _, _ = resolve_task_style(simple, TaskStyleOptions(source="saved", saved_id="test"))
    assert resolved.info.creator == "My Team" and resolved.info.credits_enabled
    assert resolved.info.duration_ms == 5000 and resolved.info.enabled
    assert resolved.info.credits_layout == "single-line"
    assert resolved.info.opacity == 65
    assert resolved.text.font == "Saved Subtitle Font"


def test_longer_credit_times_are_validated_and_round_trip_without_clamping():
    style = KaraokeStyle.model_validate({"info": {"start_ms": 3600000, "duration_ms": 600000,
        "outro_duration_ms": 600000, "credits_layout": "single-line"}}, context={"strict": True})
    saved = KaraokeStyle.model_validate(style.model_dump()).info
    assert (saved.start_ms, saved.duration_ms, saved.outro_duration_ms) == (3600000, 600000, 600000)
    assert saved.credits_layout == "single-line"
    for name, value in [("start_ms", 3600001), ("duration_ms", 600001), ("outro_duration_ms", 600001)]:
        with pytest.raises(ValidationError):
            KaraokeStyle.model_validate({"info": {name: value}}, context={"strict": True})


def test_single_line_keeps_all_credits_on_one_fitted_row_and_out_of_the_outro():
    import re
    from kara_align.karaoke.fonts import Measurer

    project, result = project_and_result()
    style = KaraokeStyle()
    style.info.credits_enabled = style.info.enabled = True
    style.info.credits_layout, style.info.creator = "single-line", "My Creator"
    style.info.start_ms, style.info.duration_ms, style.info.outro_duration_ms = 20000, 30000, 5000
    project.song_info_text = "My Song Title"
    events = info_events(project, style, 1920, 1080, 1, "Noto Sans CJK JP", 0,
                         result=result, font_families=["Noto Sans CJK JP"], end_ms=120000)
    opening = [line for line in events if line.startswith("Dialogue: 9,0:00:20.")]
    assert len(opening) == 1
    row = opening[0]
    assert "My Creator" in row and "actual-separation.ckpt" in row
    assert "actual-aligner" not in row and "对齐模型" not in row
    assert "字幕字体" in row and " | " in row and "\\N" not in row and "\\q2" in row
    family, size = re.search(r"\\fn(.+?)\\fs([\d.]+)", row).groups()
    assert Measurer(family, style.text.bold, float(size)).width(row.split("}", 1)[1]) <= 1920 - 2 * style.info.margin + 2
    outro = [line for line in events if ",0:01:5" in line]
    assert any("My Song Title" in line for line in outro)
    assert not any("My Creator" in line or "字幕字体" in line for line in outro)


def test_alignment_model_never_fills_in_for_missing_separation_model():
    project, result = project_and_result()
    style = KaraokeStyle()
    style.info.credits_enabled = True
    style.info.show_fonts = False
    project.audio = [project.asset("original")]
    assert production_lines(project, style, result=result) == []


@pytest.mark.parametrize("position,anchor,x", [("top-left", 7, 56), ("top-center", 8, 960), ("top-right", 9, 1864)])
def test_single_line_supports_left_center_and_right(position, anchor, x):
    project, result = project_and_result()
    style = KaraokeStyle.model_validate({"info": {"credits_enabled": True, "credits_layout": "single-line",
        "position": position, "creator": "Creator", "show_models": False, "show_fonts": False}}, context={"strict": True})
    events = info_events(project, style, 1920, 1080, 1, "Noto Sans CJK JP", 0, result=result)
    text_rows = [line for line in events if "视频制作者：Creator" in line]
    assert text_rows
    assert all(f"\\an{anchor}\\pos({x:.1f},56.0)" in line for line in text_rows)
    assert KaraokeStyle.model_validate(style.model_dump()).info.position == position


def test_centered_card_moves_below_an_obstruction_and_keeps_its_center_anchor():
    import re

    project, result = project_and_result()
    style = KaraokeStyle()
    style.info.credits_enabled, style.info.creator = True, "Creator"
    style.info.position = "top-center"
    style.info.start_ms, style.info.duration_ms = 0, 5000
    warnings = []
    events = info_events(project, style, 1920, 1080, 1, "Noto Sans CJK JP", 0, result=result,
        boxes=[(0, 5000, 850, 0, 1070, 110)], warnings=warnings)
    rows = [line for line in events if "视频制作者：Creator" in line]
    assert rows and all("\\an8" in line for line in rows)
    move = re.search(r"\\move\([^,]+,([^,]+),([^,]+),", rows[0])
    assert float(move[1]) > 110 and float(move[2]) == 960
    assert warnings == []
