"""Opacity must affect every rendered layer while preserving independent credits."""

import io
import shutil

import numpy as np
from PIL import Image
from pydantic import ValidationError
import pytest

from kara_align.karaoke.ass import apply_opacity, build_ass
from kara_align.karaoke.render import preview_png
from kara_align.models import AlignmentResult, Coverage, KaraokeStyle, Line, Project, Segment, UnitTiming
from kara_align.reading.prepare import units_from_spec


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                  reason="needs ffmpeg with libass")
SIZE = (960, 540)


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("KARA_ALIGN_HOME", str(tmp_path / "home"))


def fixture(effect="pulse"):
    project = Project(name="Opacity")
    segments = [Segment(surface=surface, reading=reading, units=units_from_spec(reading, None, "ja"))
                for surface, reading in [("青", "あお"), ("空", "そら")]]
    line = Line(text="青空", segments=segments, translation="A blue sky")
    project.lyrics.lines = [line]
    units, start = [], 1000
    for segment in segments:
        for unit in segment.units:
            units.append(UnitTiming(unit_id=unit.id, line_id=line.id, segment_id=segment.id,
                reading=unit.reading, start_ms=start, end_ms=start + 700))
            start += 700
    result = AlignmentResult.model_construct(units=units, coverage=Coverage(), lines=[])
    style = KaraokeStyle()
    style.layout.lines = 1
    style.ruby.sweep = "base"
    style.translation.enabled, style.translation.position = True, "line"
    style.glow.enabled, style.glow.strength = True, 60
    style.text.shadow_color = "#FFFFFF"  # a leaked shadow is visible against black
    style.timing.advance_ms = 0
    style.effects.kind = effect
    style.info.credits_enabled, style.info.creator = True, "Opacity Test"
    style.info.show_models = style.info.show_fonts = False
    style.info.position = "top-center"
    style.info.start_ms, style.info.duration_ms = 0, 5000
    return project, result, style


def render(text, t_ms=1800):
    return np.asarray(Image.open(io.BytesIO(preview_png(text, t_ms, SIZE))).convert("RGB"))


def without_info(text):
    return [line for line in text.splitlines()
            if not line.startswith("Style: KInfo,")
            and not (line.startswith("Dialogue: ") and line.split(",", 9)[3] == "KInfo")]


def test_old_styles_default_to_opaque_and_round_trip_new_values():
    legacy = KaraokeStyle.model_validate({"text": {"size": 80}, "info": {"creator": "Name"}})
    assert (legacy.text.opacity, legacy.info.opacity) == (100, 100)
    for value in (0, 50, 100):
        style = KaraokeStyle.model_validate({"text": {"opacity": value}, "info": {"opacity": value}},
                                           context={"strict": True})
        saved = KaraokeStyle.model_validate(style.model_dump())
        assert (saved.text.opacity, saved.info.opacity) == (value, value)
    for section in ("text", "info"):
        for invalid in (-1, 101):
            with pytest.raises(ValidationError):
                KaraokeStyle.model_validate({section: {"opacity": invalid}}, context={"strict": True})


def test_full_opacity_preserves_ass_bytes_and_default_render():
    raw = "[Script Info]\r\n; Preserve whitespace and line endings\r\n"
    assert apply_opacity(raw) == raw
    project, result, style = fixture()
    default, _ = build_ass(project, result, style, size=SIZE)
    style.text.opacity = style.info.opacity = 100
    explicit, _ = build_ass(project, result, style, size=SIZE)
    assert explicit == default


def test_composes_existing_alpha_and_keeps_animation_fade_and_karaoke_tags():
    raw = (
        "Style: KGlow,Arial,20,&HFFFFFFFF,&HFFFFFFFF,&H00FFFFFF,&H40010203,0,0\n"
        "Style: KInfo,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0\n"
        "Dialogue: 3,0:00:00.00,0:00:02.00,KGlow,,0,0,0,,"
        "{\\1a&HFF&\\3a&H80&\\4a&H40&\\fad(100,200)\\t(0,500,0.6,\\3a&HFF&)}"
        "{\\kf50}text,with comma\n"
        "Dialogue: 9,0:00:00.00,0:00:02.00,KInfo,,0,0,0,,{\\1a&H18&}Credits\n"
    )
    changed = apply_opacity(raw, 50, 100)
    assert "&HFFFFFFFF,&HFFFFFFFF,&H7FFFFFFF,&H9F010203" in changed
    assert "\\1a&HFF&\\3a&HBF&\\4a&H9F&" in changed
    assert "\\fad(100,200)\\t(0,500,0.6,\\3a&HFF&)" in changed
    assert "{\\kf50}text,with comma" in changed
    assert [line for line in changed.splitlines() if "KInfo" in line] == [
        line for line in raw.splitlines() if "KInfo" in line]


@needs_ffmpeg
@pytest.mark.parametrize("effect", ["none", "pulse", "ring", "shine", "sparkle", "petals", "hearts", "ball"])
def test_zero_global_opacity_leaves_no_text_glow_shadow_countdown_or_effect_pixels(effect):
    project, result, style = fixture(effect)
    opaque, _ = build_ass(project, result, style, size=SIZE)
    assert all(f",{name}," in opaque for name in ("KMain", "KRuby", "KTrans", "KGlow", "KDots"))
    if effect != "none":
        assert ",KFx," in opaque
    style.text.opacity = style.info.opacity = 0
    hidden, _ = build_ass(project, result, style, size=SIZE)
    # The first instant includes countdown dots; the second includes live syllable effects.
    for time in (500, 1750):
        assert render(opaque, time).max() > 0
        assert render(hidden, time).max() == 0


@needs_ffmpeg
@pytest.mark.parametrize("layout", ["card", "single-line"])
def test_info_opacity_is_independent_and_hides_its_fill_glow_border_and_accent_bar(layout):
    project, result, style = fixture()
    style.info.credits_layout = layout
    full, _ = build_ass(project, result, style, size=SIZE)
    full_png = render(full)
    style.info.opacity = 0
    no_info, _ = build_ass(project, result, style, size=SIZE)
    no_info_png = render(no_info)
    assert without_info(no_info) == without_info(full)
    split = round(SIZE[1] * 0.45)
    assert full_png[:split].max() > 0
    assert no_info_png[:split].max() == 0
    assert np.array_equal(no_info_png[split:], full_png[split:])
    style.info.opacity, style.text.opacity = 100, 0
    info_only, _ = build_ass(project, result, style, size=SIZE)
    info_only_png = render(info_only)
    assert np.array_equal(info_only_png[:split], full_png[:split])
    assert info_only_png[split:].max() == 0


@needs_ffmpeg
def test_half_opacity_renders_between_zero_and_full_without_changing_event_timing():
    project, result, style = fixture()
    outputs, brightness = {}, {}
    for opacity in (0, 50, 100):
        style.text.opacity = style.info.opacity = opacity
        outputs[opacity], _ = build_ass(project, result, style, size=SIZE)
        brightness[opacity] = int(render(outputs[opacity]).sum())
    assert brightness[0] == 0 < brightness[50] < brightness[100]
    prefix = lambda text: [line.split(",", 9)[:9] for line in text.splitlines() if line.startswith("Dialogue: ")]
    assert prefix(outputs[0]) == prefix(outputs[50]) == prefix(outputs[100])
    # No opacity setting turns the glow's originally hidden fill into visible text.
    for text in outputs.values():
        glow = next(line for line in text.splitlines() if line.startswith("Style: KGlow,"))
        assert glow.split(",")[3:5] == ["&HFFFFFFFF", "&HFFFFFFFF"]
