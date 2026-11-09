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
