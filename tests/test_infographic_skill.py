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
