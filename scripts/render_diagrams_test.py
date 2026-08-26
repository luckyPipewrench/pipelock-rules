"""Tests for the README asset generator.

The generator exists to stop failures that are all invisible in review: a light
and dark diagram pair drifting apart, a drawing describing bundles that have
moved on, a count painted into an asset going stale, a README badge naming a
Pipelock version CI stopped using, and a README claim nothing re-checks.
Each is asserted here, including the case where the gate itself would pass
while proving nothing.

The sharpest gate is the last class: a committed SVG carrying a live detection
pattern is scanned by this repository's own Pipelock job, and an injection or
tool-poisoning pattern reads to that scanner exactly like the attack it
describes. No asset may contain any rule's regular expression.
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
import unittest

import yaml

# Every document parsed here is a string this same module just generated from a
# literal template, so the stdlib parser never sees an untrusted document and
# the repository keeps its stdlib-only tooling rule.
import xml.etree.ElementTree as ElementTree
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "render_diagrams.py"

spec = importlib.util.spec_from_file_location("render_diagrams", SCRIPT)
assert spec and spec.loader
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

# The brand generator writes into the same assets/ directory, so the orphan
# check has to ask it what it owns rather than assume anything unclaimed is junk.
BRAND_SCRIPT = SCRIPT.parent / "render_brand.py"
_brand_spec = importlib.util.spec_from_file_location("render_brand", BRAND_SCRIPT)
assert _brand_spec and _brand_spec.loader
brand = importlib.util.module_from_spec(_brand_spec)
_brand_spec.loader.exec_module(brand)

SVG = "{http://www.w3.org/2000/svg}"


def _strings(svg: str) -> list:
    """Every rendered text run, in document order."""
    return [(node.text or "").strip()
            for node in ElementTree.fromstring(svg).iter(SVG + "text")]


def _extents(node) -> list:
    """Bounding boxes for the primitives this generator draws.

    Rects and circles have exact boxes. Paths and text do not without a full
    SVG engine, so they are left out rather than approximated: a wrong box
    would either fire falsely or hide a real overrun.
    """
    tag = node.tag.rsplit("}", 1)[-1]
    if node.get("data-role") == "bleed":
        # A decorative wash that is meant to run off the edge. Content shapes
        # carry no such tag, so the gate still catches a real overrun.
        return []
    try:
        if tag == "rect":
            x, y = float(node.get("x", 0)), float(node.get("y", 0))
            return [(x, y, x + float(node.get("width", 0)), y + float(node.get("height", 0)))]
        if tag == "circle":
            cx, cy, r = float(node.get("cx", 0)), float(node.get("cy", 0)), float(node.get("r", 0))
            return [(cx - r, cy - r, cx + r, cy + r)]
        if tag == "ellipse":
            cx, cy = float(node.get("cx", 0)), float(node.get("cy", 0))
            rx, ry = float(node.get("rx", 0)), float(node.get("ry", 0))
            return [(cx - rx, cy - ry, cx + rx, cy + ry)]
    except (TypeError, ValueError):
        return []
    return []


GEOMETRY_ATTRS = ("x", "y", "width", "height", "cx", "cy", "r", "rx", "ry",
                  "x1", "y1", "x2", "y2", "d", "points", "transform", "text-anchor")


def _geometry(root) -> list:
    """Tag plus every position-bearing attribute, ignoring color and opacity.

    Comparing tag sequences alone would let a light and dark pair differ in
    every coordinate while the parity gate passed.
    """
    return [
        (node.tag, tuple((a, node.get(a)) for a in GEOMETRY_ATTRS if node.get(a) is not None))
        for node in root.iter()
    ]


class _swap:
    """Temporarily replace a generator attribute; restores on exit."""

    def __init__(self, attribute, value):
        self.attribute, self.value = attribute, value

    def __enter__(self):
        self.saved = getattr(generator, self.attribute)
        setattr(generator, self.attribute, self.value)

    def __exit__(self, *_):
        setattr(generator, self.attribute, self.saved)


class WellFormedTest(unittest.TestCase):
    def test_every_generated_asset_parses(self):
        for path, content in generator.svg_assets().items():
            with self.subTest(asset=path.name):
                ElementTree.fromstring(content)

    def test_every_asset_declares_an_accessible_label(self):
        for path, content in generator.svg_assets().items():
            with self.subTest(asset=path.name):
                root = ElementTree.fromstring(content)
                self.assertEqual(root.get("role"), "img")
                self.assertTrue((root.get("aria-label") or "").strip())

    def test_no_asset_depends_on_an_svg_marker(self):
        # Arrowheads and ticks are drawn as paths. Some renderers and
        # sanitizers drop <marker>, which removes every arrowhead while leaving
        # a well-formed file and a green check.
        for path, content in generator.svg_assets().items():
            with self.subTest(asset=path.name):
                self.assertNotIn("<marker", content)
                self.assertNotIn("marker-end", content)

    def test_no_asset_uses_rgba_notation(self):
        # An SVG 1.1 presentation attribute takes a CSS2 <color>, which has no
        # rgba(). Browsers accept it, so GitHub looks right while Inkscape and
        # other converters paint the translucent cards solid black.
        for path, content in generator.svg_assets().items():
            with self.subTest(asset=path.name):
                self.assertNotIn("rgba(", content)

    def test_every_asset_fits_its_own_canvas(self):
        # A shape past the right edge is clipped silently by the viewBox.
        for path, content in generator.svg_assets().items():
            with self.subTest(asset=path.name):
                root = ElementTree.fromstring(content)
                _, _, width, height = (float(v) for v in root.get("viewBox").split())
                for node in root.iter():
                    for x0, y0, x1, y1 in _extents(node):
                        self.assertGreaterEqual(x0, -0.5, f"{path.name}: left of the canvas")
                        self.assertGreaterEqual(y0, -0.5, f"{path.name}: above the canvas")
                        self.assertLessEqual(x1, width + 0.5, f"{path.name}: overruns the right edge")
                        self.assertLessEqual(y1, height + 0.5, f"{path.name}: overruns the bottom edge")

    def test_every_explicit_asset_color_is_a_brand_token_or_light_adaptation(self):
        approved = (set(generator.BRAND.values()) | generator.LIGHT_THEME_DERIVATIVES
                    | generator.OVERLAY_BASES)
        for path, content in generator.svg_assets().items():
            with self.subTest(asset=path.name):
                colors = set(re.findall(r"#[0-9a-f]{6}\b", content.lower()))
                # Without this the regex could match nothing and the subset
                # check below would pass while proving nothing, which is how
                # the same gate shipped vacuous on a sibling repository.
                self.assertTrue(colors, f"{path.name}: the color scan matched nothing")
                self.assertTrue(colors <= approved, colors - approved)


def _regex_values(node) -> list:
    """Every string under a key named regex, at any depth."""
    if isinstance(node, dict):
        found = []
        for key, value in node.items():
            if key == "regex" and isinstance(value, str):
                found.append(value)
            else:
                found += _regex_values(value)
        return found
    if isinstance(node, list):
        return [value for item in node for value in _regex_values(item)]
    return []


class PatternSecrecyTest(unittest.TestCase):
    """No asset may carry a live detection pattern.

    This repository scans its own diff with Pipelock on every pull request. An
    injection or tool-poisoning regex committed inside an SVG is, to that
    scanner, the attack string it was written to catch, so the asset would
    block its own pull request. The anatomy drawing therefore describes the
    shape of a pattern and never prints one.
    """

    def _every_regex(self) -> list:
        """Every rule pattern in the corpus, read with a YAML parser.

        The previous version searched the source text for `regex: \'...\'` at a
        fixed indent. That matches how every rule happens to be written today,
        which is exactly why it was risky: a double-quoted or block-scalar
        pattern would be skipped silently and the check would go partial without
        reporting anything. Parsing sees a pattern however it is quoted.
        """
        found = []
        for bundle in generator.BUNDLES:
            document = yaml.safe_load(
                (generator.PUBLISHED_DIR / bundle / "bundle.yaml").read_text(encoding="utf-8"))
            for rule in document.get("rules") or []:
                # Walk the rule rather than reaching for a known key. The regex
                # sits at rules[].pattern.regex, and the first version of this
                # rewrite assumed rules[].regex and collected nothing. A gate
                # that silently finds nothing is the failure mode being guarded
                # against, so it takes every regex field wherever it is nested.
                found += [(rule.get("id", "<unidentified>"), value)
                          for value in _regex_values(rule)]
        return found

    def _every_committed_surface(self) -> dict:
        """Everything both generators write, as text and as rendered text.

        Two reasons this is wider than it looks. The brand vectors live in the
        same repository and are read by the same scan, so leaving them out meant
        the gate covered some of what it was protecting. And an SVG stores `<`
        as `&lt;`, so a pattern can be absent from the raw bytes and present in
        what a parser hands back: both views are checked.
        """
        surfaces = {}
        for path, content in list(generator.build().items()) + list(brand.build().items()):
            surfaces[path.name] = content
            if path.suffix == ".svg":
                try:
                    root = ElementTree.fromstring(content)
                except ElementTree.ParseError:
                    continue
                surfaces[f"{path.name} (decoded text)"] = "".join(root.itertext())
        return surfaces

    def test_the_scan_finds_patterns_to_check(self):
        # Otherwise every assertion below is vacuously true.
        self.assertGreaterEqual(len(self._every_regex()), 50)

    def test_no_generated_asset_contains_any_rule_pattern(self):
        surfaces = self._every_committed_surface()
        self.assertTrue(surfaces, "no surfaces collected; the check would prove nothing")
        for identifier, pattern in self._every_regex():
            for name, content in surfaces.items():
                with self.subTest(rule=identifier, asset=name):
                    self.assertNotIn(pattern, content)

    def test_no_asset_emits_a_long_run_of_digits(self):
        # Binary floating point printed a card width of 209.6 as the coordinate
        # 948.4000000000001. Sixteen digits in a row inside a path matched this
        # repository's own Credit Card Number DLP rule, so the diagram failed
        # the Pipelock scan on its own pull request. Coordinates are rounded at
        # the source; this holds the whole asset to it.
        seen = 0
        for path, content in generator.svg_assets().items():
            for token in re.findall(r"-?\d+\.\d+", content):
                seen += 1
                with self.subTest(asset=path.name, token=token):
                    self.assertLessEqual(len(token.split(".")[1]), 2,
                                         f"{path.name}: {token} carries float noise")
            for data in re.findall(r'd="([^"]*)"', content):
                with self.subTest(asset=path.name, check="digit run"):
                    self.assertNotRegex(data, r"\d{7,}")
        # Otherwise a generator that emitted no decimals at all would pass this
        # while proving nothing about rounding.
        self.assertGreater(seen, 0, "the precision scan matched no decimals")

    def test_the_anatomy_drawing_describes_the_pattern_it_hides(self):
        rule = generator.anatomy_rule()
        pattern = generator.regex_of(rule)
        drawing = generator.anatomy(generator.PALETTES["dark"])
        self.assertNotIn(pattern, drawing)
        text = " ".join(_strings(drawing))
        # Each value is derived from the live regex, so the description cannot
        # drift away from the rule it claims to describe.
        self.assertIn(str(len(pattern)), text)
        self.assertIn(str(pattern.count("|") + 1), text)
        self.assertIn(str(pattern.count("(?:")), text)

    def test_a_rule_using_a_construct_re2_rejects_is_reported(self):
        rule = dict(generator.anatomy_rule())
        rule["block"] = "      regex: '(?=lookahead)'\n"
        with self.assertRaises(SystemExit):
            generator.regex_shape(rule)


class ThemeParityTest(unittest.TestCase):
    """A pair that says different things is the failure the generator prevents."""

    def test_light_and_dark_carry_identical_copy(self):
        for name, render in generator.DIAGRAMS.items():
            with self.subTest(diagram=name):
                self.assertEqual(_strings(render(generator.PALETTES["light"])),
                                 _strings(render(generator.PALETTES["dark"])))

    def test_light_and_dark_carry_identical_geometry(self):
        for name, render in generator.DIAGRAMS.items():
            with self.subTest(diagram=name):
                light = ElementTree.fromstring(render(generator.PALETTES["light"]))
                dark = ElementTree.fromstring(render(generator.PALETTES["dark"]))
                self.assertEqual(_geometry(light), _geometry(dark))

    def test_the_two_palettes_actually_differ(self):
        light, dark = generator.PALETTES["light"], generator.PALETTES["dark"]
        self.assertEqual(set(light), set(dark))
        self.assertNotEqual(light["text"], dark["text"])
        self.assertNotEqual(light["accent_text"], dark["accent_text"])

    def test_readme_diagrams_are_transparent(self):
        # A painted canvas reads as a pasted rectangle on the other theme.
        for theme in generator.PALETTES.values():
            self.assertEqual(theme["canvas"], "none")


class BundleAgreementTest(unittest.TestCase):
    """Each gate is asserted twice: it passes now, and it fires when broken."""

    def test_the_committed_assets_match_the_live_bundles(self):
        self.assertEqual(generator.verify_against_corpus(), [])

    def test_a_rule_that_was_never_compiled_is_reported(self):
        real = generator.source_rule_ids
        with _swap("source_rule_ids", lambda b: real(b) | {"dlp-not-yet-compiled"}):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("dlp-not-yet-compiled" in p for p in problems), problems)

    def test_a_rule_with_no_true_positive_fixture_is_reported(self):
        with _swap("fixture_lines", lambda bundle, rule, polarity: 0):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("no true-positive fixture" in p for p in problems), problems)

    def test_a_stable_rule_with_no_false_positive_fixture_is_reported(self):
        real = generator.fixture_lines

        def only_true(bundle, rule, polarity):
            return 0 if polarity == "false-positive" else real(bundle, rule, polarity)

        with _swap("fixture_lines", only_true):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("no false-positive" in p for p in problems), problems)

    def test_a_bundle_ci_stopped_testing_at_its_floor_is_reported(self):
        with _swap("ci_compatibility_floors", dict):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("never tests this bundle" in p for p in problems), problems)

    def test_a_floor_that_disagrees_with_the_bundle_is_reported(self):
        floors = dict(generator.ci_compatibility_floors())
        floors[generator.BUNDLES[0]] = "9.9.9"
        with _swap("ci_compatibility_floors", lambda: floors):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("one of the two is wrong" in p for p in problems), problems)

    def test_a_badge_naming_the_wrong_pipelock_version_is_reported(self):
        with _swap("readme_badge_version", lambda: "0.0.1"):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("badge advertises" in p for p in problems), problems)

    def test_a_readme_that_lost_its_badge_is_reported(self):
        with _swap("readme_badge_version", lambda: None):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("tested-with badge is gone" in p for p in problems), problems)

    def test_a_pinned_key_digest_that_does_not_match_the_key_is_reported(self):
        with _swap("readme_key_digest", lambda: "0" * 64):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("pinned key digest" in p for p in problems), problems)

    def test_a_readme_that_pins_two_digests_pins_neither(self):
        """Two digests leave a reader unable to tell which belongs to the key.

        The fixture writes both digests out rather than pointing at a file that
        happens to contain some. An earlier version swapped in this test module
        on the assumption it held two, and it holds none, so the test passed by
        exercising the no-digest branch instead of the one it is named for.
        """
        first, second = "a" * 64, "b" * 64
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(f"pin {first} and also {second}\n", encoding="utf-8")
            with _swap("README", readme):
                self.assertIsNone(generator.readme_key_digest())

    def test_a_readme_that_pins_exactly_one_digest_returns_it(self):
        """The other side of the same branch, so neither direction is assumed."""
        only = "c" * 64
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(f"pin {only}\n", encoding="utf-8")
            with _swap("README", readme):
                self.assertEqual(generator.readme_key_digest(), only)

    def test_a_readme_with_no_digest_pins_nothing(self):
        """And the zero case, which is what the two-digest test used to cover."""
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text("no digest here\n", encoding="utf-8")
            with _swap("README", readme):
                self.assertIsNone(generator.readme_key_digest())

    def test_a_renamed_ci_check_is_reported(self):
        with _swap("ci_check_names", lambda: {"Some other job"}):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("no longer reports" in p for p in problems), problems)

    def test_every_pipeline_gate_names_a_real_ci_check(self):
        checks = generator.ci_check_names()
        for stage, gate in generator.PIPELINE_GATES.items():
            if gate:
                with self.subTest(stage=stage):
                    self.assertIn(gate, checks)

    def test_an_unsigned_bundle_is_reported(self):
        with _swap("signed_bundles", set):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("bundle.yaml.sig is missing" in p for p in problems), problems)

    def test_bundles_are_discovered_from_disk_not_listed(self):
        on_disk = {path.name for path in generator.PUBLISHED_DIR.iterdir()
                   if (path / "bundle.yaml").is_file()}
        self.assertEqual(set(generator.BUNDLES), on_disk)
        self.assertEqual(generator.BUNDLES[0], generator.DEFAULT_BUNDLE)

    def test_a_published_bundle_the_readme_never_installs_is_reported(self):
        # A README that documents only the default bundle, which is what the
        # install section quietly becomes if a new bundle lands unnoticed.
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(
                generator.README.read_text(encoding="utf-8").replace(
                    f"pipelock rules install {generator.BUNDLES[-1]}", "", 1),
                encoding="utf-8")
            with _swap("README", readme):
                problems = generator.verify_against_corpus()
        self.assertTrue(any("never shows how to install it" in p for p in problems), problems)

    def test_a_readme_installing_a_bundle_that_is_not_published_is_reported(self):
        with _swap("BUNDLES", (generator.DEFAULT_BUNDLE,)):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("which is not published" in p for p in problems), problems)

    def test_a_bundle_missing_from_the_makefile_preflight_loop_is_reported(self):
        with _swap("makefile_preflight_bundles", lambda: {generator.DEFAULT_BUNDLE}):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("PREFLIGHT_BUNDLES" in p for p in problems), problems)

    def test_the_makefile_preflight_loop_covers_every_published_bundle(self):
        self.assertTrue(set(generator.BUNDLES) <= generator.makefile_preflight_bundles())

    def test_a_readme_that_stops_linking_the_catalog_is_reported(self):
        # Written for the purpose rather than borrowed from the repository. An
        # earlier version swapped in CONTRIBUTING.md, which then gained a link
        # to the catalog, and the test stopped exercising the missing-link case
        # without anything failing to say so.
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text("A README that links no catalog.\n", encoding="utf-8")
            with _swap("README", readme):
                problems = generator.verify_against_corpus()
        self.assertTrue(any("generated catalog is unreachable" in p for p in problems), problems)

    def test_a_readme_naming_a_provider_no_rule_detects_is_reported(self):
        named = generator.README_NAMED_PROVIDERS + ("Nonexistent Vendor",)
        with _swap("README_NAMED_PROVIDERS", named):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("no rule detects it" in p for p in problems), problems)

    def test_every_provider_the_readme_names_is_really_covered(self):
        problems = [p for p in generator.verify_against_corpus() if "no rule detects it" in p]
        self.assertEqual(problems, [])

    def test_an_experimental_anatomy_rule_is_reported(self):
        rule = dict(generator.anatomy_rule(), status="experimental")
        with _swap("anatomy_rule", lambda: rule):
            problems = generator.verify_against_corpus()
        self.assertTrue(any("cannot" in p and "stable bar" in p for p in problems), problems)


class LiveNumbersTest(unittest.TestCase):
    """Drawings that carry a count must carry the live one."""

    def test_the_stats_strip_carries_the_live_numbers(self):
        text = _strings(generator.stats_strip(generator.PALETTES["dark"]))
        self.assertIn(str(len(generator._all_rules())), text)
        self.assertIn(str(generator.total_fixture_lines()), text)
        self.assertIn(str(len(generator.BUNDLES)), text)

    def test_the_coverage_chart_names_every_bundle_type_and_count(self):
        text = " ".join(_strings(generator.coverage(generator.PALETTES["dark"])))
        for bundle in generator.BUNDLES:
            self.assertIn(bundle, text)
            self.assertIn(generator.bundle_header(bundle)["version"], text)
            for rule_type in generator.RULE_TYPES:
                self.assertIn(rule_type, text)

    def test_every_stable_bar_records_the_count_it_draws(self):
        root = ElementTree.fromstring(generator.coverage(generator.PALETTES["dark"]))
        drawn = {(rect.get("data-bundle"), rect.get("data-type")): int(rect.get("data-stable"))
                 for rect in root.iter(SVG + "rect") if rect.get("data-bundle")}
        live = {(bundle, rule_type): counts["stable"]
                for bundle in generator.BUNDLES
                for rule_type, counts in generator.bundle_matrix(bundle).items()
                if counts["stable"]}
        self.assertEqual(drawn, live)

    def test_a_bar_width_is_proportional_to_its_count(self):
        root = ElementTree.fromstring(generator.coverage(generator.PALETTES["dark"]))
        bars = {(rect.get("data-bundle"), rect.get("data-type")):
                (float(rect.get("width")), int(rect.get("data-stable")))
                for rect in root.iter(SVG + "rect") if rect.get("data-bundle")}
        (wide, big), (narrow, small) = (max(bars.values(), key=lambda v: v[1]),
                                        min(bars.values(), key=lambda v: v[1]))
        # Widths are rounded to two decimals on the way out, so the ratio is
        # compared against that precision rather than to raw float equality.
        self.assertAlmostEqual(wide / narrow, big / small, delta=0.01)

    def test_the_coverage_chart_absorbs_a_third_bundle(self):
        # The repository has held exactly two bundles for its whole life, which
        # is how a fixed two-panel layout survives review looking correct. A
        # third has to land in a new row without clipping or overlapping.
        extra = "future-bundle"
        matrices = {b: generator.bundle_matrix(b) for b in generator.BUNDLES}
        matrices[extra] = {t: {"stable": 2, "experimental": 1} for t in generator.RULE_TYPES}
        headers = {b: generator.bundle_header(b) for b in generator.BUNDLES}
        headers[extra] = {"version": "2099.01.0", "format_version": "2",
                          "min_pipelock": "3.4.0", "name": extra, "author": "someone"}

        base = ElementTree.fromstring(generator.coverage(generator.PALETTES["dark"]))
        with _swap("BUNDLES", generator.BUNDLES + (extra,)), \
             _swap("bundle_matrix", lambda b: matrices[b]), \
             _swap("bundle_header", lambda b: headers[b]):
            grown_svg = generator.coverage(generator.PALETTES["dark"])

        grown = ElementTree.fromstring(grown_svg)
        self.assertIn(extra, " ".join(_strings(grown_svg)))
        # Taller, same width: it grew a row rather than squeezing the panels.
        self.assertEqual(base.get("width"), grown.get("width"))
        self.assertGreater(float(grown.get("height")), float(base.get("height")))
        _, _, width, height = (float(v) for v in grown.get("viewBox").split())
        for node in grown.iter():
            for x0, y0, x1, y1 in _extents(node):
                self.assertGreaterEqual(x0, -0.5)
                self.assertGreaterEqual(y0, -0.5)
                self.assertLessEqual(x1, width + 0.5)
                self.assertLessEqual(y1, height + 0.5)

    def test_the_catalog_lists_every_rule_in_every_bundle(self):
        catalog = generator.rule_catalog()
        for bundle in generator.BUNDLES:
            self.assertIn(f"## {bundle}", catalog)
            self.assertIn(generator.bundle_header(bundle)["version"], catalog)
            for rule in generator.bundle_rules(bundle):
                with self.subTest(rule=rule["id"]):
                    self.assertIn(f"`{rule['id']}`", catalog)
                    self.assertIn(rule["severity"], catalog)

    def test_the_catalog_carries_no_rule_pattern(self):
        # build() includes the catalog, so the repository-wide secrecy gate
        # covers it too. Asserted here as well because the catalog is prose and
        # an author could reasonably think pasting a pattern in would help.
        catalog = generator.rule_catalog()
        for bundle in generator.BUNDLES:
            for rule in generator.bundle_rules(bundle):
                match = generator.REGEX_FIELD.search(rule["block"])
                if match:
                    with self.subTest(rule=rule["id"]):
                        self.assertNotIn(match.group(1), catalog)

    def test_the_pipeline_carries_the_live_versions_and_assertion_count(self):
        text = " ".join(_strings(generator.pipeline(generator.PALETTES["dark"])))
        self.assertIn(generator.ci_pipelock_version(), text)
        self.assertIn(str(generator.total_fixture_lines()), text)
        for floor in generator.ci_compatibility_floors().values():
            self.assertIn(floor, text)

    def test_the_trust_chain_shows_the_real_key_digest(self):
        text = " ".join(_strings(generator.trust(generator.PALETTES["dark"])))
        self.assertIn(generator.official_key_digest()[:16], text)

    def test_pipeline_body_lines_fit_inside_their_card(self):
        # Mono advances at about 0.6em, so a longer line runs past the card
        # edge and into the next stage's arrow. This is how that shipped once.
        for _, _, _, lines in generator.pipeline_stages():
            for line in lines:
                with self.subTest(line=line):
                    self.assertLessEqual(len(line), generator.MONO_LINE_LIMIT)


class CommittedAssetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = generator.README.read_text(encoding="utf-8")

    def test_the_repository_assets_are_current(self):
        stale = [str(path.relative_to(generator.REPO_ROOT))
                 for path, content in generator.build().items()
                 if not path.exists() or path.read_text(encoding="utf-8") != content]
        self.assertEqual(stale, [], "run scripts/render_diagrams.py")

    def test_no_orphaned_generated_asset_remains(self):
        """Nothing sits in assets/ that no generator claims.

        A retired drawing left on disk keeps rendering somewhere forever. Two
        generators write here now, so this asks both rather than being widened
        to tolerate whatever it finds: an unclaimed file is still a defect.
        """
        expected = {path.name for path in generator.build()}
        expected |= {path.name for path in brand.build()}
        expected |= set(brand.PNG_EXPORTS)
        # Each raster records the vector it was exported from, so check-brand can
        # tell a current PNG from one left over by an earlier mark.
        expected |= {f"{png}.source" for png in brand.PNG_EXPORTS}
        expected.add(brand.MARK.name)          # the committed master
        on_disk = {path.name for path in generator.ASSET_DIR.iterdir()}
        self.assertEqual(on_disk - expected, set())

    def test_the_readme_embeds_both_themes_of_every_diagram(self):
        for name in generator.DIAGRAMS:
            with self.subTest(diagram=name):
                self.assertIn(f"assets/diagram-{name}-dark.svg", self.readme)
                self.assertIn(f"assets/diagram-{name}-light.svg", self.readme)

    def test_the_readme_uses_the_brand_casing(self):
        # PipeLab is the company and Pipelock is the product; the design system
        # calls the casing non-negotiable and the live site follows it.
        self.assertNotRegex(self.readme, r"\bPipelab\b")
        self.assertNotRegex(self.readme, r"\bPipeLock\b")
        self.assertNotRegex(self.readme, r"\bpipeLock\b")


if __name__ == "__main__":
    unittest.main()
