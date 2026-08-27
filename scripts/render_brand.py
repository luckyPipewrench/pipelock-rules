#!/usr/bin/env python3
"""Compose every brand asset from one committed mark.

``assets/mark.svg`` is the master: a traced, hand-approved scroll. It is the
only drawing in this repository that is not derived from something else, so it
is committed rather than generated. Everything a reader or a platform sees --
the logo, the wordmark lockup, the favicon, the social card -- is composed from
it here, so a change to the mark reaches every surface at once and none of them
can quietly disagree with the others.

This is deliberately separate from ``render_diagrams.py``. That script exists to
keep drawings honest about live bundle data and reads every value from a
producer. Brand assets track a mark, not a count. Mixing the two would blur what
each gate is actually promising.

``make brand`` writes them; ``make check-brand`` fails when a committed asset no
longer matches, or when the mark stops meeting the brand rules.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "assets"
MARK = ASSET_DIR / "mark.svg"

# Locked brand tokens. Source of truth is the PipeLab brand guidelines and
# pipelab.org/.brand/colors_and_type.css; these must not drift from it.
ACCENT = "#00e5a0"
BG = "#09090b"
BG_ELEVATED = "#0e0e11"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
DIM = "#64748b"
PURPLE = "#7c3aed"

MONO = ("'JetBrains Mono', 'JetBrainsMono Nerd Font', ui-monospace, "
        "SFMono-Regular, Menlo, monospace")
SANS = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# The display name. The repository slug stays `pipelock-rules` and is used
# for URLs, clone commands, and artifact names; it is not a wordmark.
WORDMARK = "Pipelock Rules"
WORDMARK_LEAD = "Pipelock "
WORDMARK_ACCENT = "Rules"
TAGLINE = "Signed, versioned detection rules for Pipelock"

# Family social-card footer. Same string, type, and position as Agent Egress
# Bench, so the two generated cards share one attribution rather than two.
CARD_FOOTER = "Apache 2.0  ·  maintained by PipeLab"
CARD_FOOTER_X = 120
CARD_FOOTER_Y = 566
CARD_FOOTER_SIZE = 16


def _fail(message: str):
    raise SystemExit("render_brand: FAIL - " + message)


def mark_parts() -> tuple:
    """The master mark's viewBox and its inner drawing, read not copied."""
    if not MARK.is_file():
        _fail(f"{MARK.relative_to(REPO_ROOT)} is missing; it is the master and is committed")
    text = MARK.read_text(encoding="utf-8")
    view = re.search(r'viewBox="([^"]+)"', text)
    if not view:
        _fail("mark.svg declares no viewBox")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", text, re.S)
    if not inner or not inner.group(1).strip():
        _fail("mark.svg has no drawing inside its root element")
    return view.group(1), inner.group(1).strip()


def placed_mark(x, y, size, *, fill=None) -> str:
    """The master mark, scaled into a box at (x, y) without distorting it."""
    view, inner = mark_parts()
    vx, vy, vw, vh = (float(v) for v in view.split())
    scale = size / max(vw, vh)
    body = inner if fill is None else re.sub(r'fill="#[0-9a-fA-F]{6}"', f'fill="{fill}"', inner)
    return (f'  <g transform="translate({x:.2f} {y:.2f}) scale({scale:.6f}) '
            f'translate({-vx:.2f} {-vy:.2f})">\n{body}\n  </g>')


def _text(x, y, content, *, fill, size, family=SANS, weight=400,
          anchor="start", spacing=None):
    attrs = [f'x="{x}"', f'y="{y}"', f'font-family="{family}"',
             f'font-size="{size}"', f'fill="{fill}"']
    if weight != 400:
        attrs.append(f'font-weight="{weight}"')
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if spacing:
        attrs.append(f'letter-spacing="{spacing}"')
    return "  <text " + " ".join(attrs) + f">{content}</text>"


def particles(count, w, h, seed=7) -> list:
    """Deterministic particle positions. No randomness, so the file is stable.

    Byte-identical algorithm and seed to the sibling benchmark repository, so
    the two social cards carry the same field rather than two different fields
    that merely look similar. The brand guidelines specify this treatment; see
    section 7, Hero background.
    """
    state = seed
    points = []
    for _ in range(count):
        state = (state * 1103515245 + 12345) % (2 ** 31)
        x = 80 + (state % 1000) / 1000 * (w - 160)
        state = (state * 1103515245 + 12345) % (2 ** 31)
        y = 40 + (state % 1000) / 1000 * (h - 80)
        points.append((round(x, 1), round(y, 1)))
    return points


def particle_field(w, h) -> list:
    """The particle network: dots joined where they are close enough to see."""
    points = particles(44, w, h)
    out = [f'  <g stroke="{ACCENT}" stroke-width="1">']
    for index, (x1, y1) in enumerate(points):
        for x2, y2 in points[index + 1:]:
            distance = math.hypot(x2 - x1, y2 - y1)
            if distance < 150:
                out.append(f'    <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                           f'opacity="{round(0.16 * (1 - distance / 150), 3)}"/>')
    out.append("  </g>")
    out.append(f'  <g fill="{ACCENT}" opacity="0.5">')
    out += [f'    <circle cx="{x}" cy="{y}" r="1.6"/>' for x, y in points]
    out.append("  </g>")
    return out


def _open(w, h, label, *, background=None) -> list:
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" role="img" aria-label="{label}">']
    if background:
        out.append(f'  <rect width="{w}" height="{h}" fill="{background}"/>')
    return out


# --------------------------------------------------------------------- assets

def logo() -> str:
    """The mark alone on a transparent square, with brand clear space.

    Clear space is a tenth of the box on every side, so the mark never butts
    against a heading or a badge row wherever it is dropped in.
    """
    box, pad = 240, 24
    out = _open(box, box, f"{WORDMARK} logo")
    out.append(placed_mark(pad, pad, box - pad * 2))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def favicon() -> str:
    """A square tile for a browser tab.

    On its own the mark is an outline, which disappears against a busy tab bar,
    so the favicon gets the brand's near-black tile behind it. The inner rule
    lines will not resolve at 16px; the scroll silhouette is what has to read,
    and it does.
    """
    box = 64
    out = _open(box, box, f"{WORDMARK} favicon")
    out.append(f'  <rect width="{box}" height="{box}" rx="14" fill="{BG}"/>')
    out.append(placed_mark(11, 11, box - 22))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# Type metrics for the monospace wordmark. Every glyph in a monospace face
# advances 0.6em, so a wordmark's width is exact arithmetic. ASCENDER and
# DESCENDER describe the visual band used to centre it against the mark.
MONO_ADVANCE = 0.6
TRACKING = 0.02
ASCENDER = 0.75
DESCENDER = 0.21


def lockup() -> str:
    """Mark and wordmark on ONE line, for a header or a slide.

    One line rather than stacked: a two-line wordmark beside a single mark
    reads off-balance however it is aligned, which is the exact defect the
    sibling benchmark repository's header had.
    """
    margin, mark_size, gap, size = 20, 96, 24, 46
    text_x = margin + mark_size + gap
    # Monospace: every glyph advances the same width, so the wordmark's extent
    # is arithmetic rather than an estimate. MONO_ADVANCE and TRACKING are named
    # so a font or tracking change moves the canvas with them.
    text_w = round(len(WORDMARK) * size * (MONO_ADVANCE - TRACKING), 2)
    w = round(text_x + text_w + margin, 2)
    h = margin * 2 + mark_size - 24

    # Centre the wordmark's ink on the mark's centre. A baseline sits below the
    # letters, so aligning baselines would hang the word low; this offsets by
    # half the visual band (ascender to descender) instead.
    mark_centre = 10 + mark_size / 2
    baseline = round(mark_centre - (ASCENDER + DESCENDER) * size / 2 + ASCENDER * size, 2)

    out = _open(w, h, f"{WORDMARK} logo lockup")
    out.append(placed_mark(margin, 10, mark_size))
    # Two-tone wordmark. The accent lands on the word that distinguishes
    # this project from its parent, matching 'Agent Egress Bench' next door.
    out.append(f'  <text x="{text_x}" y="{baseline}" font-family="{MONO}" font-size="{size}" '
               f'font-weight="700" letter-spacing="{-TRACKING}em" xml:space="preserve">'
               f'<tspan fill="{TEXT}">{WORDMARK_LEAD}</tspan>'
               f'<tspan fill="{ACCENT}">{WORDMARK_ACCENT}</tspan></text>')
    # No tagline. A lockup is a mark and a wordmark; a page that uses it as a
    # header states the tagline in text directly beneath, and a lockup carrying
    # its own copy made the header say it twice.
    out.append("</svg>")
    return "\n".join(out) + "\n"


def lockup_stacked() -> str:
    """Mark above, wordmark below, for square and centred placements.

    The one-line lockup is the default and belongs anywhere wide: a README
    header, a slide, a card. This one exists for the places a wide lockup
    cannot go -- an avatar, an app icon, a centred hero -- where a horizontal
    lockup has to shrink until the wordmark is unreadable.

    The rule against stacking still holds where it was aimed: it forbids
    breaking the WORDMARK across two lines beside a mark. Here the wordmark
    stays on one line and the mark sits above it, which is the form Pipelock's
    own logo already takes.
    """
    w, h = 420, 252
    out = _open(w, h, f"{WORDMARK} stacked logo")
    out.append(placed_mark((w - 132) / 2, 26, 132))
    out.append(f'  <text x="{w / 2}" y="222" font-family="{MONO}" font-size="42" '
               f'font-weight="700" letter-spacing="-0.02em" text-anchor="middle" '
               f'xml:space="preserve">'
               f'<tspan fill="{TEXT}">{WORDMARK_LEAD}</tspan>'
               f'<tspan fill="{ACCENT}">{WORDMARK_ACCENT}</tspan></text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def social_preview() -> str:
    """The card GitHub renders when someone links the repository.

    1280x640 is GitHub's stated social-preview size. This one is a card by
    nature, so unlike the README marks it carries its own background.
    """
    w, h = 1280, 640
    out = _open(w, h, f"{WORDMARK}: {TAGLINE}")
    # The brand hero treatment, section 7 of the guidelines: teal and purple
    # radials with a particle network over near-black. Same gradient stops and
    # the same field as the sibling benchmark card, so the two read as one
    # family rather than two projects that both happen to be dark.
    out.append(
        '  <defs>'
        '<radialGradient id="teal" cx="30%" cy="20%" r="55%">'
        f'<stop offset="0%" stop-color="{ACCENT}" stop-opacity="0.22"/>'
        f'<stop offset="100%" stop-color="{ACCENT}" stop-opacity="0"/>'
        '</radialGradient>'
        '<radialGradient id="purple" cx="72%" cy="82%" r="55%">'
        f'<stop offset="0%" stop-color="{PURPLE}" stop-opacity="0.30"/>'
        f'<stop offset="100%" stop-color="{PURPLE}" stop-opacity="0"/>'
        '</radialGradient>'
        '</defs>')
    out.append(f'  <rect width="{w}" height="{h}" fill="{BG}"/>')
    out.append(f'  <rect width="{w}" height="{h}" fill="url(#teal)"/>')
    out.append(f'  <rect width="{w}" height="{h}" fill="url(#purple)"/>')
    out += particle_field(w, h)

    # No accent rule across the top. The sibling benchmark card has none, and on
    # a card that bleeds to the edge it reads as a stray browser chrome line
    # rather than as brand.

    out.append(placed_mark(112, 188, 264))

    # Scale, not weight. This and the lockup have always used the same font at
    # 700; the lockup simply gave its wordmark a third of the frame height while
    # the card gave it a tenth, so the lockup read as the bolder of the two. At
    # 86 the name carries the card the way it carries the lockup.
    #
    # Accent lands on the word that distinguishes THIS project, which is the
    # rule the sibling repositories follow: "Agent Egress Bench", "Pipelock Rules".
    out.append(f'  <text x="452" y="300" font-family="{MONO}" font-size="86" '
               f'font-weight="700" letter-spacing="-0.025em" xml:space="preserve">'
               f'<tspan fill="{TEXT}">{WORDMARK_LEAD}</tspan>'
               f'<tspan fill="{ACCENT}">{WORDMARK_ACCENT}</tspan></text>')
    out.append(_text(456, 352, TAGLINE, fill=MUTED, size=25))

    chip_x = 456
    for label in ("dlp", "injection", "tool-poison"):
        width = 34 + len(label) * 15
        out.append(f'  <rect x="{chip_x}" y="398" width="{width}" height="46" rx="23" '
                   f'fill="{ACCENT}" fill-opacity="0.10" stroke="{ACCENT}" '
                   f'stroke-opacity="0.34"/>')
        out.append(_text(chip_x + width / 2, 428, label, fill=ACCENT, size=17,
                         family=MONO, weight=600, anchor="middle"))
        chip_x += width + 16

    out.append(_text(CARD_FOOTER_X, CARD_FOOTER_Y, CARD_FOOTER, fill=DIM,
                     size=CARD_FOOTER_SIZE, family=MONO, spacing="0.12em"))
    out.append("</svg>")
    return "\n".join(out) + "\n"


ASSETS = {
    "pipelock-rules-logo.svg": logo,
    "pipelock-rules-favicon.svg": favicon,
    "pipelock-rules-lockup.svg": lockup,
    "pipelock-rules-lockup-stacked.svg": lockup_stacked,
    "social-preview.svg": social_preview,
}

# Rasters exported from the vectors above by `make brand`.
PNG_EXPORTS = {
    "pipelock-rules-logo-256.png": ("pipelock-rules-logo.svg", 256),
    "social-preview.png": ("social-preview.svg", 1280),
}


def build() -> dict:
    """Every generated brand asset, as a path to its intended content."""
    return {ASSET_DIR / name: render() for name, render in ASSETS.items()}


# A flat mark is built from these and nothing else. Allowing a shape is a
# deliberate act; anything absent from this set is refused, so a construct
# nobody anticipated fails closed instead of passing unnoticed.
MARK_ELEMENTS = {"svg", "g", "path", "circle", "ellipse", "rect", "polygon",
                 "polyline", "line", "title", "desc", "metadata"}

# Attributes that carry paint. A flat mark states a literal colour or none.
PAINT_ATTRS = ("fill", "stroke", "color", "stop-color", "flood-color")


def _mark_policy_problems(inner: str) -> list:
    """Structural check of the master mark: allowed shapes, literal paint only."""
    from xml.etree import ElementTree

    problems = []
    try:
        root = ElementTree.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{inner}</svg>')
    except ElementTree.ParseError as error:
        return [f"mark.svg: does not parse as XML ({error}); it cannot be checked"]

    literal_fills = set()
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in MARK_ELEMENTS:
            problems.append(
                f"mark.svg: uses <{tag}>, which a flat single-colour mark does not need; "
                "add it to MARK_ELEMENTS deliberately if that is wrong")
            continue
        for attr in PAINT_ATTRS:
            value = (node.get(attr) or "").strip()
            if not value or value.lower() in {"none", "currentcolor", "inherit"}:
                continue
            if value.lower().startswith("url("):
                problems.append(
                    f"mark.svg: {attr} references {value}, so its colour comes from a "
                    "gradient, pattern or other paint server rather than the brand accent")
                continue
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                problems.append(f"mark.svg: {attr}={value!r} is not a six-digit hex colour")
                continue
            literal_fills.add(value.lower())
        # A mask or clip reference hides geometry from the paint check above.
        for attr in ("mask", "clip-path", "filter", "style"):
            if node.get(attr):
                problems.append(
                    f"mark.svg: carries {attr}, which can change what is drawn or painted "
                    "without changing any fill this check reads")

    if not literal_fills:
        problems.append("mark.svg: no explicit fill; the colour gate would prove nothing")
    for fill in sorted(literal_fills):
        if fill != ACCENT:
            problems.append(f"mark.svg: paints {fill}, but the mark is single-colour {ACCENT}")
    return problems


def brand_problems() -> list:
    """Report a master mark that no longer follows the brand rules."""
    problems = []
    _, inner = mark_parts()
    problems += _mark_policy_problems(inner)

    text = MARK.read_text(encoding="utf-8")
    if 'width=' in text.split(">", 1)[0]:
        problems.append("mark.svg: pins a width on its root, so it cannot scale into a lockup")
    if "<!DOCTYPE" in text:
        problems.append("mark.svg: still carries a tracer prologue; re-normalise it")

    # Deliberately no "asset is missing" check here. This runs in the WRITE path
    # too, and a rule that the outputs must already exist makes writing them for
    # the first time impossible. Presence is a --check concern.

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # The social card is generated too, but it is a link preview, not a header,
    # so showing it would not put the mark on the front page.
    header_vectors = sorted(set(ASSETS) - {"social-preview.svg"})
    if not any(f"assets/{name}" in readme for name in header_vectors):
        problems.append(
            "README: shows none of " + ", ".join(header_vectors)
            + ", so the mark exists but nobody sees it")

    # A badge for a workflow that was renamed or deleted renders as a broken
    # image on the front page, which reads worse than having no badge.
    workflows = REPO_ROOT / ".github" / "workflows"
    for referenced in sorted(set(re.findall(r"actions/workflows/([\w.-]+\.yaml)", readme))):
        if not (workflows / referenced).is_file():
            problems.append(f"README: badges {referenced}, which is not in .github/workflows/")

    # The family footer is a contract with the sibling card, not decoration.
    card = social_preview()
    if CARD_FOOTER not in card:
        problems.append("social-preview: missing the family footer line")
    if f'x="{CARD_FOOTER_X}"' not in card or f'y="{CARD_FOOTER_Y}"' not in card:
        problems.append(
            f"social-preview: family footer is not at {CARD_FOOTER_X},{CARD_FOOTER_Y}"
        )
    return problems


def sidecar(png: str) -> Path:
    """Where the digest of the SVG a raster was exported from is recorded."""
    return ASSET_DIR / f"{png}.source"


def raster_problems() -> list[str]:
    """Rasters that are missing, or that came from an older vector.

    Existence is not provenance. A PNG left over from a previous mark sits on
    disk looking exactly like a current one, so the check compares the digest
    recorded at export time against the vector as it stands now. Inkscape is
    not always present, which is why export is a separate step and this reads
    the recorded digest rather than re-rasterising to compare.
    """
    problems = []
    for png, (svg, _) in PNG_EXPORTS.items():
        raster = ASSET_DIR / png
        if not raster.exists():
            problems.append(f"assets/{png}: missing; run 'make brand'")
            continue
        note = sidecar(png)
        if not note.exists():
            problems.append(
                f"assets/{png}: no record of the vector it came from; "
                "run 'make brand'")
            continue
        want = hashlib.sha256((ASSET_DIR / svg).read_bytes()).hexdigest()
        if note.read_text(encoding="utf-8").strip() != want:
            problems.append(
                f"assets/{png}: exported from an older assets/{svg}; "
                "re-export it and run 'make brand'")
    return problems


def main() -> int:
    """Write the brand assets, or with --check compare without writing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare committed assets without writing")
    parser.add_argument("--stamp-png", action="store_true",
                        help="record the SVG digest each exported raster was made from")
    args = parser.parse_args()

    if args.stamp_png:
        for png, (svg, _) in PNG_EXPORTS.items():
            digest = hashlib.sha256((ASSET_DIR / svg).read_bytes()).hexdigest()
            sidecar(png).write_text(digest + "\n", encoding="utf-8")
            print(f"stamped assets/{png}.source")
        return 0

    problems = brand_problems()
    files = build()

    if args.check:
        for path, content in sorted(files.items()):
            relative = path.relative_to(REPO_ROOT)
            if not path.exists():
                problems.append(f"{relative}: missing; run 'make brand'")
            elif path.read_text(encoding="utf-8") != content:
                problems.append(f"{relative}: stale; run 'make brand'")
        problems += raster_problems()
        if problems:
            print("check-brand: FAIL", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"check-brand: OK ({len(files)} vectors and {len(PNG_EXPORTS)} rasters)")
        return 0

    if problems:
        print("render_brand: FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    for path, content in sorted(files.items()):
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
