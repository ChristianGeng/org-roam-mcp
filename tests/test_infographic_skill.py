"""Tests for the org-roam-infographic skill: its SKILL.md and check_svg.py (#3)."""

import importlib.util
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "org-roam-infographic"
EXAMPLE_SVG = Path(__file__).resolve().parent.parent / "docs" / "img" / "reading-circle-members.svg"


def _load_check_svg():
    """Import check_svg.py from the skill folder, which is not a package."""
    spec = importlib.util.spec_from_file_location("check_svg", SKILL_DIR / "check_svg.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_svg = _load_check_svg()

GOOD = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
  <title>Two numbers</title>
  <desc>A is 3.</desc>
  <rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>
  <text x="20" y="40">A: 3</text>
</svg>"""


class TestSkillFile:
    """SKILL.md has the front matter agents read."""

    def test_front_matter_has_name_and_description(self):
        """The front matter starts the file and names the skill."""
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        front = text.split("---\n", 2)[1]
        fields = dict(line.split(":", 1) for line in front.strip().splitlines())
        assert fields["name"].strip() == "org-roam-infographic"
        assert len(fields["description"].strip()) > 50

    def test_skill_says_nothing_is_sent(self):
        """The instructions forbid image APIs and uploads."""
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert "no image API" in text
        assert "Never overwrite a file" in text


class TestCheckSvg:
    """check_svg.check() reports what the skill forbids."""

    def test_good_svg_passes(self):
        """A small, self-contained SVG with a background card has no problems."""
        assert check_svg.check(GOOD) == []

    def test_the_documented_example_passes(self):
        """The example in docs/examples.md follows the skill's own rules."""
        assert check_svg.check(EXAMPLE_SVG.read_text(encoding="utf-8")) == []

    def test_not_xml(self):
        """Broken XML is one problem, not a crash."""
        assert check_svg.check("<svg")[0].startswith("not well-formed XML")

    def test_too_wide(self):
        """A width over 1200 px is reported."""
        problems = check_svg.check(GOOD.replace('width="400"', 'width="1500"', 1))
        assert any("over 1200 px" in p for p in problems)

    def test_external_image_and_script(self):
        """Images, scripts and external links are reported."""
        bad = GOOD.replace(
            "</svg>",
            '<image href="https://example.org/a.png"/><script>alert(1)</script></svg>',
        )
        problems = check_svg.check(bad)
        assert any("<image>" in p for p in problems)
        assert any("<script>" in p for p in problems)
        assert any("external reference" in p for p in problems)

    def test_style_that_loads_from_outside(self):
        """@import, @font-face and url() in styles are reported."""
        bad = GOOD.replace("</svg>", "<style>@import url(https://example.org/a.css);</style></svg>")
        assert any("loads something from outside" in p for p in check_svg.check(bad))

    def test_local_references_are_fine(self):
        """References inside the file (#id) are allowed."""
        ok = GOOD.replace("</svg>", '<use href="#t"/></svg>')
        assert check_svg.check(ok) == []

    def test_text_as_paths_only(self):
        """A picture without <text> is reported."""
        bad = GOOD.replace('<text x="20" y="40">A: 3</text>', '<path d="M0 0 L10 10"/>')
        assert any("no <text>" in p for p in check_svg.check(bad))

    def test_missing_background_card(self):
        """Without a filled rect over the whole picture, dark pages are a problem."""
        bad = GOOD.replace('fill="#f8fafc"', 'fill="none"')
        assert any("background card" in p for p in check_svg.check(bad))

    def test_missing_width_or_height_attribute(self):
        """A viewBox alone is not enough; width= and height= must be set."""
        no_width = GOOD.replace(' width="400"', "", 1)
        no_height = GOOD.replace(' height="200"', "", 1)
        assert any("no width=" in p for p in check_svg.check(no_width))
        assert any("no height=" in p for p in check_svg.check(no_height))

    def test_card_must_cover_an_offset_view_box(self):
        """With viewBox "-20 -20 400 200", a card at 0,0 leaves part uncovered."""
        offset = GOOD.replace('viewBox="0 0 400 200"', 'viewBox="-20 -20 400 200"')
        assert any("background card" in p for p in check_svg.check(offset))
        covered = offset.replace('<rect x="0" y="0"', '<rect x="-20" y="-20"')
        assert check_svg.check(covered) == []

    def test_viewbox_may_use_plus_signs(self):
        """SVG numbers may start with +, so "+0 +0 +400 +200" is a valid viewBox."""
        plus = GOOD.replace('viewBox="0 0 400 200"', 'viewBox="+0 +0 +400 +200"')
        assert check_svg.check(plus) == []

    def test_card_in_switch_branch_that_may_not_show(self):
        """A <switch> with a conditional child cannot be checked and is reported."""
        card = '<rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>'
        conditional = card.replace("<rect ", '<rect systemLanguage="xx" ')
        hidden = GOOD.replace(card, "<switch>" + conditional + "</switch>")
        assert any("cannot be checked" in p for p in check_svg.check(hidden))

    def test_card_in_unconditional_switch_branch_passes(self):
        """The first child of a <switch> without conditions is always shown."""
        card = '<rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>'
        shown = GOOD.replace(card, "<switch>" + card + "</switch>")
        assert check_svg.check(shown) == []

    def test_conditional_branch_before_card_is_not_counted(self):
        """A conditional child ahead of the card may be the one shown, so the switch is reported once."""
        card = '<rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>'
        cond = '<circle systemLanguage="en" r="1"/>'
        svg = GOOD.replace(card, "<switch>" + cond + card + "</switch>")
        problems = check_svg.check(svg)
        assert sum("cannot be checked" in p for p in problems) == 1

    def test_card_drawn_after_the_text_is_reported(self):
        """A card painted after the labels hides them."""
        late = GOOD.replace(
            '  <rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>\n  <text x="20" y="40">A: 3</text>',
            '  <text x="20" y="40">A: 3</text>\n  <rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>',
        )
        assert any("drawn after <text>" in p for p in check_svg.check(late))

    def test_missing_desc(self):
        """<desc> with the message and the numbers is required, like <title>."""
        bad = GOOD.replace("  <desc>A is 3.</desc>\n", "")
        assert any("no <desc>" in p for p in check_svg.check(bad))

    def test_relative_url_in_style_or_attribute(self):
        """A url(...) to another file is reported; url(#id) inside the file is fine."""
        in_style = GOOD.replace("</svg>", "<style>rect { filter: url(./effects.svg#blur); }</style></svg>")
        assert any("url(./effects.svg#blur)" in p for p in check_svg.check(in_style))
        in_attr = GOOD.replace('fill="#f8fafc"', 'fill="url(other.svg#grad)"')
        assert any("url(other.svg#grad)" in p for p in check_svg.check(in_attr))
        local = GOOD.replace(
            "</svg>",
            '<defs><linearGradient id="g"/></defs><rect x="0" y="0" width="10" height="10" fill="url(#g)"/></svg>',
        )
        assert check_svg.check(local) == []

    def test_numbers_in_scientific_and_leading_decimal_form(self):
        """Numbers in viewBox and lengths, like "4e2" and ".5", are valid SVG numbers."""
        sci = GOOD.replace('viewBox="0 0 400 200"', 'viewBox="0 0 4e2 2E2"').replace(
            'width="400" height="200" fill', 'width="4.0e2" height="200.0" fill'
        )
        assert check_svg.check(sci) == []
        leading = GOOD.replace('<rect x="0" y="0"', '<rect x=".0" y="-.0"')
        assert check_svg.check(leading) == []

    def test_template_in_defs_does_not_count_as_painted(self):
        """A <text> template in <defs> before the card is not painted there."""
        templated = GOOD.replace(
            "  <rect x=",
            '  <defs><text id="label">A: 3</text></defs>\n  <rect x=',
            1,
        )
        assert check_svg.check(templated) == []

    def test_card_after_bars_is_reported(self):
        """A card painted after shapes (not only text) hides them."""
        late = GOOD.replace(
            "  <rect x=",
            '  <g><rect x="40" y="60" width="20" height="80" fill="#2f6f9f"/></g>\n  <rect x=',
            1,
        )
        assert any("drawn after <rect>" in p for p in check_svg.check(late))

    def test_escaped_css_cannot_hide_url_or_import(self):
        """CSS escapes (hex for a letter, or a backslash before @) are decoded before the check."""
        hex_escaped = GOOD.replace("</svg>", "<style>rect { fill: u\\72l(https://example.org/a.png); }</style></svg>")
        assert any("https://example.org/a.png" in p for p in check_svg.check(hex_escaped))
        char_escaped = GOOD.replace("</svg>", "<style>\\@import 'https://example.org/a.css';</style></svg>")
        assert any("@import" in p for p in check_svg.check(char_escaped))

    def test_malformed_view_box_is_reported(self):
        """A viewBox with units or not exactly four numbers is invalid SVG."""
        for bad_box in ("10 10 400px 200", "0 0 400", "0 0 400 200 5"):
            bad = GOOD.replace('viewBox="0 0 400 200"', f'viewBox="{bad_box}"')
            assert any("no valid viewBox" in p for p in check_svg.check(bad)), bad_box
        commas = GOOD.replace('viewBox="0 0 400 200"', 'viewBox="0,0, 400 ,200"')
        assert check_svg.check(commas) == []

    def test_card_inside_a_switch_counts_as_first(self):
        """<switch> is a container like <g>; a card inside it is still first."""
        switched = GOOD.replace(
            '  <rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>',
            '  <switch><rect x="0" y="0" width="400" height="200" fill="#f8fafc"/></switch>',
        )
        assert check_svg.check(switched) == []

    def test_card_through_use_is_not_accepted(self):
        """The skill asks for the card as a <rect> drawn first, not reused through <use>."""
        reused = GOOD.replace(
            '  <rect x="0" y="0" width="400" height="200" fill="#f8fafc"/>',
            '  <defs><rect id="card" x="0" y="0" width="400" height="200" fill="#f8fafc"/></defs>\n'
            '  <use href="#card"/>',
        )
        assert any("background card" in p for p in check_svg.check(reused))

    def test_escaped_backslash_cannot_fake_a_fragment(self):
        """An escaped backslash stays a backslash, so it cannot turn an outside file into a #fragment."""
        tricky = GOOD.replace("</svg>", '<style>rect { fill: url("\\\\23 file.svg"); }</style></svg>')
        assert any("from outside the file" in p for p in check_svg.check(tricky))
        fragment = GOOD.replace(
            "</svg>",
            '<defs><linearGradient id="file.svg"/></defs><style>rect { fill: url(\\23 file.svg); }</style></svg>',
        )
        assert not any("from outside the file" in p for p in check_svg.check(fragment))

    def test_main_exit_status(self, tmp_path, capsys):
        """main() prints ok or the problems, and returns 0 or 1."""
        good = tmp_path / "good.svg"
        good.write_text(GOOD, encoding="utf-8")
        bad = tmp_path / "bad.svg"
        bad.write_text(GOOD.replace('width="400"', 'width="1500"', 1), encoding="utf-8")
        assert check_svg.main([str(good)]) == 0
        assert check_svg.main([str(bad)]) == 1
        out = capsys.readouterr().out
        assert f"{good}: ok" in out
        assert "over 1200 px" in out


def _with_labels(labels: str) -> str:
    """Return GOOD with its label replaced by the given <text> elements."""
    return GOOD.replace('<text x="20" y="40">A: 3</text>', labels)


class TestOverlaps:
    """check_svg.overlaps() warns about labels that seem to overlap (#19)."""

    def test_labels_at_the_same_place(self):
        """Two labels at the same place are one warning, with both texts."""
        warnings, skipped = check_svg.overlaps(
            _with_labels('<text x="20" y="40">Members</text><text x="20" y="40">Budget</text>')
        )
        assert len(warnings) == 1
        assert "'Members'" in warnings[0] and "'Budget'" in warnings[0]
        assert skipped == 0

    def test_labels_side_by_side_with_room(self):
        """Labels next to each other with room between them are fine."""
        svg = _with_labels('<text x="20" y="40">Members</text><text x="120" y="40">Budget</text>')
        assert check_svg.overlaps(svg) == ([], 0)

    def test_text_anchor_moves_the_box(self):
        """An anchor of middle centres the box on x, and end ends it there."""
        start = '<text x="100" y="40">Members</text>'
        middle = '<text x="100" y="40" text-anchor="middle">Budget</text>'
        end = '<text x="100" y="40" style="text-anchor: end">Budget</text>'
        assert len(check_svg.overlaps(_with_labels(start + middle))[0]) == 1
        assert check_svg.overlaps(_with_labels(start + end)) == ([], 0)

    def test_translate_on_a_parent_moves_the_box(self):
        """translate(...) on a parent <g> moves its labels."""
        apart = '<text x="20" y="40">Members</text><g transform="translate(200)"><text x="20" y="40">Budget</text></g>'
        assert check_svg.overlaps(_with_labels(apart)) == ([], 0)
        together = apart.replace("translate(200)", "translate(0, 0) translate(5 2)")
        assert len(check_svg.overlaps(_with_labels(together))[0]) == 1

    def test_inherited_font_size(self):
        """A large font size set on a parent <g> makes the box larger."""
        labels = '<text x="20" y="40">Members</text><text x="20" y="70">Budget</text>'
        assert check_svg.overlaps(_with_labels(labels)) == ([], 0)
        large = f'<g font-size="48">{labels}</g>'
        assert len(check_svg.overlaps(_with_labels(large))[0]) == 1

    def test_rotated_label_is_skipped_and_counted(self):
        """A rotated label is not checked, and the count says so."""
        labels = '<text x="20" y="40">Members</text><text x="20" y="40" transform="rotate(-90 20 40)">Budget</text>'
        assert check_svg.overlaps(_with_labels(labels)) == ([], 1)

    def test_tspans_with_their_own_position_are_lines(self):
        """<tspan>s with x and dy are separate lines, so they do not overlap each other."""
        lines = '<text x="20" y="40">First line<tspan x="20" dy="1.2em">Second line</tspan></text>'
        assert check_svg.overlaps(_with_labels(lines)) == ([], 0)
        same = lines.replace('dy="1.2em"', 'dy="0"')
        assert len(check_svg.overlaps(_with_labels(same))[0]) == 1

    def test_dx_and_dy_move_the_label(self):
        """The attributes dx and dy move a label even without its own x or y."""
        below = '<text x="20" y="40">Members</text><text x="20" y="40" dy="40">Budget</text>'
        assert check_svg.overlaps(_with_labels(below)) == ([], 0)
        back = '<text x="20" y="40">Members</text><text x="300" y="40" dx="-280">Budget</text>'
        assert len(check_svg.overlaps(_with_labels(back))[0]) == 1

    def test_a_tspan_with_only_y_goes_on_after_the_text_before_it(self):
        """A <tspan> with y and no x starts where the text before it ended, not at the line's x."""
        text = '<text x="20" y="40">FirstLongText<tspan y="80">Second</tspan></text>'
        assert check_svg.overlaps(_with_labels(text + '<text x="20" y="80">Other</text>')) == ([], 0)
        assert len(check_svg.overlaps(_with_labels(text + '<text x="150" y="80">Other</text>'))[0]) == 1

    def test_an_inline_tspan_is_measured_in_its_own_font_size(self):
        """A <tspan> without a position but with a larger font is measured at that size."""
        labels = '<text x="20" y="40"><tspan font-size="48">Hello</tspan></text><text x="100" y="40">World</text>'
        assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1

    def test_pieces_of_one_label_do_not_overlap_each_other(self):
        """Text and <tspan>s on one line touch each other; that is no warning."""
        label = '<text x="20" y="40">Members: <tspan font-weight="bold">12</tspan> people</text>'
        assert check_svg.overlaps(_with_labels(label)) == ([], 0)

    def test_a_tspan_keeps_the_baseline_of_its_label(self):
        """dominant-baseline set on the <text> or a parent <g> holds for its <tspan>s too."""
        plain = '<text x="20" y="40" dominant-baseline="hanging">HelloWorld</text><text x="70" y="32">Other</text>'
        styled = plain.replace("HelloWorld", 'Hello<tspan font-weight="bold">World</tspan>')
        assert check_svg.overlaps(_with_labels(styled)) == check_svg.overlaps(_with_labels(plain))
        first, other = styled.replace(' dominant-baseline="hanging"', "").split("</text>", 1)
        grouped = f'<g dominant-baseline="hanging">{first}</text></g>{other}'
        assert check_svg.overlaps(_with_labels(grouped)) == check_svg.overlaps(_with_labels(plain))

    def test_overlap_is_judged_against_whole_labels(self):
        """A short piece almost covered by another label is no warning if the labels overlap little."""
        labels = (
            '<text x="0" y="40"><tspan font-weight="bold">A</tspan>LLLLLLLLLLLLLLL</text>'
            '<text x="-75" y="40">MMMMMMMMMM</text>'
        )
        assert check_svg.overlaps(_with_labels(labels)) == ([], 0)

    def test_a_transformed_or_rotated_tspan_is_skipped_and_counted(self):
        """A <tspan> with a transform, or rotate on its glyphs, makes its label skipped and counted."""
        for attribute in ('transform="rotate(90)"', 'rotate="30"'):
            labels = f'<text x="20" y="40">Members</text><text x="20" y="40">A<tspan {attribute}>B</tspan></text>'
            assert check_svg.overlaps(_with_labels(labels)) == ([], 1)

    def test_warnings_do_not_change_check(self):
        """check() still returns the structural problems only."""
        assert check_svg.check(_with_labels('<text x="20" y="40">A</text><text x="20" y="40">B</text>')) == []

    def test_the_documented_example_has_no_overlaps(self):
        """The example in docs/examples.md has no overlap warnings and no skipped labels."""
        assert check_svg.overlaps(EXAMPLE_SVG.read_text(encoding="utf-8")) == ([], 0)

    def test_strict_makes_warnings_fail(self, tmp_path, capsys):
        """A warning prints but exits 0; with --strict it exits 1."""
        path = tmp_path / "overlap.svg"
        path.write_text(_with_labels('<text x="20" y="40">A</text><text x="20" y="40">B</text>'), encoding="utf-8")
        assert check_svg.main([str(path)]) == 0
        assert check_svg.main(["--strict", str(path)]) == 1
        out = capsys.readouterr().out
        assert f"{path}: warning: labels overlap: 'A' and 'B'" in out
        assert f"{path}: ok" not in out
