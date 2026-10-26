"""Song title card: title / artist / album / credits in a top corner at the start
(and, with ``info.outro``, the same card again at the end).

The lines come from the song data (lyrics metadata filled from the music
platform, credit lines such as ``作词：…`` kept in the lyrics) and the fields the
style picks, unless the project has its own text (``Project.song_info_text``,
one line each, the first is the title).  The card slides in beside a thin accent
bar in the lyrics' sung colour, uses the lyrics' font, outline and glow, and
fades out after ``duration_ms`` — or before the first lyric / translation that
would share the top edge (after 2 s at least), and always before anything that
would be drawn where the card is (then without the 2 s; a card that would not
last a second is left out).

The ending card is the mirror image: it stays until the end of the song for
``outro_duration_ms``, comes in only after the last lyric / translation along the
top edge has gone (staying 2 s at least) and after anything drawn where it is.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from ..models import AlignmentResult, KaraokeStyle, Project
from .fonts import BUNDLED_JP, HAN_FAMILIES, Measurer, covering

LABELS = {"title": "歌名", "artist": "歌手", "album": "专辑", "lyricist": "作词", "composer": "作曲", "arranger": "编曲"}
# a label may name several roles ("作词/作曲", "词曲", "Lyrics & Music"): each one is filled
_CREDIT = {"lyricist": re.compile(r"作词|作詞|^[词詞]|lyric|written", re.I),
           "arranger": re.compile(r"编曲|編曲|arrang", re.I),
           "composer": re.compile(r"作曲|^曲$|[词詞]曲|compos|music", re.I)}
_LABEL = re.compile(r"^\s*([^:：]{1,16}?)\s*[:：]\s*(.+?)\s*$")

L_INFO_GLOW, L_INFO = 8, 9
_IN_MS, _OUT_MS, _STAGGER, _BAR_MS = 450, 400, 90, 380  # slide in / out, between lines, bar grow / shrink
_BAR = 6  # accent bar width (px at 1920 wide)


def song_fields(project: Project) -> dict[str, str]:
    """Every field the song data can fill (empty ones left out)."""
    meta = project.lyrics.meta
    out = {"title": meta.title or project.name or "", "artist": meta.artist or "", "album": meta.album or ""}
    for ln in project.lyrics.lines:
        if ln.kind != "meta":
            continue
        m = _LABEL.match(ln.text)
        if not m:
            continue
        for key, pat in _CREDIT.items():
            if pat.search(m.group(1).strip()) and not out.get(key):
                out[key] = m.group(2)
    return {k: v.strip() for k, v in out.items() if v and v.strip()}


def auto_lines(project: Project, style: KaraokeStyle) -> list[str]:
    fields = song_fields(project)
    lines = []
    for f in style.info.fields:
        v = fields.get(f)
        if v:
            lines.append(f"{LABELS[f]}：{v}" if f in ("lyricist", "composer", "arranger") else v)
    return lines


def info_lines(project: Project, style: KaraokeStyle) -> list[str]:
    """The card's lines: the project's own text, or the chosen fields."""
    if project.song_info_text is not None:
        return [x.strip() for x in project.song_info_text.splitlines() if x.strip()]
    return auto_lines(project, style)


def production_lines(project: Project, style: KaraokeStyle, *, result: Optional[AlignmentResult] = None,
                     font_families: Sequence[str] = ()) -> list[str]:
    """Opening-only credits. Automatic values describe this render, never the global defaults."""
    info = style.info
    if not info.credits_enabled:
        return []

    def one_line(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    lines = []
    creator = one_line(info.creator)
    if creator:
        lines.append(f"视频制作者：{creator}")
    if info.show_models:
        custom = one_line(info.model_text)
        if custom:
            lines.append(f"分离模型：{custom}")
        else:
            original = project.asset("original")
            parent = original.sha256 if original else None
            models = []
            for role in ("vocals", "instrumental"):
                stem = project.asset(role)
                if stem is None or stem.source.parent_sha256 not in (None, parent):
                    continue  # a stem from the replaced original is not used in this video
                name = one_line(stem.source.model or "")
                if name and name not in models:
                    models.append(name)
            lines.extend(f"分离模型：{name}" for name in models)
    if info.show_fonts:
        custom = one_line(info.font_text)
        fonts = list(dict.fromkeys(one_line(f) for f in font_families if one_line(f)))
        if custom or fonts:
            lines.append(f"字幕字体：{custom or ' / '.join(fonts)}")
    return lines


# where a card line may wrap: after a space / "・" / "/", or before a bracket, a tilde or " - " —
# preferably not inside brackets (「(M@STER VERSION)」, 「～For Miria MIX～」 stay together)
_OPEN, _CLOSE, _TILDES = "(（[［【〈《「『", ")）]］】〉》」』", "~〜～"
_BREAK_AFTER = " \u3000・/／、，,"


def _depths(text: str) -> list[int]:
    """Bracket depth before each character (a tilde opens when another one follows, else closes)."""
    out, depth, in_tilde = [], 0, False
    for i, c in enumerate(text):
        out.append(depth)
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth = max(0, depth - 1)
        elif c in _TILDES:
            if in_tilde:
                depth, in_tilde = max(0, depth - 1), False
            elif any(x in _TILDES for x in text[i + 1:]):
                depth, in_tilde = depth + 1, True
    return out


def wrap_text(text: str, width, max_w: float) -> list[str]:
    """``text`` in rows no wider than ``max_w`` (``width``: text -> px), broken where it reads well:
    the longest first row that ends at a good place outside brackets, else at a good place, else
    between any two characters; spaces at the break are dropped."""
    text = text.strip()
    rows: list[str] = []
    while text and width(text) > max_w:
        depth = _depths(text)
        cuts = [i for i in range(1, len(text))
                if text[i] in _OPEN or (text[i] in _TILDES and depth[i] == 0) or text[i - 1] in _BREAK_AFTER
                or text[i:i + 3] == " - "]
        fit = [i for i in cuts if width(text[:i].rstrip()) <= max_w]
        outside = [i for i in fit if depth[i] == 0]
        if outside or fit:
            i = (outside or fit)[-1]
        else:  # no good place fits: as many characters as fit
            i = 1
            while i < len(text) and width(text[:i + 1]) <= max_w:
                i += 1
        head, text = text[:i].rstrip(" \u3000"), text[i:].lstrip(" \u3000")
        if head:
            rows.append(head)
    if text:
        rows.append(text)
    return rows or [""]


def info_events(project: Project, style: KaraokeStyle, W: int, H: int, k: float, family: str,
                time_offset_ms: float, *,
                boxes: Sequence[tuple[float, float, float, float, float, float]] = (),
                warnings: Optional[list[str]] = None, end_ms: Optional[float] = None,
                result: Optional[AlignmentResult] = None, font_families: Sequence[str] = ()) -> list[str]:
    """Dialogue lines of the card (style ``KInfo``) in its corner at the top, for its whole
    duration: when a translation or lyric (``boxes``: (from, to, x0, y0, x1, y1) of what else is
    drawn) would be where the card is, the card gets narrower (its lines wrap) so it ends before it.
    ``end_ms`` (the end of the song on the subtitles' timeline): the ending card too."""
    info = style.info
    song_lines = info_lines(project, style) if info.enabled else []
    credits = production_lines(project, style, result=result, font_families=font_families or (family,))
    lines = song_lines + credits if song_lines else (["视频制作", *credits] if credits else [])
    if not lines:
        return []
    # a title / album with characters the lyric font lacks: a font with all of them (Windows: libass would
    # fill them in from a font of its own, at another size)
    family = covering(family, style.text.bold, "".join(lines), [BUNDLED_JP, *HAN_FAMILIES])
    t0 = max(0.0, info.start_ms + time_offset_ms)
    t1 = t0 + info.duration_ms
    if credits and info.credits_layout == "single-line":
        events = _single_line(song_lines + credits, style, W, H, k, family, t0, t1, boxes, warnings)
    else:
        events = _card(lines, style, W, H, k, family, t0, t1, boxes, warnings, at_end=False)
    if info.enabled and song_lines and info.outro and end_ms is not None and end_ms - info.outro_duration_ms > t1:
        events += _card(song_lines, style, W, H, k, family, end_ms - info.outro_duration_ms, end_ms, boxes, warnings,
                        at_end=True)
    return events


def _single_line(lines: list[str], style: KaraokeStyle, W: int, H: int, k: float, family: str,
                 t0: float, t1: float,
                 boxes: Sequence[tuple[float, float, float, float, float, float]],
                 warnings: Optional[list[str]]) -> list[str]:
    """A single full-width opening line, fitted to the frame and kept clear of subtitles."""
    info, txt, glow = style.info, style.text, style.glow
    text = "   |   ".join(lines)
    margin = info.margin * k
    max_w = max(1.0, W - 2 * margin)
    requested_size = max(1.0, info.size * k)
    size = requested_size
    # Measurement uses a sub-pixel font size grid; remeasure after fitting rather than
    # assuming that glyph advances scale exactly linearly at every rounded size.
    for _ in range(8):
        size = round(size, 2)
        width = Measurer(family, txt.bold, size).width(text)
        if width <= max_w:
            break
        size = max(0.01, size * min(0.995, max_w / max(width, 1.0)))
    fit = min(1.0, size / requested_size)
    scale_x = f"\\fscx{min(100.0, max_w / max(width, 1.0) * 100):.2f}" if width > max_w else ""
    if size < 12 * k and warnings is not None:
        warnings.append("片头单行文字较多，字号已缩小；可精简模型或字体说明，让文字更清楚")
    pad = (txt.outline + (glow.size + glow.blur if glow.enabled else 0)) * k * fit + 4 * k

    def hits(top):
        return [box for box in boxes if box[2] < W - margin + pad and margin - pad < box[4]
                and box[3] < top + size + pad and top - pad < box[5]
                and box[0] - 200 < t1 and t0 < box[1] + 200]

    tops = [margin] + sorted({box[5] + pad + 6 * k for box in boxes if box[5] + pad + 6 * k > margin
                             and box[0] - 200 < t1 and t0 < box[1] + 200})
    top = next((y for y in tops if y + size + pad <= H * 0.45 and not hits(y)), None)
    if top is None:
        for y in tops:
            if y + size + pad > H * 0.45:
                continue
            end = min([t1, *[box[0] - 200 for box in hits(y)]])
            if end - t0 >= 1000:
                top, t1 = y, end
                break
    if top is None or t1 <= t0:
        if warnings is not None:
            warnings.append("顶部歌词或翻译占满了空间，片头单行署名没有显示；可调整出现时间或字号")
        return []

    anchor, x = {"top-left": (7, margin), "top-center": (8, W / 2),
                 "top-right": (9, W - margin)}[info.position]
    fade_in, fade_out = min(350, (t1 - t0) / 4), min(400, (t1 - t0) / 4)
    tags = (f"\\an{anchor}\\pos({x:.1f},{top:.1f})\\fn{family}\\fs{size:.2f}\\b{int(txt.bold)}{scale_x}\\q2"
            f"\\fad({fade_in:.0f},{fade_out:.0f})")
    body = _escape(text)
    events = []
    if glow.enabled:
        look = (f"\\1a&HFF&\\3c{_bgr(glow.color_unsung)}"
                f"\\3a&H{int(round(255 * (1 - glow.strength / 100))):02X}&"
                f"\\bord{glow.size * k * fit * 0.5:.2f}\\blur{glow.blur * k * fit:.2f}\\shad0")
        events.append(_dialogue(L_INFO_GLOW, t0, t1, tags + look, body))
    look = (f"\\1c{_bgr(info.color or txt.color_unsung)}\\3c{_bgr(txt.outline_color)}"
            f"\\bord{txt.outline * k * fit * 0.55:.2f}\\shad{txt.shadow * k * fit * 0.6:.2f}")
    events.append(_dialogue(L_INFO, t0, t1, tags + look, body))
    return events


def _card(lines: list[str], style: KaraokeStyle, W: int, H: int, k: float, family: str, t0: float, t1: float,
          boxes: Sequence[tuple[float, float, float, float, float, float]], warnings: Optional[list[str]], *,
          at_end: bool) -> list[str]:
    """One showing of the card from t0 to t1, in its corner at the top, as narrow as it needs to be
    to stay clear of what else is drawn there (its lines wrap).  Only when not even a narrow card
    fits beside it: shorter (gone before that shows / in after it has gone), else moved down below
    it, else in the other corner."""
    info, txt, glow = style.info, style.text, style.glow
    centered = info.position == "top-center"

    title_size = info.size * k
    sub_size = max(18 * k, title_size * 0.56)
    margin = info.margin * k
    bar_w = _BAR * k
    gap = 14 * k
    max_w = W * 0.42
    color = _bgr(info.color or txt.color_unsung)
    accent = _bgr(info.accent or txt.color_sung)
    outline_c = _bgr(txt.outline_color)

    pad = (txt.outline + (glow.size + glow.blur if glow.enabled else 0)) * k + 8 * k
    lowest = H * 0.45  # a card moved down stays in the upper part of the frame
    slide_room = 28 * k  # the lines slide in from beyond the text by this much

    def rows(width: float) -> tuple[list, float, float]:
        """(rows, height, reach) of the card with its lines wrapped to ``width``: each row
        (text, size, bold, width, y from the card's top, level; level 0 = the title).  A line too
        wide wraps (at a space, before a bracket …) instead of being squeezed."""
        placed: list = []
        y = bottom = 0.0
        for i, text in enumerate(lines):
            size = title_size if i == 0 else sub_size
            bold = txt.bold if i == 0 else False
            m = Measurer(family, bold, size)
            for j, row in enumerate(wrap_text(text, m.width, width)):
                if placed:  # below the previous row: a wrapped row closer, the title's rows further
                    prev_size, prev_level = placed[-1][1], placed[-1][5]
                    y += prev_size * (1.1 if j else (1.18 if prev_level == 0 else 1.32))
                placed.append((row, size, bold, m.width(row), y, 0 if i == 0 else 1))
                bottom = y + size
        reach = bar_w + gap + min(width, max(r[3] for r in placed)) + slide_room
        return placed, bottom, reach  # (the accent bar is as tall as the text)

    def region(right: bool, top: float, block_h: float, reach: float) -> tuple[float, float, float, float]:
        """Where the card is drawn (sliding in, outline and glow included)."""
        if centered:
            text_w = max(0.0, reach - bar_w - gap - slide_room)
            extent = text_w / 2 + bar_w + gap + slide_room + pad
            return W / 2 - extent, top - pad, W / 2 + extent, top + block_h + pad
        x0, x1 = (W - margin - reach - pad, W - margin + pad) if right else (margin - pad, margin + reach + pad)
        return x0, top - pad, x1, top + block_h + pad

    def in_the_way(area, a: float, b: float) -> list:
        x0, y0, x1, y1 = area
        return [bx for bx in boxes if bx[2] < x1 and x0 < bx[4] and bx[3] < y1 and y0 < bx[5]
                and bx[0] - 200 < b and a < bx[1] + 200]

    right = info.position == "top-right"
    where = "结尾" if at_end else "开头"

    # 1) in its corner at the top for its whole time, as narrow as needed to end before whatever
    #    else is drawn there (a translation along the top edge): the lines wrap
    min_w = max(title_size * 4, 240 * k)
    width = max_w
    for _ in range(8):
        placed, block_h, reach = rows(width)
        hits = in_the_way(region(right, margin, block_h, reach), t0, t1)
        if not hits:
            top, n0, n1 = margin, t0, t1
            break
        if centered:
            placed = None
            break
        # the room between the corner and the nearest thing in the way
        room = (W - margin - max(bx[4] for bx in hits) if right else min(bx[2] for bx in hits) - margin) \
            - 2 * pad - bar_w - gap - slide_room
        if room < min_w or room >= width - 1:
            placed = None
            break
        width = room
    else:
        placed = None

    if placed is None:
        # 2) nothing narrow enough fits beside it (e.g. a translation across the whole top): the
        #    full-width card, gone before it shows / come in after it has gone; else moved down
        #    below it; else the other corner (same order); else no card
        placed, block_h, reach = rows(max_w)

        def clear(side: bool, top: float) -> tuple[float, float]:
            hits = in_the_way(region(side, top, block_h, reach), t0, t1)
            start, end = t0, t1
            if at_end:  # comes in after the last of them has gone
                moved = True
                while moved:
                    moved = False
                    for bx in hits:
                        if bx[0] - 200 < end and bx[1] + 200 > start:
                            start, moved = bx[1] + 200, True
            else:  # leaves before the first of them shows
                for bx in hits:
                    if bx[1] > start and bx[0] - 200 < end:
                        end = bx[0] - 200
            return start, end

        def place(side: bool, move: bool) -> Optional[tuple[float, float, float]]:
            x0, _, x1, _ = region(side, margin, block_h, reach)
            tops = [margin] + sorted({bx[5] + pad + 6 * k for bx in boxes
                                      if bx[2] < x1 and x0 < bx[4] and bx[1] > t0 and bx[0] < t1
                                      and bx[5] + pad + 6 * k > margin})
            for top in (tops if move else tops[:1]):
                if top + block_h > lowest:
                    break
                a, b = clear(side, top)
                if b - a >= 1000:
                    return top, a, b
            return None

        got = None
        candidates = ((right, False), (right, True)) if centered else (
            (right, False), (right, True), (not right, False), (not right, True))
        for side, move in candidates:
            got = place(side, move)
            if got is not None:
                break
        if got is None:
            if warnings is not None:
                warnings.append(f"{where}的歌词 / 翻译占满了画面顶部，{where}的歌曲信息没有显示"
                                f"（可调整它的{'显示时长' if at_end else '开始时间'}）")
            return []
        if side != right and warnings is not None:
            warnings.append(f"{where}的歌词 / 翻译占满了画面顶部，{where}的歌曲信息改到了另一侧")
        right = side
        top, n0, n1 = got
    t0, t1 = n0, n1
    slide = 28 * k * (1 if right else -1)
    x_text = W / 2 if centered else ((W - margin - bar_w - gap) if right else (margin + bar_w + gap))
    an = 8 if centered else (9 if right else 7)

    # coming in: the bar grows down, then the lines slide in from the edge one after another;
    # leaving is the same played backwards: the lines slide back out (the last one first), then the
    # bar shrinks up.  (An event has one \\move: a line is one event coming in and one going out.)
    events: list[str] = []
    for i, (text, size, bold, width, y, level) in enumerate(placed):
        y += top
        sx = f"\\fscx{max_w / width * 100:.1f}" if width > max_w else ""
        a = t0 + _STAGGER * i  # lines come in one after another
        out_end = t1 - 200 - _STAGGER * i  # and leave in the opposite order, before the bar
        out_start = max(out_end - _OUT_MS, a + _IN_MS)
        font = f"\\an{an}\\fn{family}\\fs{size:.1f}\\b{int(bold)}{sx}"
        body = _escape(text)
        looks = []
        if glow.enabled:
            looks.append((L_INFO_GLOW, f"\\1a&HFF&\\3c{_bgr(glow.color_unsung)}"
                                       f"\\3a&H{int(round(255 * (1 - glow.strength / 100))):02X}&"
                                       f"\\bord{glow.size * k * (0.7 if level == 0 else 0.5):.1f}"
                                       f"\\blur{glow.blur * k:.1f}\\shad0"))
        sub_alpha = "" if level == 0 else "\\1a&H18&"
        looks.append((L_INFO, f"\\1c{color}{sub_alpha}\\3c{outline_c}"
                              f"\\bord{txt.outline * k * (0.7 if level == 0 else 0.55):.2f}"
                              f"\\shad{txt.shadow * k * 0.6:.2f}"))
        move_in = f"\\move({x_text + slide:.1f},{y:.1f},{x_text:.1f},{y:.1f},0,{_IN_MS})"
        for layer, look in looks:
            if out_end - out_start >= 150:
                events.append(_dialogue(layer, a, out_start, f"{font}{move_in}\\fad(350,0){look}", body))
                move_out = f"\\move({x_text:.1f},{y:.1f},{x_text + slide:.1f},{y:.1f},0,{out_end - out_start:.0f})"
                events.append(_dialogue(layer, out_start, out_end,
                                        f"{font}{move_out}\\fad(0,{out_end - out_start:.0f}){look}", body))
            else:  # too short a card for both: in, then a plain fade
                events.append(_dialogue(layer, a, t1, f"{font}{move_in}\\fad(350,300){look}", body))
    bar_x = W / 2 - max(r[3] for r in placed) / 2 - gap - bar_w if centered else (
        (W - margin - bar_w) if right else margin)
    rect = f"m 0 0 l {bar_w:.1f} 0 l {bar_w:.1f} {block_h:.1f} l 0 {block_h:.1f}"
    bar = f"\\an7\\pos({bar_x:.1f},{top:.1f})\\bord0\\shad{txt.shadow * k * 0.4:.2f}\\1c{accent}"
    shape = f"{{\\p1}}{rect}{{\\p0}}"
    shrink = t1 - _BAR_MS
    if shrink >= t0 + _BAR_MS:
        events.append(_dialogue(L_INFO, t0, shrink, f"{bar}\\fscy0\\t(0,{_BAR_MS},0.6,\\fscy100)\\fad(250,0)", shape))
        events.append(_dialogue(L_INFO, shrink, t1, f"{bar}\\t(0,{_BAR_MS},1.6,\\fscy0)\\fad(0,250)", shape))
    else:
        events.append(_dialogue(L_INFO, t0, t1, f"{bar}\\fscy0\\t(0,{_BAR_MS},0.6,\\fscy100)\\fad(250,500)", shape))
    return events


def info_style(family: str, size: float) -> str:
    return (f"Style: KInfo,{family},{size:.1f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,"
            "0,0,7,0,0,0,1")


def _dialogue(layer: int, t0: float, t1: float, tags: str, body: str) -> str:
    from .ass import ass_time

    return f"Dialogue: {layer},{ass_time(t0)},{ass_time(t1)},KInfo,,0,0,0,,{{{tags}}}{body}"


def _bgr(hex_rgb: str) -> str:
    from .ass import bgr_tag

    return bgr_tag(hex_rgb)


def _escape(text: str) -> str:
    from .ass import escape_text

    return escape_text(text)
