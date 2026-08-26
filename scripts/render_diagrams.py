#!/usr/bin/env python3
"""Render every README asset from one source, on the PipeLab design system.

The README embeds each diagram twice, through a ``<picture>`` element that
picks a variant from the reader's color scheme. Two hand-maintained copies of
one drawing drift the moment either is edited, and a drifted pair is invisible
in review because each file is individually well-formed. So geometry, copy and
counts live here once, the palette is the only thing that varies, and
``make check-diagrams`` fails when a committed asset no longer matches what
this script produces from the live bundles.

Every number and name painted into a diagram is read from a producer: the
compiled bundles under ``published/``, the rule sources under ``rules/``, the
fixtures that gate them, the pinned signing key, and the Pipelock version CI
actually installs. Nothing here restates a fact that lives somewhere else,
because a restated fact is one that can rot without anything noticing.

There are no brand marks here on purpose. The logomark and social card are
a designer's job; this file owns the drawings that have to track the data.

Run ``scripts/render_diagrams.py`` to write the files, or ``--check`` to
compare without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "assets"
PUBLISHED_DIR = REPO_ROOT / "published"
RULES_DIR = REPO_ROOT / "rules"
FIXTURE_DIR = REPO_ROOT / "fixtures"
README = REPO_ROOT / "README.md"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yaml"
OFFICIAL_PUBKEY = REPO_ROOT / ".github" / "rules-official" / "pipelock-official.pub"
CATALOG = REPO_ROOT / "docs" / "rule-catalog.md"

# The bundle make and the docs treat as the default when none is named.
DEFAULT_BUNDLE = "pipelock-community"


def discover_bundles() -> tuple:
    """Every published bundle, found on disk rather than listed here.

    A hardcoded pair is the same defect as a hardcoded rule count: it reads as
    a fact and is really a snapshot, and it quietly tells a reader the
    repository will only ever hold two. A third bundle now gets a catalog
    section and a coverage panel with nobody remembering to edit this file, and
    ``verify_against_corpus`` names the other places that must learn about it.
    """
    if not PUBLISHED_DIR.is_dir():
        _fail("published/ does not exist; there is nothing to describe")
    found = sorted(path.name for path in PUBLISHED_DIR.iterdir()
                   if (path / "bundle.yaml").is_file())
    if not found:
        _fail("published/ contains no compiled bundle")
    lead = [name for name in found if name == DEFAULT_BUNDLE]
    return tuple(lead + [name for name in found if name != DEFAULT_BUNDLE])


BUNDLES = discover_bundles()

# Rule types, in the order compile.sh concatenates them.
RULE_TYPES = ("dlp", "injection", "tool-poison")

# Brand font stacks. GitHub renders README images without web fonts, so the
# fallbacks matter; the PNG exports are made on a host with the brand fonts.
MONO = "'JetBrains Mono', 'JetBrainsMono Nerd Font', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, monospace"
SANS = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Locked brand tokens (pipelab.org/.brand/colors_and_type.css).
BRAND = {
    "accent": "#00e5a0",
    "purple": "#7c3aed",
    "bg": "#09090b",
    "bg_elevated": "#0e0e11",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "dim": "#64748b",
    "warn": "#f59e0b",
    "danger": "#ef4444",
    "info": "#38bdf8",
}

# Contrast adaptations for text and status marks on GitHub's white canvas.
# Filled bars keep the locked accent, with dark token text on top.
LIGHT_THEME_DERIVATIVES = {"#008f66", "#dc2626", "#b45309", "#0284c7"}

# White is not a paint color here. The brand defines translucent surfaces as
# rgba(255,255,255,...) card and border tokens, and _paint splits those into a
# hex base plus an opacity attribute, so the base is what lands in the file.
# Named here so the color gate stays a real check rather than being widened.
OVERLAY_BASES = {"#ffffff"}

# README palettes. Both canvases are transparent so a diagram sits on GitHub's
# own page color instead of arriving as a pasted rectangle.
PALETTES = {
    "dark": {
        "canvas": "none",
        "card": "rgba(255,255,255,0.04)",
        "card_strong": "rgba(255,255,255,0.07)",
        "border": "rgba(255,255,255,0.10)",
        "border_strong": "rgba(255,255,255,0.18)",
        "text": BRAND["text"],
        "muted": BRAND["muted"],
        "dim": BRAND["dim"],
        "accent": BRAND["accent"],
        "accent_text": BRAND["accent"],
        "accent_soft": "rgba(0,229,160,0.12)",
        "accent_border": "rgba(0,229,160,0.35)",
        "danger": BRAND["danger"],
        "danger_soft": "rgba(239,68,68,0.14)",
        "warn": BRAND["warn"],
        "warn_soft": "rgba(245,158,11,0.14)",
        "info": BRAND["info"],
        "info_soft": "rgba(56,189,248,0.14)",
    },
    "light": {
        "canvas": "none",
        "card": "rgba(9,9,11,0.03)",
        "card_strong": "rgba(9,9,11,0.06)",
        "border": "rgba(9,9,11,0.12)",
        "border_strong": "rgba(9,9,11,0.22)",
        "text": BRAND["bg"],
        "muted": BRAND["dim"],
        "dim": "#64748b",
        "accent": BRAND["accent"],
        "accent_text": "#008f66",
        "accent_soft": "rgba(0,229,160,0.16)",
        "accent_border": "rgba(0,143,102,0.45)",
        "danger": "#dc2626",
        "danger_soft": "rgba(220,38,38,0.10)",
        "warn": "#b45309",
        "warn_soft": "rgba(180,83,9,0.12)",
        "info": "#0284c7",
        "info_soft": "rgba(2,132,199,0.12)",
    },
}


# --------------------------------------------------------------------------
# Producers. Everything painted into an asset comes through here.
# --------------------------------------------------------------------------

RULE_START = re.compile(r"^  - id: (\S+)[ \t]*\n", re.M)
SCALAR = re.compile(r"^    (type|status|severity|confidence|name): (.+?)[ \t]*\n", re.M)
HEADER_FIELD = re.compile(r'^(format_version|name|version|author|min_pipelock): "?(.*?)"?[ \t]*\n', re.M)


def _fail(message: str):
    """Abort with a message the operator can act on, not a traceback."""
    raise SystemExit("render_diagrams: FAIL - " + message)


def _published(bundle: str) -> str:
    """The compiled bundle text, or a failure naming the command that writes it."""
    path = PUBLISHED_DIR / bundle / "bundle.yaml"
    if not path.is_file():
        _fail(f"{path.relative_to(REPO_ROOT)} is missing; run 'BUNDLE_NAME={bundle} make compile'")
    return path.read_text(encoding="utf-8")


def bundle_header(bundle: str) -> dict:
    """The compiled bundle's own declared identity and compatibility floor."""
    head = _published(bundle).split("\nrules:", 1)[0] + "\n"
    fields = dict(HEADER_FIELD.findall(head))
    for required in ("format_version", "name", "version", "min_pipelock"):
        if not fields.get(required):
            _fail(f"{bundle}: compiled bundle declares no {required}")
    if fields["name"] != bundle:
        _fail(f"{bundle}: compiled bundle calls itself {fields['name']!r}")
    return fields


def bundle_rules(bundle: str) -> list:
    """Every rule in the compiled bundle, in published order.

    Parsed from the artifact operators actually install rather than from the
    per-rule sources, so a drawing describes what shipped. ``source_rule_ids``
    then checks the two agree, which is what catches an uncompiled edit.
    """
    body = _published(bundle)
    parts = RULE_START.split(body)[1:]
    rules = []
    for identifier, block in zip(parts[0::2], parts[1::2]):
        fields = dict(SCALAR.findall(block))
        for required in ("type", "status", "severity"):
            if required not in fields:
                _fail(f"{bundle}: rule {identifier!r} declares no {required}")
        if fields["type"] not in RULE_TYPES:
            _fail(f"{bundle}: rule {identifier!r} has unknown type {fields['type']!r}")
        rules.append(dict(fields, id=identifier, block=block))
    if not rules:
        _fail(f"{bundle}: compiled bundle contains no rules")
    if len({rule["id"] for rule in rules}) != len(rules):
        _fail(f"{bundle}: compiled bundle repeats a rule id")
    return rules


def source_rule_ids(bundle: str) -> set:
    """Rule ids declared under rules/, which compile.sh merges into the bundle."""
    root = RULES_DIR / bundle
    if not root.is_dir():
        _fail(f"{bundle}: no rule sources at {root.relative_to(REPO_ROOT)}")
    found = set()
    for path in sorted(root.rglob("*.yaml")):
        found |= set(RULE_START.findall(path.read_text(encoding="utf-8") + "\n"))
    if not found:
        _fail(f"{bundle}: no rule ids found under {root.relative_to(REPO_ROOT)}")
    return found


def _assertion_lines(path: Path) -> int:
    """Non-empty lines in a fixture file. Every one of them is a test."""
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def fixture_lines(bundle: str, rule: dict, polarity: str) -> int:
    """Non-empty assertion lines in one fixture file; every line is tested."""
    return _assertion_lines(FIXTURE_DIR / bundle / rule["type"] / f"{rule['id']}-{polarity}.txt")


def total_fixture_lines() -> int:
    """Every fixture assertion in the repository, across both bundles."""
    total = sum(_assertion_lines(path) for path in sorted(FIXTURE_DIR.rglob("*.txt")))
    if not total:
        _fail("no fixture assertions found under fixtures/")
    return total


def ci_pipelock_version() -> str:
    """The Pipelock release CI installs to validate the bundles.

    Read from the workflow rather than from a constant, so the README badge
    cannot keep claiming a version the gate stopped using.
    """
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    declared = set(re.findall(r"[ \t]PIPELOCK_VERSION[=:][ \t]*\"?([0-9]+\.[0-9]+\.[0-9]+)", text))
    if not declared:
        _fail("ci.yaml declares no PIPELOCK_VERSION")
    if len(declared) != 1:
        _fail("ci.yaml installs more than one Pipelock version: " + repr(sorted(declared)))
    return declared.pop()


def ci_compatibility_floors() -> dict:
    """Per-bundle floor the compatibility job actually installs and tests."""
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    floors = dict(re.findall(r"- bundle: (\S+)\n[ \t]+version: (\S+)", text))
    if not floors:
        _fail("ci.yaml declares no compatibility-floor matrix")
    return floors


def official_key_digest() -> str:
    """SHA-256 of the pinned official public key, computed from the key itself."""
    if not OFFICIAL_PUBKEY.is_file():
        _fail(f"{OFFICIAL_PUBKEY.relative_to(REPO_ROOT)} is missing")
    return hashlib.sha256(OFFICIAL_PUBKEY.read_bytes()).hexdigest()


def readme_key_digest():
    """The key digest the README tells a reader to check, if it states one."""
    found = set(re.findall(r"\b([0-9a-f]{64})\b", README.read_text(encoding="utf-8")))
    if len(found) != 1:
        # Zero means the verify step lost its pin; more than one means a reader
        # cannot tell which digest belongs to the key, so neither is a pin.
        return None
    return found.pop()


def readme_badge_version():
    """The Pipelock version the README badge advertises, if it states one."""
    match = re.search(r"tested_with_Pipelock-v([0-9]+\.[0-9]+\.[0-9]+)-", README.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def makefile_preflight_bundles() -> set:
    """Bundles the local preflight target actually loops over."""
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^PREFLIGHT_BUNDLES\s*:?=\s*(.+)$", text, re.M)
    if not match:
        _fail("the Makefile declares no PREFLIGHT_BUNDLES")
    return set(match.group(1).split())


def signed_bundles() -> set:
    """Bundles that ship a detached signature next to the compiled file."""
    return {name for name in BUNDLES if (PUBLISHED_DIR / name / "bundle.yaml.sig").is_file()}


# --------------------------------------------------------------------------
# SVG primitives.
# --------------------------------------------------------------------------

_RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)")


def _n(value) -> str:
    """Format a coordinate: integers bare, everything else to two decimals.

    Binary floating point turns a card width of 209.6 into a coordinate
    printed as ``948.4000000000001``. Sixteen digits in a row inside a path is
    not just untidy: this repository scans its own diff with Pipelock, and that
    run matched the Credit Card Number pattern, so the drawing blocked its own
    pull request. Rounding here removes the noise at its source, and the tests
    hold path data to integers so it cannot come back.
    """
    if isinstance(value, str):
        return value
    rounded = round(float(value), 2)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"


def _paint(attribute: str, value: str) -> str:
    """Emit a paint as hex plus a separate opacity attribute.

    An SVG 1.1 presentation attribute takes a CSS2 ``<color>``, which has no
    ``rgba()``. Browsers parse it anyway, so a README image looks right on
    GitHub while every non-browser renderer paints it black. Hex plus
    ``-opacity`` is the portable spelling of the same color.
    """
    match = _RGBA.fullmatch(value.strip())
    if not match:
        return f'{attribute}="{value}"'
    red, green, blue, alpha = match.groups()
    hexed = "#%02x%02x%02x" % (int(red), int(green), int(blue))
    return f'{attribute}="{hexed}" {attribute}-opacity="{alpha}"'


def _esc(text: str) -> str:
    """Escape text for an SVG text node."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _text(x, y, content, *, fill, size=13, family=SANS, weight=400, anchor="start",
          spacing=None, opacity=None, upper=False):
    if upper:
        content = content.upper()
    attrs = [f'x="{_n(x)}"', f'y="{_n(y)}"', f'font-family="{family}"',
             f'font-size="{_n(size)}"', f'fill="{fill}"']
    if weight != 400:
        attrs.append(f'font-weight="{weight}"')
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if spacing is not None:
        attrs.append(f'letter-spacing="{spacing}"')
    if opacity is not None:
        attrs.append(f'opacity="{opacity}"')
    return "  <text " + " ".join(attrs) + ">" + _esc(content) + "</text>"


def _eyebrow(x, y, content, *, fill, size=10, anchor="start"):
    """Uppercase mono label with wide tracking: the brand's section eyebrow."""
    return _text(x, y, content, fill=fill, size=size, family=MONO, weight=600,
                 anchor=anchor, spacing="0.15em", upper=True)


def _card(x, y, w, h, *, fill, stroke, width=1, radius=12, dash=None, extra=""):
    """A rounded panel: the base surface every diagram is built on."""
    tail = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'  <rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" rx="{radius}" '
            f'{_paint("fill", fill)} {_paint("stroke", stroke)} '
            f'stroke-width="{_n(width)}"{tail}{extra}/>')


def _bar(x, y, w, h, *, fill, opacity=None, radius=4, extra=""):
    """A solid measure. Opacity is an attribute so non-browser renderers keep it."""
    tail = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'  <rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" rx="{radius}" '
            f'{_paint("fill", fill)}{tail}{extra}/>')


def _outline_bar(x, y, w, h, *, stroke, width=1.4, radius=4, extra=""):
    """An unfilled measure, for the experimental half of a coverage bar."""
    return (f'  <rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" rx="{radius}" '
            f'fill="none" {_paint("stroke", stroke)} stroke-width="{_n(width)}"{extra}/>')


def _line(x1, y1, x2, y2, color, *, width=2, dash=None, cap="butt", opacity=None):
    tail = f' stroke-dasharray="{dash}"' if dash else ""
    if opacity is not None:
        tail += f' opacity="{opacity}"'
    return (f'  <path d="M {_n(x1)} {_n(y1)} L {_n(x2)} {_n(y2)}" {_paint("stroke", color)} '
            f'stroke-width="{_n(width)}" stroke-linecap="{cap}" fill="none"{tail}/>')


def _chevron(x, y, color, size=7):
    """A forward arrowhead drawn as a path.

    Deliberately not an SVG ``<marker>``: sanitizers and several converters
    drop markers, which removes every arrowhead while leaving a well-formed
    file and a green check.
    """
    return (f'  <path d="M {_n(x)} {_n(y - size)} L {_n(x + size)} {_n(y)} '
            f'L {_n(x)} {_n(y + size)}" '
            f'fill="none" {_paint("stroke", color)} stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def _tick(x, y, color, size=5, width=2):
    """A check mark, drawn as a path for the same reason as the chevron."""
    return (f'  <path d="M {_n(x - size)} {_n(y)} L {_n(x - size * 0.2)} {_n(y + size * 0.8)} '
            f'L {_n(x + size)} {_n(y - size * 0.9)}" fill="none" {_paint("stroke", color)} '
            f'stroke-width="{_n(width)}" stroke-linecap="round" stroke-linejoin="round"/>')


def _cross(x, y, color, size=4.5, width=2):
    """An X, drawn as a path for the same reason as the tick."""
    return (f'  <path d="M {_n(x - size)} {_n(y - size)} L {_n(x + size)} {_n(y + size)} '
            f'M {_n(x + size)} {_n(y - size)} L {_n(x - size)} {_n(y + size)}" fill="none" '
            f'{_paint("stroke", color)} stroke-width="{_n(width)}" stroke-linecap="round"/>')


def _svg_open(w, h, label, p):
    """Open an SVG with the accessible label screen readers announce."""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" role="img" aria-label="{_esc(label)}">']
    if p["canvas"] != "none":
        out.append(f'  <rect width="{w}" height="{h}" fill="{p["canvas"]}"/>')
    return out


# --------------------------------------------------------------------------
# Headline numbers. Every tile is read from the bundles, never typed in.
# --------------------------------------------------------------------------


def _all_rules() -> list:
    """Every rule in every published bundle, flattened."""
    return [rule for bundle in BUNDLES for rule in bundle_rules(bundle)]


def stats_strip(p) -> str:
    """The headline tiles under the README intro."""
    rules = _all_rules()
    tiles = [
        (str(len(rules)), "detection rules"),
        (str(len(BUNDLES)), "signed bundles"),
        (str(total_fixture_lines()), "fixture assertions"),
        (str(sum(1 for rule in rules if rule["status"] == "stable")), "stable, cited rules"),
    ]
    w, h = 1200, 128
    out = _svg_open(w, h, "; ".join(f"{value} {label}" for value, label in tiles), p)
    margin, gap = 24, 16
    card_w = (w - margin * 2 - gap * (len(tiles) - 1)) / len(tiles)
    x = margin
    for value, label in tiles:
        out.append(_card(x, 16, card_w, h - 32, fill=p["card"], stroke=p["border"]))
        out.append(_text(x + card_w / 2, 72, value, fill=p["accent_text"], size=40,
                         family=MONO, weight=700, anchor="middle"))
        out.append(_eyebrow(x + card_w / 2, 98, label, fill=p["muted"], anchor="middle"))
        x += card_w + gap
    out.append("</svg>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# The pipeline: what a rule passes through before anyone can install it.
#
# The gate chip under each stage names the CI job that enforces it, read from
# the workflow, so a renamed or deleted job breaks the drawing rather than
# leaving it advertising a check that stopped running.
# --------------------------------------------------------------------------

# stage key -> (eyebrow, title, body lines, CI job that enforces it)
PIPELINE_GATES = {
    "author": None,
    "compile": "Lint YAML",
    "prove": "Test fixtures",
    "validate": "Validate bundle",
    "sign": "Verify published signatures",
}


def pipeline_stages() -> list:
    """Stage copy, with the live numbers and versions filled in.

    Body lines are mono and the cards are narrow, so each line is kept inside
    MONO_LINE_LIMIT characters. Longer copy silently ran past the card edge and
    into the next stage's arrow.
    """
    floors = ci_compatibility_floors()
    floor_list = " · ".join(f"v{floors[bundle]}" for bundle in BUNDLES if bundle in floors)
    return [
        ("author", "1 · author", "One rule, one file", [
            "rules/<type>/rule.yaml",
            "+ lines it must match",
            "+ lines it must not",
        ]),
        ("compile", "2 · compile", "make compile", [
            "published/bundle.yaml",
            "sorted: type, then id",
            "same bytes on rerun",
        ]),
        ("prove", "3 · prove", "make test-fixtures", [
            f"{total_fixture_lines()} assertions run",
            "positives must match",
            "negatives must not",
        ]),
        ("validate", "4 · validate", "make validate", [
            f"schema on v{ci_pipelock_version()}",
            "and on each bundle's",
            f"floor: {floor_list}",
        ]),
        ("sign", "5 · sign & serve", "Sign, then install", [
            "Ed25519 detached sig",
            "rules install <name>",
            "writes bundle.lock",
        ]),
    ]


# Mono glyphs advance at roughly 0.6em, so this is the widest body line a
# pipeline card holds without running past its own edge.
MONO_LINE_LIMIT = 22


def _wrap(text: str, limit: int) -> list:
    """Greedy word wrap, for labels that must stay inside a card."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def pipeline(p) -> str:
    """The five stages a rule passes before an operator can install it."""
    stages = pipeline_stages()
    w, h = 1200, 396
    out = _svg_open(w, h, "How a rule reaches an operator: author, compile, prove, "
                          "validate, then sign and serve", p)
    out.append(_eyebrow(24, 34, "from a pull request to an installed bundle",
                        fill=p["muted"], size=11))

    margin, gap = 24, 26
    count = len(stages)
    card_w = (w - margin * 2 - gap * (count - 1)) / count
    top, card_h = 58, 214
    x = margin
    for index, (key, eyebrow, title, lines) in enumerate(stages):
        last = index == count - 1
        out.append(_card(x, top, card_w, card_h,
                         fill=p["accent_soft"] if last else p["card"],
                         stroke=p["accent_border"] if last else p["border"]))
        out.append(_eyebrow(x + 18, top + 30, eyebrow, fill=p["accent_text"], size=10))
        out.append(_text(x + 18, top + 62, title, fill=p["text"], size=15, weight=600))
        out.append(_line(x + 18, top + 80, x + card_w - 18, top + 80, p["border"], width=1))
        for row, line in enumerate(lines):
            out.append(_text(x + 18, top + 106 + row * 24, line, fill=p["muted"],
                             size=11.5, family=MONO))
        gate = PIPELINE_GATES[key]
        label, ink = (gate, p["accent_text"]) if gate else ("human review", p["dim"])
        wrapped = _wrap(label, 24)
        base = top + card_h - 18 - (len(wrapped) - 1) * 14
        for row, line in enumerate(wrapped):
            out.append(_text(x + 18, base + row * 14, line, fill=ink,
                             size=10.5, family=MONO, weight=600))
        if not last:
            out.append(_chevron(x + card_w + 8, top + card_h / 2, p["dim"], size=7))
        x += card_w + gap

    out.append(_line(24, 316, w - 24, 316, p["border"], width=1))
    out.append(_text(24, 346, "Every gate below the stage runs on every pull request. "
                              "A rule that skips one cannot reach a published bundle.",
                     fill=p["dim"], size=13))
    out.append(_text(24, 370, "Bundles are additive: they extend Pipelock's built-in "
                              "scanners and never override them.",
                     fill=p["dim"], size=13))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Coverage: what each bundle actually contains, by type and by status.
# --------------------------------------------------------------------------


def bundle_matrix(bundle: str) -> dict:
    """Stable and experimental counts per rule type, for one bundle."""
    rules = bundle_rules(bundle)
    return {
        rule_type: {
            status: sum(1 for rule in rules
                        if rule["type"] == rule_type and rule["status"] == status)
            for status in ("stable", "experimental")
        }
        for rule_type in RULE_TYPES
    }


def coverage(p) -> str:
    """One panel per published bundle, laid out two to a row.

    The canvas grows a row at a time, so a third or fourth bundle lands without
    anyone rebalancing the drawing. A fixed two-panel layout would have clipped
    the moment the repository stopped having exactly two.
    """
    matrices = {bundle: bundle_matrix(bundle) for bundle in BUNDLES}
    widest = max(sum(row.values()) for matrix in matrices.values() for row in matrix.values())
    widest = max(widest, 1)

    margin, gap = 24, 24
    per_row = 2
    top, panel_h = 58, 258
    rows = -(-len(BUNDLES) // per_row)
    w = 1200
    panel_w = (w - margin * 2 - gap * (per_row - 1)) / per_row
    legend_y = top + rows * (panel_h + gap) + 48
    h = legend_y + 34

    out = _svg_open(w, h, "Rule coverage by bundle, type and status", p)
    out.append(_eyebrow(24, 34, "what is in each bundle", fill=p["muted"], size=11))

    for index, bundle in enumerate(BUNDLES):
        x = margin + (index % per_row) * (panel_w + gap)
        top = 58 + (index // per_row) * (panel_h + gap)
        header = bundle_header(bundle)
        matrix = matrices[bundle]
        out.append(_card(x, top, panel_w, panel_h, fill=p["card"], stroke=p["border"]))
        out.append(_text(x + 20, top + 34, bundle, fill=p["text"], size=17,
                         family=MONO, weight=700))
        out.append(_text(x + panel_w - 20, top + 34, header["version"], fill=p["accent_text"],
                         size=13, family=MONO, weight=600, anchor="end"))
        out.append(_text(x + 20, top + 56, f"format {header['format_version']}  ·  "
                                           f"needs Pipelock {header['min_pipelock']} or newer",
                         fill=p["dim"], size=11, family=MONO))
        out.append(_line(x + 20, top + 72, x + panel_w - 20, top + 72, p["border"], width=1))

        label_w, count_w = 108, 48
        track_x = x + 20 + label_w
        track_w = panel_w - 40 - label_w - count_w
        for row, rule_type in enumerate(RULE_TYPES):
            y = top + 104 + row * 42
            counts = matrix[rule_type]
            total = counts["stable"] + counts["experimental"]
            out.append(_text(x + 20, y + 5, rule_type, fill=p["muted"], size=13, family=MONO))
            if total:
                stable_w = track_w * counts["stable"] / widest
                exp_w = track_w * counts["experimental"] / widest
                if stable_w:
                    out.append(_bar(track_x, y - 9, stable_w, 20, fill=p["accent"],
                                    extra=f' data-bundle="{bundle}" data-type="{rule_type}"'
                                          f' data-stable="{counts["stable"]}"'))
                if exp_w:
                    out.append(_outline_bar(track_x + stable_w + (3 if stable_w else 0),
                                            y - 9, max(exp_w - 3, 2), 20,
                                            stroke=p["accent_border"]))
                out.append(_text(x + panel_w - 20, y + 5, str(total), fill=p["text"],
                                 size=13, family=MONO, weight=600, anchor="end"))
            else:
                out.append(_line(track_x, y - 1, track_x + 26, y - 1, p["border_strong"], width=1))
                out.append(_text(x + panel_w - 20, y + 5, "0", fill=p["dim"],
                                 size=13, family=MONO, anchor="end"))

        totals = {status: sum(row[status] for row in matrix.values())
                  for status in ("stable", "experimental")}
        out.append(_line(x + 20, top + panel_h - 44, x + panel_w - 20, top + panel_h - 44,
                         p["border"], width=1))
        out.append(_text(x + 20, top + panel_h - 20,
                         f"{sum(totals.values())} rules  ·  {totals['stable']} stable  ·  "
                         f"{totals['experimental']} experimental",
                         fill=p["muted"], size=12, family=MONO))

    out.append(_bar(24, legend_y - 9, 22, 14, fill=p["accent"], radius=3))
    out.append(_text(54, legend_y + 2, "stable  ·  cited, fixtures in both directions, "
                                       "on by default",
                     fill=p["dim"], size=13))
    out.append(_outline_bar(margin + panel_w + gap, legend_y - 9, 22, 14,
                            stroke=p["accent_border"], radius=3))
    out.append(_text(margin + panel_w + gap + 30, legend_y + 2,
                     "experimental  ·  true-positive fixtures only, off unless you opt in",
                     fill=p["dim"], size=13))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Anatomy: one real rule, taken apart.
#
# The regular expression itself is never painted. A committed SVG carrying a
# live detection pattern is scanned by this repository's own Pipelock job, and
# a tool-poisoning pattern reads to that scanner exactly like the attack it
# describes. The drawing shows the pattern's shape instead, computed from the
# same string, which is the part a reader actually needs.
# --------------------------------------------------------------------------

ANATOMY_BUNDLE = "pipelock-community"
ANATOMY_RULE = "tool-poison-concealment"

REGEX_FIELD = re.compile(r"^      regex: '(.*)'[ \t]*\n", re.M)
SCAN_FIELD = re.compile(r"^      scan_field: (\S+)", re.M)
REFERENCE = re.compile(r"^      - \"(https?://[^\"]+)\"", re.M)
# RE2 rejects these outright, which is the constraint every rule is written to.
UNSUPPORTED = {"lookahead": r"\(\?=", "lookbehind": r"\(\?<", "backreference": r"\\[1-9]"}


def anatomy_rule() -> dict:
    """The rule the anatomy drawing dissects, read from the compiled bundle."""
    for rule in bundle_rules(ANATOMY_BUNDLE):
        if rule["id"] == ANATOMY_RULE:
            return rule
    _fail(f"anatomy: {ANATOMY_RULE!r} is no longer in {ANATOMY_BUNDLE}; "
          "point ANATOMY_RULE at a live stable rule")


def regex_of(rule: dict) -> str:
    """The rule's pattern text. Read for measurement only, never painted."""
    match = REGEX_FIELD.search(rule["block"])
    if not match:
        _fail(f"anatomy: rule {rule['id']!r} declares no single-quoted regex")
    return match.group(1)


def regex_shape(rule: dict) -> list:
    """Describe a pattern without reprinting it.

    Every value is derived from the live regex, so the drawing cannot claim a
    shape the rule stopped having.
    """
    pattern = regex_of(rule)
    bounded = re.findall(r"\{\d+,\d+\}", pattern)
    shape = [
        ("characters", str(len(pattern))),
        ("alternatives", str(pattern.count("|") + 1)),
        ("non-capturing groups", str(pattern.count("(?:"))),
        ("bounded quantifier", bounded[0] if bounded else "none"),
    ]
    for name, probe in sorted(UNSUPPORTED.items()):
        if re.search(probe, pattern):
            _fail(f"anatomy: rule {rule['id']!r} uses a {name}, which RE2 rejects")
    return shape


def anatomy(p) -> str:
    """One real rule taken apart: declaration, pattern shape, fixtures."""
    rule = anatomy_rule()
    w, h = 1200, 412
    out = _svg_open(w, h, f"Anatomy of the {rule['id']} rule: its declaration, the shape of "
                          "its pattern, and the fixtures that hold it to it", p)
    out.append(_eyebrow(24, 34, "one rule, taken apart", fill=p["muted"], size=11))

    margin, gap = 24, 20
    top, card_h = 58, 248
    left_w = 430
    scan = SCAN_FIELD.search(rule["block"])
    out.append(_card(margin, top, left_w, card_h, fill=p["card"], stroke=p["border"]))
    out.append(_text(margin + 20, top + 34, rule["id"], fill=p["accent_text"], size=16,
                     family=MONO, weight=700))
    out.append(_text(margin + 20, top + 58, rule.get("name", "").strip('"'),
                     fill=p["text"], size=14))
    out.append(_line(margin + 20, top + 76, margin + left_w - 20, top + 76, p["border"], width=1))
    declared = [
        ("type", rule["type"]),
        ("status", rule["status"]),
        ("severity", rule["severity"]),
        ("confidence", rule.get("confidence", "unset")),
        ("scans", scan.group(1) if scan else "the whole payload"),
    ]
    # Five rows here against the shape card's four, so they are pitched tighter
    # to clear the footer rule rather than running underneath it.
    for row, (key, value) in enumerate(declared):
        y = top + 100 + row * 22
        out.append(_text(margin + 20, y, key, fill=p["dim"], size=12, family=MONO))
        out.append(_text(margin + 160, y, value, fill=p["text"], size=12,
                         family=MONO, weight=600))
    reference = REFERENCE.search(rule["block"])
    if reference:
        host = reference.group(1).split("/")[2]
        out.append(_line(margin + 20, top + card_h - 46, margin + left_w - 20,
                         top + card_h - 46, p["border"], width=1))
        out.append(_tick(margin + 26, top + card_h - 26, p["accent_text"], size=5))
        out.append(_text(margin + 40, top + card_h - 22, f"primary source: {host}",
                         fill=p["accent_text"], size=11, family=MONO, weight=600))

    mid_x = margin + left_w + gap
    mid_w = 352
    out.append(_card(mid_x, top, mid_w, card_h, fill=p["card"], stroke=p["border"]))
    out.append(_eyebrow(mid_x + 20, top + 30, "pattern shape", fill=p["muted"]))
    out.append(_text(mid_x + 20, top + 58, "The pattern itself is not printed here.",
                     fill=p["dim"], size=12))
    out.append(_line(mid_x + 20, top + 76, mid_x + mid_w - 20, top + 76, p["border"], width=1))
    for row, (key, value) in enumerate(regex_shape(rule)):
        y = top + 104 + row * 24
        out.append(_text(mid_x + 20, y, key, fill=p["dim"], size=12, family=MONO))
        out.append(_text(mid_x + mid_w - 20, y, value, fill=p["text"], size=12,
                         family=MONO, weight=600, anchor="end"))
    out.append(_line(mid_x + 20, top + card_h - 46, mid_x + mid_w - 20, top + card_h - 46,
                     p["border"], width=1))
    out.append(_tick(mid_x + 26, top + card_h - 26, p["accent_text"], size=5))
    out.append(_text(mid_x + 40, top + card_h - 22, "RE2: no lookaround, no backrefs",
                     fill=p["accent_text"], size=11, family=MONO, weight=600))

    right_x = mid_x + mid_w + gap
    right_w = w - margin - right_x
    panel_h = (card_h - gap) / 2
    panels = [
        ("true-positive lines", "must all match", p["accent_text"], p["accent_soft"],
         p["accent_border"], True),
        ("false-positive lines", "must never match", p["danger"], p["danger_soft"],
         p["danger"], False),
    ]
    y = top
    for label, rule_text, ink, fill, stroke, positive in panels:
        polarity = "true-positive" if positive else "false-positive"
        count = fixture_lines(ANATOMY_BUNDLE, rule, polarity)
        out.append(_card(right_x, y, right_w, panel_h, fill=fill, stroke=stroke))
        if positive:
            out.append(_tick(right_x + 28, y + 42, ink, size=9, width=2.6))
        else:
            out.append(_cross(right_x + 28, y + 42, ink, size=8, width=2.6))
        out.append(_text(right_x + 54, y + 52, str(count), fill=ink, size=32,
                         family=MONO, weight=700))
        out.append(_text(right_x + 20, y + 84, label, fill=p["text"], size=13, weight=600))
        out.append(_text(right_x + 20, y + 104, rule_text, fill=p["muted"], size=11,
                         family=MONO))
        y += panel_h + gap

    out.append(_line(24, 342, w - 24, 342, p["border"], width=1))
    out.append(_text(24, 372, "A stable rule carries a primary source, fixtures that must "
                              "match, and fixtures that must not. An experimental rule has "
                              "only the first kind, so it stays off until you ask for it.",
                     fill=p["dim"], size=13))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Trust: who signed a bundle, and what an operator checks before loading it.
# --------------------------------------------------------------------------


def trust(p) -> str:
    """Sign, verify against the pinned key, pin again at install."""
    w, h = 1200, 328
    digest = official_key_digest()
    out = _svg_open(w, h, "The trust chain: a bundle is signed with Ed25519, verified "
                          "against a pinned public key, and pinned again at install", p)
    out.append(_eyebrow(24, 34, "what an operator checks before loading a bundle",
                        fill=p["muted"], size=11))

    steps = [
        ("bundle.yaml", "the compiled rules", "what you install"),
        ("bundle.yaml.sig", "Ed25519, detached", "signed by the maintainer"),
        ("pipelock verify", "against a pinned key", f"sha256 {digest[:16]}…"),
        ("bundle.lock", "written at install", "provenance, on your disk"),
    ]
    margin, gap = 24, 40
    top, card_h = 62, 128
    card_w = (w - margin * 2 - gap * (len(steps) - 1)) / len(steps)
    x = margin
    for index, (title, subtitle, note) in enumerate(steps):
        last = index == len(steps) - 1
        out.append(_card(x, top, card_w, card_h,
                         fill=p["accent_soft"] if last else p["card"],
                         stroke=p["accent_border"] if last else p["border"]))
        out.append(_text(x + 20, top + 42, title, fill=p["text"], size=16,
                         family=MONO, weight=700))
        out.append(_text(x + 20, top + 68, subtitle, fill=p["accent_text"], size=12,
                         family=MONO))
        out.append(_line(x + 20, top + 86, x + card_w - 20, top + 86, p["border"], width=1))
        out.append(_text(x + 20, top + 112, note, fill=p["muted"], size=12, family=MONO))
        if not last:
            out.append(_chevron(x + card_w + 14, top + card_h / 2, p["dim"], size=7))
        x += card_w + gap

    roots = [
        ("official bundles", "verified against the keyring compiled into the "
                             "Pipelock release binary"),
        ("third-party bundles", "verified against the keys you list in trusted_keys"),
    ]
    y = top + card_h + 34
    root_w = (w - margin * 2 - 20) / 2
    x = margin
    for title, body in roots:
        out.append(_card(x, y, root_w, 66, fill=p["card"], stroke=p["border"]))
        out.append(_eyebrow(x + 20, y + 26, title, fill=p["accent_text"]))
        out.append(_text(x + 20, y + 48, body, fill=p["muted"], size=12))
        x += root_w + 20
    out.append(_text(24, h - 16, "An unsigned bundle installs only when you pass "
                                 "--allow-unsigned, which is for a bundle you are still writing.",
                     fill=p["dim"], size=13))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# The rule catalog.
#
# The README used to list covered providers in a hand-written table, which
# answered the question a reader actually arrives with -- does this cover my
# stack -- and went stale the moment a rule landed. This regenerates the same
# answer from the compiled bundles, so it cannot drift, and check-diagrams
# fails when the committed copy falls behind.
#
# Names, severities and citations only. A rule's pattern never appears here for
# the same reason it never appears in a diagram.
# --------------------------------------------------------------------------

TYPE_TITLES = {
    "dlp": "Credentials and sensitive data",
    "injection": "Prompt injection",
    "tool-poison": "MCP tool poisoning",
}

# Providers the README names as examples of what the community bundle covers.
# Kept short on purpose; the catalog is the complete answer.
README_NAMED_PROVIDERS = ("1Password", "Doppler", "Pulumi", "Shopify", "Vercel")


def _citation_host(rule: dict) -> str:
    match = REFERENCE.search(rule["block"])
    if not match:
        return "-"
    host = match.group(1).split("/")[2]
    return f"[{host}]({match.group(1)})"


def rule_catalog() -> str:
    """The full rule list, as Markdown, generated from the compiled bundles."""
    lines = [
        "# Rule catalog",
        "",
        "Every rule in every published bundle, generated from the compiled bundles by",
        "`scripts/render_diagrams.py`. Do not edit this file by hand: run `make diagrams`.",
        "",
        "Stable rules are enabled by default and carry a primary source plus fixtures in",
        "both directions. Experimental rules carry true-positive fixtures only and stay off",
        "until you set `rules.include_experimental: true`.",
        "",
    ]
    for bundle in BUNDLES:
        header = bundle_header(bundle)
        rules = bundle_rules(bundle)
        lines += [
            f"## {bundle}",
            "",
            f"Version `{header['version']}` · format {header['format_version']} · "
            f"needs Pipelock {header['min_pipelock']} or newer · "
            f"{len(rules)} rules · author {header.get('author', 'unknown')}",
            "",
        ]
        for rule_type in RULE_TYPES:
            selected = [rule for rule in rules if rule["type"] == rule_type]
            if not selected:
                continue
            lines += [
                f"### {TYPE_TITLES[rule_type]} (`{rule_type}`)",
                "",
                "| Rule | Detects | Severity | Status | Source |",
                "|------|---------|----------|--------|--------|",
            ]
            for rule in sorted(selected, key=lambda item: item["id"]):
                name = rule.get("name", rule["id"]).strip('"')
                lines.append(
                    f"| `{rule['id']}` | {name} | {rule['severity']} | "
                    f"{rule['status']} | {_citation_host(rule)} |")
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


# --------------------------------------------------------------------------
# Build, verify, write.
# --------------------------------------------------------------------------

# Rendered once per theme, embedded behind <picture>.
DIAGRAMS = {
    "pipeline": pipeline,
    "coverage": coverage,
    "anatomy": anatomy,
    "trust": trust,
    "stats-strip": stats_strip,
}
CI_JOB_NAME = re.compile(r"^    name: (.+?)[ \t]*\n", re.M)


def ci_check_names() -> set:
    """Display names of the CI jobs, which are what GitHub reports as checks."""
    names = set(CI_JOB_NAME.findall(CI_WORKFLOW.read_text(encoding="utf-8")))
    if not names:
        _fail("ci.yaml declares no named jobs")
    return {re.sub(r"\s*\(\$\{\{.*", "", name).strip() for name in names}


def _strings_of(svg: str) -> list:
    """Text runs of a generated SVG, for gates that check what a drawing says."""
    return [re.sub(r"&[a-z]+;", " ", run)
            for run in re.findall(r"<text[^>]*>([^<]*)</text>", svg)]


def verify_against_corpus() -> list:
    """Report drawings and README claims that no longer match the repository."""
    problems = []

    for bundle in BUNDLES:
        rules = bundle_rules(bundle)
        published_ids = {rule["id"] for rule in rules}
        source_ids = source_rule_ids(bundle)
        for missing in sorted(source_ids - published_ids):
            problems.append(f"{bundle}: rule {missing!r} exists under rules/ but is not in the "
                            f"compiled bundle; run 'BUNDLE_NAME={bundle} make compile'")
        for extra in sorted(published_ids - source_ids):
            problems.append(f"{bundle}: compiled bundle contains {extra!r}, which no rule "
                            "source declares")
        for rule in rules:
            if not fixture_lines(bundle, rule, "true-positive"):
                problems.append(f"{bundle}: rule {rule['id']!r} has no true-positive fixture")
            if rule["status"] == "stable" and not fixture_lines(bundle, rule, "false-positive"):
                problems.append(f"{bundle}: stable rule {rule['id']!r} has no false-positive "
                                "fixture, which the contribution bar requires")

    floors = ci_compatibility_floors()
    for bundle in BUNDLES:
        declared = bundle_header(bundle)["min_pipelock"]
        tested = floors.get(bundle)
        if tested is None:
            problems.append(f"{bundle}: the coverage diagram shows a floor of {declared}, but "
                            "CI's compatibility matrix never tests this bundle")
        elif tested != declared:
            problems.append(f"{bundle}: declares min_pipelock {declared} while CI tests its "
                            f"floor at {tested}; one of the two is wrong")

    # A new bundle is picked up automatically here, so the risk is the opposite
    # one: it lands in the drawings and the catalog while the gates that give
    # those drawings their meaning never learn it exists.
    for bundle in BUNDLES:
        if bundle not in makefile_preflight_bundles():
            problems.append(f"{bundle}: is published but missing from PREFLIGHT_BUNDLES in the "
                            "Makefile, so make preflight never validates or fixture-tests it")

    unsigned = sorted(set(BUNDLES) - signed_bundles())
    for bundle in unsigned:
        problems.append(f"{bundle}: the trust diagram shows a detached signature, but "
                        f"published/{bundle}/bundle.yaml.sig is missing")

    badge = readme_badge_version()
    tested_with = ci_pipelock_version()
    if badge is None:
        problems.append("README: the tested-with badge is gone; the diagrams still name a "
                        "tested Pipelock version")
    elif badge != tested_with:
        problems.append(f"README: the badge advertises Pipelock v{badge} while CI validates "
                        f"with v{tested_with}")

    pinned = readme_key_digest()
    if pinned is None:
        problems.append("README: the verify step no longer pins exactly one key digest")
    elif pinned != official_key_digest():
        problems.append("README: the pinned key digest does not match "
                        ".github/rules-official/pipelock-official.pub")

    checks = ci_check_names()
    for stage, gate in PIPELINE_GATES.items():
        if gate and gate not in checks:
            problems.append(f"pipeline diagram: stage {stage!r} credits the {gate!r} check, "
                            "which ci.yaml no longer reports")

    # The install section used to say "either official bundle", which quietly
    # told a reader the repository would only ever hold two. It now lists them,
    # and this checks the list both ways: a published bundle nobody can find
    # instructions for, and instructions for a bundle that is not published.
    listed = set(re.findall(r"^pipelock rules install ([a-z0-9][a-z0-9-]*)\s*$",
                            README.read_text(encoding="utf-8"), re.M))
    for bundle in BUNDLES:
        if bundle not in listed:
            problems.append(f"{bundle}: is published but the README install section never "
                            "shows how to install it")
    for extra in sorted(listed - set(BUNDLES)):
        problems.append(f"README: tells a reader to install {extra!r}, which is not published")

    link = CATALOG.relative_to(REPO_ROOT).as_posix()
    if link not in README.read_text(encoding="utf-8"):
        problems.append(f"README: does not link {link}, so the generated catalog is unreachable")

    # The README names a few providers as examples. The list is deliberately not
    # exhaustive, because the catalog is, so a new rule does not force a prose
    # edit. It must never name one that is gone, though: that is the direction
    # that misleads a reader deciding whether their stack is covered.
    catalogued = " ".join(rule.get("name", "") for bundle in BUNDLES
                          for rule in bundle_rules(bundle)).lower()
    for provider in README_NAMED_PROVIDERS:
        if provider.lower() not in catalogued:
            problems.append(f"README: names {provider!r} as covered, but no rule detects it")

    rule = anatomy_rule()
    if rule["status"] != "stable":
        problems.append(f"anatomy diagram: {rule['id']!r} is {rule['status']}, so it cannot "
                        "illustrate the stable bar")
    return problems


def build() -> dict:
    """Every generated file, as a path to its full intended content."""
    files = {CATALOG: rule_catalog()}
    for name, render in DIAGRAMS.items():
        for theme, palette in PALETTES.items():
            files[ASSET_DIR / f"diagram-{name}-{theme}.svg"] = render(palette)
    return files


def svg_assets() -> dict:
    """Just the vector assets.

    ``build()`` also produces the Markdown catalog, and the gates that check
    SVG shape -- parses, has a label, fits its canvas, uses brand colors, keeps
    coordinates short -- are meaningless against prose. Splitting here keeps
    those gates pointed at real SVGs rather than being loosened to tolerate a
    document they were never about.
    """
    return {path: content for path, content in build().items()
            if path.suffix == ".svg"}


def main() -> int:
    """Write the assets, or with --check compare them without writing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare committed assets without writing")
    args = parser.parse_args()

    problems = verify_against_corpus()
    files = build()

    if args.check:
        for path, content in sorted(files.items()):
            relative = path.relative_to(REPO_ROOT)
            if not path.exists():
                problems.append(f"{relative}: missing; run scripts/render_diagrams.py")
            elif path.read_text(encoding="utf-8") != content:
                problems.append(f"{relative}: stale; run scripts/render_diagrams.py")
        if problems:
            print("check-diagrams: FAIL", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"check-diagrams: OK ({len(files)} assets match the bundles)")
        return 0

    if problems:
        print("render_diagrams: FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    for path, content in sorted(files.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
