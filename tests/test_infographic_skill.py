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
        # px, and numbers without a separator between them, are still read.
        for transform in ("translate(200px)", "translate(200PX, 0px)", "translate(200-0)"):
            assert check_svg.overlaps(_with_labels(apart.replace("translate(200)", transform))) == ([], 0), transform

    def test_translate_with_percent_or_em_is_skipped_and_counted(self):
        """translate() with % or em is not read as user units; the label is counted as not a plain length (#26)."""
        members = '<text x="20" y="40">Members</text>'
        for transform in ("translate(50%)", "translate(2em)", "translate(200, 5%)", "translate(1e1EM 0)"):
            for budget in (
                f'<g transform="{transform}"><text x="20" y="40">Budget</text></g>',
                f'<text x="20" y="40" transform="{transform}">Budget</text>',
            ):
                assert check_svg.overlap_report(_with_labels(members + budget)) == ([], {"units": 1}), budget

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

    def test_the_anchor_of_a_chunk_is_the_one_of_its_first_character(self):
        """The text-anchor of a <tspan> that holds the chunk's first character moves the chunk."""
        labels = (
            '<text x="300" y="40"><tspan text-anchor="end">Members</tspan></text>'
            '<text x="250" y="40">Budget</text>'
        )
        assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1

    def test_an_empty_tspan_does_not_move_the_text(self):
        """A <tspan> without characters has no effect on the position."""
        labels = '<text x="20" y="40">AAAA<tspan x="400"/>BBBBBBBB</text><text x="60" y="40">CCCCCC</text>'
        assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1

    def test_warnings_do_not_change_check(self):
        """check() still returns the structural problems only."""
        assert check_svg.check(_with_labels('<text x="20" y="40">A</text><text x="20" y="40">B</text>')) == []

    def test_the_documented_example_has_no_overlaps(self):
        """The example in docs/examples.md, sized by class rules, has no overlap warnings and no skipped labels."""
        svg = EXAMPLE_SVG.read_text(encoding="utf-8")
        assert check_svg.overlaps(svg) == ([], 0)
        styles, _ = check_svg._cascade(check_svg.ET.fromstring(svg))
        title = next(el for el in styles if el.get("class") == "title")
        assert styles[title]["font-size"] == "22px" and styles[title]["font-weight"] == "700"

    def test_style_rules_set_size_weight_and_anchor(self):
        """Class, id and element rules in <style>, and the font shorthand, are read."""
        members, budget = '<text{} x="20" y="40">Members</text>', '<text x="200" y="40">Budget</text>'
        assert check_svg.overlaps(_with_labels(members.format("") + budget)) == ([], 0)
        for rule, attribute in (
            (".big { font-size: 60px }", ' class="big"'),
            ("#big { font-size: 60px }", ' id="big"'),
            ("text { font-size: 60px }", ""),
            (".a, .big { font: 60px/1.2 sans-serif }", ' class="big"'),
        ):
            labels = f"<style>{rule}</style>" + members.format(attribute) + budget
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, rule
        # At x=255, Budget is clear of Members in normal 60 px text (ends at 251), not in bold (ends at 272).
        near = '<text x="255" y="40">Budget</text>'
        for font, bold in (
            ("bold 60px/1.2 sans-serif", True),
            ("60px sans-serif", False),
            ("italic 650 60px serif", True),
            ("450 60px serif", False),
        ):
            in_rule = f"<style>.a, .big {{ font: {font} }}</style>" + members.format(' class="big"') + near
            in_style = members.format(f' style="font: {font}"') + near
            for labels in (in_rule, in_style):
                assert len(check_svg.overlaps(_with_labels(labels))[0]) == int(bold), labels
        anchored = '<style>.r { text-anchor: end }</style><text class="r" x="100" y="40">Members</text>'
        assert len(check_svg.overlaps(_with_labels(anchored + '<text x="60" y="40">Budget</text>'))[0]) == 1
        assert check_svg.overlaps(_with_labels(anchored + '<text x="110" y="40">Budget</text>')) == ([], 0)

    def test_style_rule_precedence(self):
        """style= wins over rules, rules over attributes; id over class over element; then the later rule."""
        budget = '<text x="200" y="40">Budget</text>'
        cases = {
            # (rules, attributes of the first label): whether it is 60 px, so overlaps Budget
            ("text { font-size: 10px }", 'font-size="60"'): False,
            ("#a { font-size: 60px } .b { font-size: 10px } text { font-size: 10px }", 'id="a" class="b"'): True,
            ("#a { font-size: 10px }", 'id="a" style="font-size: 60px"'): True,
            (".a { font-size: 10px } .b { font-size: 60px }", 'class="b a"'): True,
            (".b { font-size: 60px } .a { font-size: 10px }", 'class="b a"'): False,
            ("text.a { font-size: 60px } .a { font-size: 10px }", 'class="a"'): True,
            # A repeated class counts twice; every selector of a comma list has its own specificity.
            (".big.big { font-size: 60px } .big { font-size: 10px }", 'class="big"'): True,
            (".big.big { font-size: 60px } .small { font-size: 10px }", 'class="big small"'): True,
            ("#x, .a { font-size: 60px } .a { font-size: 10px }", 'id="x" class="a"'): True,
            ("#x, .a { font-size: 60px } .a { font-size: 10px }", 'class="a"'): False,
        }
        for (rules, attributes), overlap in cases.items():
            labels = f'<style>{rules}</style><text {attributes} x="20" y="40">Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == int(overlap), (rules, attributes)

    def test_important_declarations_win(self):
        """!important wins over normal declarations, in style= and in rules; among them the usual order holds."""
        budget = '<text x="200" y="40">Budget</text>'
        cases = {
            # (rules, attributes of the first label): whether it is 60 px, so overlaps Budget
            ("", 'style="font-size: 60px!important; font-size: 10px"'): True,
            (".a { font-size: 60px !important }", 'class="a" style="font-size: 10px"'): True,
            (".a { font-size: 10px !important }", 'class="a" style="font-size: 60px !important"'): True,
            ("#a { font-size: 60px !important } .a { font-size: 10px !important }", 'id="a" class="a"'): True,
            (".a { font-size: 60px !important } .a { font-size: 10px }", 'class="a"'): True,
            (".a { font: bold 60px serif !IMPORTANT } .a { font-size: 10px }", 'class="a"'): True,
        }
        for (rules, attributes), overlap in cases.items():
            labels = f'<style>{rules}</style><text {attributes} x="20" y="40">Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == int(overlap), (rules, attributes)
        shown = '<text x="20" y="40" style="display: inline!important; display: none">Members</text>'
        assert len(check_svg.overlaps(_with_labels(shown + '<text x="20" y="40">Budget</text>'))[0]) == 1

    def test_a_font_shorthand_without_family_or_with_a_bad_number_changes_nothing(self):
        """A font shorthand that is not valid CSS (no family, a weight over 1000) leaves the font as it was."""
        budget = '<text x="200" y="40">Budget</text>'
        for font in ("bold 60px", "60px/1.2", "2000 60px serif", "60 serif", "650 16px sans-serif"):
            labels = f'<text x="20" y="40" style="font-size: 16px; font: {font}">Members</text>{budget}'
            assert check_svg.overlaps(_with_labels(labels)) == ([], 0), font

    def test_keywords_are_read_in_any_case(self):
        """CSS keywords such as NONE, BOLD, MIDDLE and HANGING are case-insensitive."""
        hidden = '<style>.h { display: NONE }</style><text class="h" x="20" y="40">Long Hidden Text</text>'
        assert check_svg.overlap_report(_with_labels(hidden + '<text x="20" y="40">Budget</text>')) == ([], {})
        bold = '<style>.a { font: BOLD 60px SANS-SERIF }</style><text class="a" x="20" y="40">Members</text>'
        assert len(check_svg.overlaps(_with_labels(bold + '<text x="255" y="40">Budget</text>'))[0]) == 1
        other = '<text x="140" y="40">Budget</text>'
        for anchor in ('style="text-anchor: MIDDLE"', 'text-anchor=" Middle "'):
            middle = f'<text x="100" y="40" {anchor}>Members</text>'
            assert check_svg.overlaps(_with_labels(middle + other)) == ([], 0), anchor
        assert len(check_svg.overlaps(_with_labels('<text x="100" y="40">Members</text>' + other))[0]) == 1

    def test_css_wide_keywords(self):
        """The keyword unset inherits an inherited property, initial gives the initial value, revert is not followed."""
        near = '<text x="255" y="40">Budget</text>'
        unset = '<g font-weight="bold"><text x="20" y="40" font-size="60" style="font-weight: unset">Members</text></g>'
        assert len(check_svg.overlaps(_with_labels(unset + near))[0]) == 1
        initial = '<g font-size="60"><text x="20" y="40" style="font-size: initial">Members</text></g>'
        assert check_svg.overlaps(_with_labels(initial + '<text x="200" y="40">Budget</text>')) == ([], 0)
        shown = '<text x="20" y="40" display="none" style="display: unset">Members</text>'
        assert len(check_svg.overlaps(_with_labels(shown + '<text x="20" y="40">Budget</text>'))[0]) == 1
        for style, reason in (
            ("font-size: revert", "css"),
            ("dominant-baseline: revert-layer", "css"),
            ("transform: inherit", "css-transform"),
        ):
            labels = f'<text x="20" y="40" style="{style}">Members</text><text x="20" y="40">Budget</text>'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {reason: 1}), style

    def test_labels_with_var_or_unfollowed_css_are_skipped_and_counted(self):
        """var() values, and properties such as letter-spacing or visibility, are not estimated but counted."""
        budget = '<text x="20" y="40">Budget</text>'
        for style in (
            'style="display: var(--shown)"',
            'style="text-anchor: var(--anchor)"',
            'style="font: var(--font)"',
            'style="letter-spacing: 4px"',
            'style="writing-mode: vertical-rl"',
            'style="rotate: 90deg"',
            'visibility="hidden"',
            'direction="rtl"',
        ):
            labels = f'<text x="20" y="40" {style}>Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), style
        for style in ('style="letter-spacing: normal"', 'visibility="visible"', 'style="rotate: none"'):
            labels = f'<text x="20" y="40" {style}>Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, style

    def test_positions_from_css_are_skipped_and_counted(self):
        """x, y, dx and dy set from CSS move a label (SVG 2); they are not followed but counted."""
        members = '<text x="20" y="40">Members</text>'
        for budget in (
            '<text x="300" y="40" style="x: 20px">Budget</text>',
            '<text x="300" y="40" style="dx: 0">Budget</text>',
            '<style>tspan { y: 40px }</style><text x="300" y="90"><tspan>Budget</tspan></text>',
        ):
            assert check_svg.overlap_report(_with_labels(members + budget)) == ([], {"css": 1}), budget
        # As attributes they are read, and from CSS on a group they move nothing.
        labels = '<g style="x: 300px"><text x="20" y="40">Members</text></g><text x="20" y="40" dx="0">Budget</text>'
        assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1

    def test_keywords_the_estimate_does_not_know_are_skipped_and_counted(self):
        """A text-anchor, dominant-baseline or font-weight it does not know is counted, not taken as the default."""
        budget = '<text x="70" y="40">Budget</text>'
        for attrs in (
            'text-anchor="end" style="text-anchor: bogus"',
            'text-anchor="ending"',
            'dominant-baseline="hanging" style="dominant-baseline: bogus"',
            'dominant-baseline="mathematical"',
            'font-weight="bold" style="font-weight: bogus"',
            'font-weight="1001"',
            'style="font-weight: 600px"',
        ):
            labels = f'<text x="100" y="40" {attrs}>Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), attrs
        for attrs in (
            'text-anchor="end"',
            'dominant-baseline="alphabetic"',
            'font-weight="450"',
            'font-weight="inherit"',
        ):
            labels = f'<text x="100" y="40" {attrs}>Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, attrs

    def test_alignment_baseline_and_width_changing_properties_are_skipped_and_counted(self):
        """alignment-baseline and the properties that change the width of text are counted, unless they are normal."""
        budget = '<text x="60" y="40">Budget</text>'
        for attrs in (
            'alignment-baseline="hanging"',
            'style="font-stretch: expanded"',
            'font-stretch="150%"',
            'font-variant="small-caps"',
            'font-size-adjust="0.9"',
            'style="text-transform: uppercase"',
            'style="white-space: pre"',
        ):
            labels = f'<text x="20" y="40" {attrs}>Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), attrs
        for attrs in (
            'alignment-baseline="baseline"',
            'style="font-stretch: normal"',
            'font-stretch="100%"',
            'font-variant="normal"',
            'font-size-adjust="none"',
            'style="text-transform: none"',
            'style="white-space: nowrap"',
        ):
            labels = f'<text x="20" y="40" {attrs}>Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, attrs

    def test_stretch_and_small_caps_in_the_font_shorthand_are_counted(self):
        """The font shorthand also sets font-stretch and font-variant: a stretch or small-caps is counted."""
        budget = '<text x="60" y="40">Budget</text>'
        for font in ("expanded 16px serif", "bold condensed 16px serif", "small-caps 16px serif"):
            labels = f'<text x="20" y="40" style="font: {font}">Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), font
        # Without them it resets both to normal.
        reset = '<text x="20" y="40" font-stretch="expanded" style="font: 16px serif">Members</text>'
        assert len(check_svg.overlaps(_with_labels(reset + budget))[0]) == 1

    def test_no_effect_values_are_per_property(self):
        """A value without effect for one property (0, 100%) may have one for another: scale: 0, translate: 100%."""
        budget = '<text x="20" y="40">Budget</text>'
        for attrs in (
            'style="scale: 0"',
            'style="translate: 100%"',
            'baseline-shift="100%"',
            'style="font-size-adjust: 0"',
            'style="rotate: 0"',
            'style="font-variant: none"',
        ):
            labels = f'<text x="20" y="40" {attrs}>Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), attrs
        for attrs in (
            'style="scale: 1"',
            'style="scale: 1 100%"',
            'style="translate: 0 0px"',
            'style="rotate: 0deg"',
            'baseline-shift="0"',
            'style="letter-spacing: 0"',
            'style="font-stretch: 100%"',
            'style="font-size-adjust: initial"',
        ):
            labels = f'<text x="20" y="40" {attrs}>Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, attrs

    def test_the_font_shorthand_resets_the_width_changing_font_properties(self):
        """font, also as initial, inherit or a system font, resets an earlier stretch, variant, size adjustment, ..."""
        budget = '<text x="20" y="40">Budget</text>'
        for earlier in (
            "font-stretch: expanded",
            "font-variant: small-caps",
            "font-variant-caps: small-caps",
            "font-size-adjust: 0.5",
            "font-kerning: none",
            "font-feature-settings: 'liga' 0",
            "font-variation-settings: 'wdth' 150",
        ):
            for font in ("initial", "inherit", "unset", "16px serif"):
                labels = f'<text x="20" y="40" style="{earlier}; font: {font}">Members</text>{budget}'
                assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, (earlier, font)
            # In a later rule, too.
            rules = f"<style>.a {{ {earlier} }} .b {{ font: initial }}</style>"
            labels = f'{rules}<text class="a b" x="20" y="40">Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, earlier
            # A system font resets them as well; its size is then not followed.
            labels = f'<text x="20" y="40" style="{earlier}; font: caption">Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels))[1] == {"css": 1}, earlier
        # font-variant resets its longhands.
        labels = (
            f'<text x="20" y="40" style="font-variant-caps: small-caps; font-variant: normal">Members</text>{budget}'
        )
        assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1

    def test_all_sets_every_property_it_covers(self):
        """all: initial resets display and the rest, positions too, so the label is counted.

        Later declarations still win; all: revert or var() is counted.
        """
        budget = '<text x="20" y="40">Budget</text>'
        for attrs in (
            'display="none" style="all: initial"',
            'display="none" style="all: unset"',
            'font-stretch="expanded" style="all: initial"',
            'transform="rotate(90)" style="all: initial"',
            'display="none" style="all: initial !important; display: none"',
        ):
            labels = f'<text x="20" y="40" {attrs}>Members</text>{budget}'
            # Drawn (display reset), but its position comes from CSS (x and y
            # reset to 0): counted, not measured at x="20" y="40".
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), attrs
        for attrs in ('style="all: initial; display: none"', 'style="display: none !important; all: initial"'):
            labels = f'<text x="20" y="40" {attrs}>Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {}), attrs
        for attrs in ('display="none" style="all: revert"', 'display="none" style="all: var(--reset)"'):
            labels = f'<text x="20" y="40" {attrs}>Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), attrs
        rule = '<style>text { all: initial }</style><text x="20" y="40" display="none">Members</text>'
        # In a rule it beats the attribute and applies to both labels; an all
        # that is not valid is dropped. Both are counted, none measured.
        labels = rule + '<text x="20" y="40" style="all: none">Budget</text>'
        assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 2})
        # The reviewer's case: all: initial from a rule must not hide an overlap.
        labels = '<style>text { all: initial }</style><text x="10" y="40">AAAA</text><text x="60" y="40">B</text>'
        assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 2})

    def test_font_variant_passes_css_wide_keywords_to_its_longhands(self):
        """font-variant: inherit takes the parent's longhands (a guard: the label is counted either way today)."""
        budget = '<text x="20" y="40">Budget</text>'
        members = '<text x="20" y="40" style="font-variant: inherit">Members</text>'
        labels = f'<g style="font-variant-caps: small-caps">{members}</g>{budget}'
        assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1})

    def test_other_width_changing_font_properties_are_skipped_and_counted(self):
        """The font-variant longhands, font-kerning, font-feature-settings, ... are counted, unless without effect."""
        budget = '<text x="20" y="40">Budget</text>'
        for style in (
            "font-variant-caps: small-caps",
            "font-variant-numeric: tabular-nums",
            "font-variant-ligatures: none",
            "font-variant-east-asian: full-width",
            "font-variant-position: super",
            "font-kerning: none",
            "font-feature-settings: 'smcp'",
            "font-variation-settings: 'wght' 900",
            "font-synthesis: none",
        ):
            labels = f'<text x="20" y="40" style="{style}">Members</text>{budget}'
            assert check_svg.overlap_report(_with_labels(labels)) == ([], {"css": 1}), style
        for style in (
            "font-variant-caps: normal",
            "font-variant-numeric: normal",
            "font-variant-ligatures: normal",
            "font-variant-east-asian: normal",
            "font-variant-position: normal",
            "font-kerning: auto",
            "font-feature-settings: normal",
            "font-variation-settings: normal",
            "font-synthesis: weight style",
        ):
            labels = f'<text x="20" y="40" style="{style}">Members</text>{budget}'
            assert len(check_svg.overlaps(_with_labels(labels))[0]) == 1, style

    def test_style_media_other_than_screen_is_not_read(self):
        """A <style> with a media other than all or screen may not hold; labels it may style are counted."""
        labels = '<text x="20" y="40">Members</text><text x="20" y="40">Budget</text>'
        for media in ("not all", "print", "screen and (min-width: 1px)"):
            sheet = f'<style media="{media}">text {{ display: none }}</style>'
            assert check_svg.overlap_report(_with_labels(sheet + labels)) == ([], {"style": 2}), media
        for media in ("", "all", "Screen"):
            sheet = f'<style media="{media}">text {{ display: none }}</style>'
            assert check_svg.overlap_report(_with_labels(sheet + labels)) == ([], {}), media

    def test_braces_and_semicolons_in_strings_and_urls(self):
        """A { } or ; inside a quoted string or url(...) does not end a rule or a declaration."""
        members, budget = '<text class="x" x="20" y="40">Members</text>', '<text x="200" y="40">Budget</text>'
        for rule in (
            '.x { font-family: "}"; font-size: 60px }',
            ".x { font-family: 'a;b{'; font-size: 60px }",
            ".x { fill: url(#a;}); font-size: 60px }",
            '.x { font: bold 60px "My {Font}" }',
        ):
            assert len(check_svg.overlaps(_with_labels(f"<style>{rule}</style>{members}{budget}"))[0]) == 1, rule
        inline = members.replace('class="x"', "style='font-family: \"a;b\"; font-size: 60px'")
        assert len(check_svg.overlaps(_with_labels(inline + budget))[0]) == 1

    def test_deeply_nested_at_rules_are_read(self):
        """Thousands of nested at-rules do not crash the check; their rules count as not read."""
        css = "@media all {" * 5000 + ".x { font-size: 60px }" + "}" * 5000
        labels = f'<style>{css}</style><text class="x" x="20" y="40">Members</text>'
        assert check_svg.overlap_report(_with_labels(labels)) == ([], {"style": 1})

    def test_the_note_names_sizes_that_are_not_plain_lengths(self, tmp_path, capsys):
        """A font size such as large, in em or not a number is counted as not a plain length."""
        path = tmp_path / "units.svg"
        path.write_text(_with_labels('<text x="20" y="40" font-size="large">A</text>'), encoding="utf-8")
        assert check_svg.main([str(path)]) == 0
        assert "1 with a position or font size that is not a plain length" in capsys.readouterr().out

    def test_labels_styled_by_rules_that_are_not_read_are_skipped_and_counted(self):
        """Rules with combinators, pseudo-classes, attribute selectors or inside at-rules are not guessed."""
        label = '<g class="c"><text class="x" x="20" y="40">Members</text></g>'
        for rule in (
            ".c text { font-size: 60px }",
            ".c > .x { font-weight: bold }",
            "text:first-child { text-anchor: end }",
            '[class="x"] { dominant-baseline: hanging }',
            "@media (min-width: 1px) { .x { font-size: 60px } }",
            "g.c * { transform: rotate(90deg) }",
            "@starting-style { .x { font-size: 60px } }",
            "@-moz-document url-prefix() { .x { font-size: 60px } }",
            ".c { &amp; .x { font-size: 60px } }",
            # A display of none from such a rule is not applied: the rule may not match.
            "g.c text { display: none }",
        ):
            assert check_svg.overlap_report(_with_labels(f"<style>{rule}</style>{label}")) == ([], {"style": 1}), rule
        # Rules that set nothing the estimate uses, or cannot match the label, change nothing.
        for rule in (
            ".c text { fill: red }",
            "rect:hover { font-size: 60px }",
            ".bar.last { fill: red }",
            "@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(90deg) } }",
            "@font-face { font-family: x; src: local(x) }",
            "@page { margin: 1cm; @top-left { content: 'x' } }",
        ):
            assert check_svg.overlaps(_with_labels(f"<style>{rule}</style>{label}")) == ([], 0), rule

    def test_a_css_transform_is_skipped_and_counted(self):
        """A CSS transform other than none, in style= or a rule, makes its label skipped and counted."""
        members = '<text x="20" y="40">Members</text>'
        for budget in (
            '<text x="20" y="40" style="transform: rotate(90deg); transform-origin: 20px 40px">Budget</text>',
            '<text x="20" y="40" style="transform: translate(200px)">Budget</text>',
            '<style>.t { transform: scale(2) }</style><g class="t"><text x="20" y="40">Budget</text></g>',
        ):
            assert check_svg.overlap_report(_with_labels(members + budget)) == ([], {"css-transform": 1}), budget
        none = '<text x="20" y="40" style="transform: none">Budget</text>'
        assert len(check_svg.overlaps(_with_labels(members + none))[0]) == 1

    def test_a_label_in_a_nested_svg_is_skipped_and_counted(self):
        """A nested <svg> with x, y or a viewBox moves its labels, which is not followed."""
        labels = '<svg x="400"><text x="20" y="40">Budget</text></svg><text x="20" y="40">Members</text>'
        assert check_svg.overlap_report(_with_labels(labels)) == ([], {"nested-svg": 1})

    def test_title_desc_and_metadata_in_a_label_are_not_measured(self):
        """<title>, <desc> and <metadata> inside a <text> draw nothing; the text after them does."""
        for child in ("title", "desc", "metadata"):
            tooltip = f'<text x="20" y="40"><{child}>A very long tooltip text here</{child}>Hi</text>'
            assert check_svg.overlaps(_with_labels(tooltip + '<text x="80" y="40">Budget</text>')) == ([], 0)
            assert len(check_svg.overlaps(_with_labels(tooltip + '<text x="25" y="40">Budget</text>'))[0]) == 1

    def test_hidden_labels_are_neither_checked_nor_counted(self):
        """A display of none on a label, a parent or a <tspan>, set any way, draws nothing."""
        budget = '<text x="20" y="40">Budget</text>'
        for hidden in (
            '<text x="20" y="40" display="none">Members</text>',
            '<text x="20" y="40" style="display: none">Members</text>',
            '<style>.h { display: none }</style><text class="h" x="20" y="40">Members</text>',
            '<g display="none"><text x="20" y="40">Members</text></g>',
            '<text x="20" y="40"><tspan display="none">Members</tspan></text>',
        ):
            assert check_svg.overlap_report(_with_labels(hidden + budget)) == ([], {}), hidden
        partly = '<text x="20" y="40"><tspan display="none">Long hidden text</tspan>Hi</text>'
        assert check_svg.overlaps(_with_labels(partly + '<text x="60" y="40">Budget</text>')) == ([], 0)

    def test_a_text_path_is_skipped_and_counted(self):
        """Text on a <textPath> is laid out along the path, which is not followed."""
        labels = (
            '<path id="p" d="M20 40 L300 40"/><text><textPath href="#p">Budget</textPath></text>'
            '<text x="20" y="40">Members</text>'
        )
        assert check_svg.overlap_report(_with_labels(labels)) == ([], {"textPath": 1})

    def test_the_note_says_what_was_skipped(self, tmp_path, capsys):
        """The note line counts the labels not checked, per kind."""
        labels = (
            '<svg x="400"><text x="20" y="40">A</text></svg>'
            '<text x="20" y="40" transform="rotate(90)">B</text><text x="20" y="80" transform="scale(2)">C</text>'
        )
        path = tmp_path / "skipped.svg"
        path.write_text(_with_labels(labels), encoding="utf-8")
        assert check_svg.main([str(path)]) == 0
        out = capsys.readouterr().out
        assert (
            f"{path}: note: 3 label(s) not checked for overlap: "
            "1 inside a nested <svg>, 2 with a rotate, scale, matrix or skew transform"
        ) in out

    def test_strict_makes_warnings_fail(self, tmp_path, capsys):
        """A warning prints but exits 0; with --strict it exits 1."""
        path = tmp_path / "overlap.svg"
        path.write_text(_with_labels('<text x="20" y="40">A</text><text x="20" y="40">B</text>'), encoding="utf-8")
        assert check_svg.main([str(path)]) == 0
        assert check_svg.main(["--strict", str(path)]) == 1
        out = capsys.readouterr().out
        assert f"{path}: warning: labels overlap: 'A' and 'B'" in out
        assert f"{path}: ok" not in out
