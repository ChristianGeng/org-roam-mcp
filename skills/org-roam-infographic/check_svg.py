"""Check an infographic SVG against the rules of the org-roam-infographic skill.

Usage: python check_svg.py [--strict] FILE.svg [FILE.svg ...]

Prints one line per problem and exits 1 if there is any, 0 if the file is
fine. It also warns about text labels that seem to overlap; the sizes of the
labels are estimates, so a warning alone does not fail, unless --strict is
given. Rendering the file and looking at it is still needed (see SKILL.md,
step 4). Uses the standard library only.
"""

import re
import sys
import xml.etree.ElementTree as ET


XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
MAX_WIDTH = 1200
FORBIDDEN_TAGS = {"script", "foreignObject", "image"}
# Elements that describe or style the picture but draw nothing.
NOT_DRAWN = {"svg", "title", "desc", "style", "defs", "metadata", "g", "a", "switch"}
# Containers whose content is a template, painted only where it is used.
TEMPLATES = {"defs", "symbol", "clipPath", "mask", "marker", "pattern", "linearGradient", "radialGradient", "filter"}
# Attributes that make a <switch> child conditional.
CONDITIONS = ("systemLanguage", "requiredExtensions", "requiredFeatures")
NUMBER = r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
# One CSS escape: a backslash and 1 to 6 hex digits (and one optional white
# space), or a backslash and any other character. Read left to right in one
# pass, so an escaped backslash ("\\\\") stays a backslash.
CSS_ESCAPE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})[ \t\n\r\f]?|(.))", re.DOTALL)
URL_IN_CSS = re.compile(r"url\(\s*['\"]?([^)'\"]*)", re.IGNORECASE)
CSS_LOADS = re.compile(r"@import|@font-face", re.IGNORECASE)
# Estimated label boxes: font size when none is set, average character width
# as a share of the font size (normal and bold), and the share of the smaller
# box two boxes may overlap before it is a warning.
DEFAULT_FONT_SIZE = 16.0
CHAR_WIDTH = 0.55
BOLD_CHAR_WIDTH = 0.6
MAX_OVERLAP = 0.25
# Top and bottom of the box, in font sizes from the y position, per
# dominant-baseline. The default is the alphabetic base line.
BASELINES = {
    "middle": (-0.5, 0.5),
    "central": (-0.5, 0.5),
    "hanging": (0.0, 1.0),
    "text-before-edge": (0.0, 1.0),
    "text-top": (0.0, 1.0),
    "text-after-edge": (-1.0, 0.0),
    "text-bottom": (-1.0, 0.0),
    "ideographic": (-1.0, 0.0),
}
ALPHABETIC = (-0.8, 0.2)
TRANSFORM = re.compile(r"\s*([a-zA-Z]+)\s*\(([^)]*)\)\s*,?")
# The arguments of a transform: numbers with their units, if any. A comma
# goes only between two of them; white space alone, or nothing (as in
# "10-20"), separates them too. Each separator can be read in only one way,
# so a long run of white space or commas does not backtrack.
FIRST_ARGUMENT = re.compile(rf"\s*({NUMBER})(%|[a-zA-Z]+)?")
NEXT_ARGUMENT = re.compile(rf"(?:\s*,\s*|\s*)({NUMBER})(%|[a-zA-Z]+)?")
# After a number with a unit ("10px20" is not valid) a comma or white space is needed.
AFTER_UNIT_ARGUMENT = re.compile(rf"(?:\s*,\s*|\s+)({NUMBER})(%|[a-zA-Z]+)?")
# The properties the estimate reads, from attributes, <style> rules or
# style= (the font shorthand gives font-size and font-weight).
STYLE_PROPERTIES = ("font-size", "font-weight", "text-anchor", "dominant-baseline", "transform", "display")
# Properties that change where, whether or how wide text is drawn in ways
# the estimate does not follow; a label with one of them set to a value
# that has an effect is skipped and counted. The first ones are also
# presentation attributes.
UNFOLLOWED_ATTRIBUTES = (
    "letter-spacing",
    "word-spacing",
    "writing-mode",
    "direction",
    "unicode-bidi",
    "alignment-baseline",
    "baseline-shift",
    "visibility",
    "font-stretch",
    "font-variant",
    "font-size-adjust",
    "white-space",
)
# The longhands of font-variant, and the other font properties that change
# the width of text; the font shorthand resets them all.
FONT_WIDTH = (
    "font-variant-caps",
    "font-variant-numeric",
    "font-variant-ligatures",
    "font-variant-east-asian",
    "font-variant-position",
    "font-variant-alternates",
    "font-kerning",
    "font-feature-settings",
    "font-variation-settings",
)
UNFOLLOWED = UNFOLLOWED_ATTRIBUTES + FONT_WIDTH + ("font-synthesis", "rotate", "scale", "translate", "text-transform")
# Per unfollowed property, the values that have no effect, its initial
# value first. For scale and translate each of up to three values counts.
NO_EFFECT = {
    "letter-spacing": ("normal", "0", "0px"),
    "word-spacing": ("normal", "0", "0px"),
    "writing-mode": ("horizontal-tb",),
    "direction": ("ltr",),
    "unicode-bidi": ("normal",),
    "alignment-baseline": ("auto", "baseline"),
    "baseline-shift": ("baseline", "0", "0px"),
    "visibility": ("visible",),
    "font-stretch": ("normal", "100%"),
    "font-variant": ("normal",),
    "font-size-adjust": ("none",),
    "white-space": ("normal", "nowrap"),
    "font-variant-caps": ("normal",),
    "font-variant-numeric": ("normal",),
    "font-variant-ligatures": ("normal",),
    "font-variant-east-asian": ("normal",),
    "font-variant-position": ("normal",),
    "font-variant-alternates": ("normal",),
    "font-kerning": ("auto",),
    "font-feature-settings": ("normal",),
    "font-variation-settings": ("normal",),
    "font-synthesis": ("weight style small-caps position", "weight style"),
    "rotate": ("none", "0deg", "0rad", "0grad", "0turn"),
    "scale": ("none", "1", "100%"),
    "translate": ("none", "0", "0px"),
    "text-transform": ("none",),
}
# Their values for initial (and unset, where they are not inherited).
INITIAL = {
    **{name: values[0] for name, values in NO_EFFECT.items()},
    "font-size": f"{DEFAULT_FONT_SIZE:g}px",
    "font-weight": "normal",
    "text-anchor": "start",
    "dominant-baseline": "auto",
    "transform": "none",
    "display": "inline",
}
# What the font shorthand sets besides its size, and to what when it does
# not give it: the width-changing font properties are reset to initial.
FONT_RESETS = ("font-weight", "font-stretch", "font-variant", "font-size-adjust") + FONT_WIDTH
# The positions of a label, which SVG 2 also takes as CSS properties. As
# attributes they are read; set from CSS, to any value, they are not followed.
POSITIONS = ("x", "y", "dx", "dy")
# The keywords the estimate follows, per property it reads; any other value
# (one that is not valid, or one such as dominant-baseline: mathematical) is
# not followed. A font-weight may also be a number from 1 to 1000.
KEYWORDS = {
    "text-anchor": {"start", "middle", "end"},
    "dominant-baseline": {"auto", "alphabetic"}.union(BASELINES),
    "font-weight": {"normal", "bold", "bolder", "lighter"},
}
INHERITED = {"font-size", "font-weight", "text-anchor", "dominant-baseline", "font-synthesis", "text-transform"}.union(
    UNFOLLOWED_ATTRIBUTES, FONT_WIDTH
) - {"unicode-bidi", "alignment-baseline", "baseline-shift"}
# What the all property sets: every property but direction and unicode-bidi
# (the positions, from CSS, are not followed anyway).
# all covers every property it resets, positions included (x, y, dx, dy are
# CSS properties too), except direction and unicode-bidi, as CSS says.
ALL = tuple(name for name in STYLE_PROPERTIES + UNFOLLOWED + POSITIONS if name not in ("direction", "unicode-bidi"))
# Words of the font shorthand before its size, and sizes that are keywords.
FONT_PREFIX = {
    "normal",
    "italic",
    "oblique",
    "small-caps",
    "ultra-condensed",
    "extra-condensed",
    "condensed",
    "semi-condensed",
    "semi-expanded",
    "expanded",
    "extra-expanded",
    "ultra-expanded",
}
FONT_SIZES = {
    "xx-small",
    "x-small",
    "small",
    "medium",
    "large",
    "x-large",
    "xx-large",
    "xxx-large",
    "larger",
    "smaller",
}
SYSTEM_FONTS = {"caption", "icon", "menu", "message-box", "small-caption", "status-bar"}
# The line height of the font shorthand: normal, a number, length or
# percentage that is not negative (written so that a long number does not
# backtrack), or one of the functions that may give one, in any case and
# also over several lines. What is inside a function is not type-checked:
# calc(1em + 2s) is taken as valid though browsers drop it, a deliberate
# limit (the line height does not change the estimate).
LENGTH_UNIT = r"(?:r?(?:em|ex|cap|ch|ic|lh)|[sld]?v(?:w|h|i|b|min|max)|cq(?:w|h|i|b|min|max)|cm|mm|q|in|pt|pc|px)"
UNSIGNED = r"\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?"
LINE_HEIGHT = re.compile(
    rf"normal|{UNSIGNED}(?:%|{LENGTH_UNIT})?|(?:calc|min|max|clamp|round|mod|rem|abs|sign|var|env)\(.*\)",
    re.DOTALL | re.IGNORECASE,
)
# Functions with a fixed number of arguments (min, max or None for no limit).
# asin, acos, atan and atan2 give an angle, which a line height cannot be.
ARGUMENT_COUNTS = {
    "pow": (2, 2),
    "sqrt": (1, 1),
    "exp": (1, 1),
    "log": (1, 2),
    "hypot": (1, None),
    "sin": (1, 1),
    "cos": (1, 1),
    "tan": (1, 1),
}
COUNTED_FUNCTION = re.compile(r"(pow|sqrt|exp|log|hypot|sin|cos|tan)\((.*)\)", re.DOTALL | re.IGNORECASE)
# A negative font size is not valid; browsers drop the declaration. -0 (also
# -0.0, -.0, -0px, -0%) is a valid size of 0, so it does not count.
NEGATIVE_ZERO = re.compile(rf"-(?:0+(?:\.0*)?|\.0+)(?:e[+-]?[0-9]+)?(?:%|{LENGTH_UNIT})?", re.IGNORECASE)


def _negative_size(value: str) -> bool:
    """Whether a font size is negative, and not a zero such as -0."""
    value = value.strip()
    return bool(re.match(r"-[0-9.]", value)) and not NEGATIVE_ZERO.fullmatch(value)


def _line_height(token: str) -> bool:
    """Whether a token is a valid line height of the font shorthand."""
    if LINE_HEIGHT.fullmatch(token):
        return True
    counted = COUNTED_FUNCTION.fullmatch(token)
    if not counted:
        return False
    # Count the arguments at the top level; an empty one is not valid.
    arguments, depth, current = [], 0, ""
    for char in counted.group(2):
        if char == "," and depth == 0:
            arguments.append(current)
            current = ""
            continue
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return False
        current += char
    arguments.append(current)
    low, high = ARGUMENT_COUNTS[counted.group(1).lower()]
    count = len(arguments)
    return depth == 0 and all(a.strip() for a in arguments) and count >= low and (high is None or count <= high)
# One name of the font family list: a quoted string (blanked by _opaque),
# or one or more identifiers, which do not start with a digit. A CSS-wide
# keyword alone (inherit, initial, ...) is not a family name.
IDENTIFIER = r"(?:-?(?:[a-z_\u0080-\U0010ffff]|\\.)|--)(?:[\w\-\u0080-\U0010ffff]|\\.)*"
FAMILY = re.compile(rf"\"[^\"]*\"|'[^']*'|{IDENTIFIER}(?:\s+{IDENTIFIER})*")
CSS_WIDE = {"inherit", "initial", "unset", "revert", "revert-layer"}
# Comments, strings and url(...) in CSS, whose braces and semicolons do not count.
CSS_OPAQUE = re.compile(
    r"/\*.*?(?:\*/|$)|\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?|url\([^)\"']*",
    re.DOTALL | re.IGNORECASE,
)
# At-rules whose blocks hold no rules for elements (frames, font faces, ...).
NO_ELEMENT_RULES = re.compile(
    r"@(?:-[a-z]+-)?(?:keyframes|font-face|font-feature-values|page|counter-style)\b",
    re.IGNORECASE,
)
# The media of a <style> that hold on a screen.
SCREEN_MEDIA = {"", "all", "screen"}
# The types of a <style> whose rules are read. The match is exact (case,
# parameters and white space count), so a type that a browser may not apply,
# such as TEXT/CSS or text/css with parameters, errs toward counting.
CSS_TYPES = {"", "text/css"}
# Children of a <text> whose content is not drawn.
NO_TEXT = {"title", "desc", "metadata"}
# Why a label was not checked for overlap, as the note line says it.
SKIPPED = {
    "css": (
        "with CSS the estimate does not follow "
        "(var(), revert, a value it does not know, letter-spacing, font-stretch, writing-mode, visibility, ...)"
    ),
    "css-transform": "with a CSS transform",
    "layout": "with textLength or rotate",
    "nested-svg": "inside a nested <svg>",
    "style": "styled by <style> rules that are not read",
    "textPath": "on a <textPath>",
    "transform": "with a rotate, scale, matrix or skew transform",
    "units": "with a position or font size that is not a plain length",
}


def _local(tag: str) -> str:
    """Return the tag name without its XML namespace."""
    return tag.split("}", 1)[-1]


def _number(value: str | None) -> float | None:
    """Read a length such as "720", "-20", ".5", "1e3" or "720px"; None if it is not one."""
    if value is None:
        return None
    match = re.fullmatch(rf"\s*({NUMBER})\s*(?:px)?\s*", value)
    return float(match.group(1)) if match else None


def _view_box(root: ET.Element) -> tuple[float, float, float, float] | None:
    """Return the viewBox as (min_x, min_y, width, height), or None."""
    view_box = root.get("viewBox")
    if not view_box:
        return None
    # Exactly four numbers, separated by white space and/or one comma; no units.
    separator = r"(?:\s*,\s*|\s+)"
    if not re.fullmatch(rf"\s*{NUMBER}(?:{separator}{NUMBER}){{3}}\s*", view_box):
        return None
    return tuple(float(part) for part in re.findall(NUMBER, view_box))


def _covers_picture(rect: ET.Element, view_box: tuple[float, float, float, float] | None) -> bool:
    """Whether a <rect> is filled and covers the whole viewBox, offset included."""
    if rect.get("fill") in (None, "none", "transparent"):
        return False
    if rect.get("width") == "100%" and rect.get("height") == "100%":
        return _number(rect.get("x") or "0") == 0 and _number(rect.get("y") or "0") == 0
    if view_box is None:
        return False
    x, y = _number(rect.get("x") or "0"), _number(rect.get("y") or "0")
    w, h = _number(rect.get("width")), _number(rect.get("height"))
    if None in (x, y, w, h):
        return False
    min_x, min_y, width, height = view_box
    return x <= min_x and y <= min_y and x + w >= min_x + width and y + h >= min_y + height


def _unescape_css(css: str) -> str:
    """Decode CSS escapes (a hex escape for a letter, or a backslash before a character).

    So an escape cannot hide a url( or an @import.
    """

    def decode(match: re.Match) -> str:
        if match.group(1) is not None:
            code = int(match.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF else "\ufffd"
        return match.group(2)

    return CSS_ESCAPE.sub(decode, css)


def _outside_urls(css: str) -> list[str]:
    """Return the url(...) targets in CSS text that point outside the file."""
    return [target for target in URL_IN_CSS.findall(_unescape_css(css)) if not target.strip().startswith("#")]


def _conditional_switch(el: ET.Element) -> bool:
    """Whether a <switch> has a child with systemLanguage, requiredExtensions or requiredFeatures.

    Which child is shown then depends on the viewer, so it cannot be checked.
    """
    return _local(el.tag) == "switch" and any(a in child.attrib for child in el for a in CONDITIONS)


def _painted(root: ET.Element) -> list[ET.Element]:
    """Return the elements that paint something, in paint order.

    Containers (g, a) and descriptions are left out, and so is everything
    inside a template (defs, symbol, clipPath, ...), which is painted only
    where it is used. Of a <switch> without conditions only the first child
    counts; of one with conditions none does (see _conditional_switch).
    """
    painted = []

    def walk(el: ET.Element) -> None:
        name = _local(el.tag)
        if name in TEMPLATES:
            return
        if name not in NOT_DRAWN:
            painted.append(el)
        children = list(el)
        if name == "switch":
            # With conditions the shown child depends on the viewer, so none counts.
            children = [] if _conditional_switch(el) else children[:1]
        for child in children:
            walk(child)

    walk(root)
    return painted


def check(svg_text: str) -> list[str]:
    """Return the problems found in one SVG document; empty if none."""
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as error:
        return [f"not well-formed XML: {error}"]
    if _local(root.tag) != "svg":
        return [f"the root element is <{_local(root.tag)}>, not <svg>"]

    problems = []
    view_box = _view_box(root)
    width = _number(root.get("width"))
    if view_box is None:
        problems.append("no valid viewBox on <svg>")
    if width is None:
        problems.append("no width= on <svg>: set width, height and viewBox")
    elif width > MAX_WIDTH:
        problems.append(f"width {width:g} px is over {MAX_WIDTH} px")
    if _number(root.get("height")) is None:
        problems.append("no height= on <svg>: set width, height and viewBox")

    elements = list(root.iter())
    tags = [_local(el.tag) for el in elements]
    for tag in sorted(FORBIDDEN_TAGS.intersection(tags)):
        problems.append(f"<{tag}> is not allowed (one self-contained file, text as text)")

    for el in elements:
        name = _local(el.tag)
        for attr in ("href", XLINK_HREF):
            href = el.get(attr)
            if href and not href.startswith("#"):
                problems.append(f"external reference {href!r} in <{name}>")
        if name == "style" and el.text:
            if CSS_LOADS.search(_unescape_css(el.text)):
                problems.append("the <style> loads something from outside (@import or @font-face)")
            for target in _outside_urls(el.text):
                problems.append(f"the <style> loads url({target}) from outside the file")
        for attr, value in el.attrib.items():
            for target in _outside_urls(value):
                problems.append(f"{_local(attr)}= in <{name}> loads url({target}) from outside the file")

    if any(_conditional_switch(el) for el in elements):
        problems.append(
            "a <switch> with conditional children cannot be checked; "
            "draw the background card and the labels outside it"
        )

    if "text" not in tags:
        problems.append("no <text>: labels must be text, not paths")
    if "title" not in tags:
        problems.append("no <title> with the message")
    if "desc" not in tags:
        problems.append("no <desc> with the message and the numbers")

    painted = _painted(root)
    card = next((i for i, el in enumerate(painted) if _local(el.tag) == "rect" and _covers_picture(el, view_box)), None)
    if card is None:
        problems.append("no filled background card over the whole viewBox (needed for dark pages)")
    elif card > 0:
        hidden = _local(painted[0].tag)
        problems.append(f"the background card is drawn after <{hidden}> and hides it; draw the card first")
    return problems


Styles = dict[ET.Element, dict[str, str]]
Declarations = dict[str, tuple[str, bool]]


def _opaque(css: str) -> str:
    """Blank out comments and what is inside strings and url(...), so their braces and semicolons do not count.

    What the estimate reads (sizes, weights, keywords) is never inside them;
    a quoted font family stays a word.
    """

    def blank(match: re.Match) -> str:
        text = match.group()
        if text.startswith("/*"):
            return " "
        return "url(x" if text[0] not in "\"'" else f"{text[0]}x{text[0]}"

    return CSS_OPAQUE.sub(blank, css)


def _declarations(block: str) -> Declarations:
    """Read the properties the estimate uses from a declaration block (style= or a rule).

    Returns per property its value, in lower case, and whether it is
    !important. An !important declaration wins over a normal one; otherwise
    the later one wins. The font shorthand gives font-size, font-weight and
    the font properties it resets (see _font_shorthand); font-variant resets
    its longhands; all with a CSS-wide keyword or a var() gives that value
    to every property it sets (see ALL), and with anything else is not valid.
    """
    properties: Declarations = {}
    for part in _opaque(block).split(";"):
        key, colon, value = part.partition(":")
        key, value = key.strip().lower(), value.strip().lower()
        plain = re.sub(r"!\s*important\s*$", "", value).strip()
        if not colon or not plain:
            continue
        important = plain != value
        if key == "font":
            found = _font_shorthand(plain)
        elif key == "all":
            found = dict.fromkeys(ALL, plain) if plain in CSS_WIDE or "var(" in plain else {}
        elif key == "font-variant":
            # A shorthand passes a CSS-wide keyword on to its longhands.
            found = {**dict.fromkeys(FONT_WIDTH[:6], plain if plain in CSS_WIDE else "initial"), key: plain}
        elif key == "font-size" and _negative_size(plain):
            # A negative size is not valid; the earlier value holds.
            continue
        elif key in STYLE_PROPERTIES or key in UNFOLLOWED or key in POSITIONS:
            found = {key: plain}
        else:
            continue
        for name, found_value in found.items():
            if important or not properties.get(name, ("", False))[1]:
                properties[name] = (found_value, important)
    return properties


def _font_shorthand(value: str) -> dict[str, str]:
    """Read a font shorthand such as "bold 60px/1.2 sans-serif".

    Gives font-size and the properties of FONT_RESETS, which the shorthand
    sets as well. A weight is a keyword or a number from 1 to 1000; a
    weight, stretch or variant that is not given is normal, as in CSS, and
    the other width-changing font properties (font-size-adjust,
    font-kerning, font-feature-settings, ...) are reset to their initial
    values. A shorthand without a size or without a valid family list, or
    with a line height that is not valid, is not valid and gives nothing,
    as browsers drop it. A CSS-wide keyword or a var() gives its whole value
    to all of them. A system font (such as caption) gives its name as size
    and weight, which is then not a plain length, and resets the others.
    """
    if value in CSS_WIDE or "var(" in value:
        return dict.fromkeys(("font-size",) + FONT_RESETS, value)
    found = dict.fromkeys(FONT_RESETS, "initial")
    if value in SYSTEM_FONTS:
        return {**found, "font-size": value, "font-weight": value}
    found["font-weight"] = "normal"
    tokens = _font_tokens(value)
    for i, token in enumerate(tokens):
        number = float(token) if re.fullmatch(NUMBER, token) else None
        if token in ("bold", "bolder", "lighter") or (number is not None and 1 <= number <= 1000):
            found["font-weight"] = token
        elif number:
            # A number that is neither a weight nor 0 is not a size either.
            return {}
        elif token.endswith(("condensed", "expanded")) and token in FONT_PREFIX:
            found["font-stretch"] = token
        elif token == "small-caps":
            found["font-variant"] = token
        elif token in FONT_PREFIX or re.fullmatch(rf"{NUMBER}(?:deg|grad|rad|turn)", token):
            continue
        elif re.match(r"[+-]?[0-9.]", token) or token in FONT_SIZES or token.startswith("calc("):
            if _negative_size(token):
                # A negative size is not valid (-0 is).
                return {}
            family = tokens[i + 1 :]
            if family[:1] == ["/"]:
                if not _line_height(family[1] if len(family) > 1 else ""):
                    return {}
                family = family[2:]
            names = " ".join(family).split(",")
            valid = family and all(FAMILY.fullmatch(name.strip()) and name.strip() not in CSS_WIDE for name in names)
            return {"font-size": token, **found} if valid else {}
        else:
            return {}
    return {}


def _font_tokens(value: str) -> list[str]:
    """Split a font shorthand at white space and at "/", outside parentheses, so calc(1em + 2px) stays one token."""
    tokens, current, depth = [], "", 0
    for char in value:
        if depth == 0 and (char.isspace() or char == "/"):
            tokens += [current] if current else []
            tokens += [char] if char == "/" else []
            current = ""
            continue
        depth = max(0, depth + (char == "(") - (char == ")"))
        current += char
    return tokens + ([current] if current else [])


def _unknown(value: str) -> bool:
    """Whether a value is one the cascade does not resolve: revert, revert-layer or a var()."""
    return value in ("revert", "revert-layer") or "var(" in value


def _no_effect(name: str, value: str) -> bool:
    """Whether a value of an unfollowed property has no effect (see NO_EFFECT), or is inherited."""
    value = " ".join(value.split())
    if value == "inherit" or value in NO_EFFECT[name]:
        return True
    # scale and translate take up to three values, one per axis.
    parts = value.split()
    return name in ("scale", "translate") and len(parts) <= 3 and set(parts) <= set(NO_EFFECT[name]) - {"none"}


def _followed(name: str, value: str) -> bool:
    """Whether the estimate follows a value of a keyword property it reads (see KEYWORDS)."""
    if name not in KEYWORDS or value == "inherit" or value in KEYWORDS[name]:
        return True
    return name == "font-weight" and bool(re.fullmatch(NUMBER, value)) and 1 <= float(value) <= 1000


def _style_rules(css: str) -> list[tuple[str, str, bool]]:
    """Split CSS into rules, as (selectors, declarations, readable).

    Rules inside @media, @supports, @layer and other at-rules, and rules
    nested in a rule, are not readable: whether and in which order they
    hold is not followed. At-rules such as @keyframes and @font-face style
    no element; what is inside them is left out. One pass, without
    recursion, so any depth of nesting can be read.
    """
    css = _opaque(css)
    rules = []
    # The open blocks, innermost last, as [kind, prelude, body pieces, start
    # of the current piece]. A kind is "rule", "group" (an at-rule with
    # rules inside) or "skip" (an at-rule without rules for elements).
    blocks: list[list] = []
    statement = 0

    def close(end: int) -> None:
        kind, prelude, pieces, start = blocks.pop()
        if kind == "rule":
            rules.append((prelude, "".join(pieces) + css[start:end], not blocks))
        if blocks and blocks[-1][0] == "rule":
            blocks[-1][3] = end + 1

    for i, char in enumerate(css):
        if char == ";":
            statement = i + 1
        elif char == "{":
            prelude = css[statement:i].strip()
            if any(block[0] == "skip" for block in blocks) or NO_ELEMENT_RULES.match(prelude):
                kind = "skip"
            else:
                kind = "group" if prelude.startswith("@") else "rule"
            if blocks and blocks[-1][0] == "rule":
                # A nested rule is not part of the declarations around it.
                blocks[-1][2].append(css[blocks[-1][3] : statement])
            blocks.append([kind, prelude, [], i + 1])
            statement = i + 1
        elif char == "}":
            if blocks:
                close(i)
            statement = i + 1
    # Blocks still open at the end close there, as in CSS.
    while blocks:
        close(len(css))
    return rules


def _compound(selector: str) -> tuple[str | None, set[str], set[str]] | None:
    """Read a selector made of an element name, classes and ids, such as "text.title" or "#total".

    Returns (element name or None, classes, ids), or None for any other
    selector (combinators, pseudo-classes, attribute selectors, ...).
    """
    match = re.fullmatch(r"\s*(\*|[A-Za-z][\w-]*)?((?:[.#][A-Za-z_-][\w-]*)*)\s*", selector)
    if not match or not (match.group(1) or match.group(2)):
        return None
    tag = None if match.group(1) in (None, "*") else match.group(1)
    parts = re.findall(r"([.#])([\w-]+)", match.group(2))
    return (
        tag,
        {name for kind, name in parts if kind == "."},
        {name for kind, name in parts if kind == "#"},
    )


def _specificity(selector: str, compound: tuple[str | None, set[str], set[str]]) -> tuple[int, int, int]:
    """Return the specificity of a compound selector: ids, classes, element name.

    Every id and class counts, also a repeated one (".big.big" is more
    specific than ".big").
    """
    return selector.count("#"), selector.count("."), 0 if compound[0] is None else 1


def _subject(selector: str) -> tuple[str | None, set[str], set[str]]:
    """Return what an element must have to be matched by a selector that is not read.

    Only the last compound counts (the element the rule styles), without
    its pseudo-classes and attribute selectors; if nothing is left, any
    element may be matched.
    """
    plain = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", selector)
    plain = re.sub(r":{1,2}[\w-]*", "", plain)
    last = re.split(r"\s*[>+~]\s*|\s+", plain.strip())[-1]
    return _compound(last) or (None, set(), set())


def _matches(el: ET.Element, compound: tuple[str | None, set[str], set[str]]) -> bool:
    """Whether an element has the element name, classes and ids of a compound selector."""
    tag, classes, ids = compound
    if tag is not None and _local(el.tag) != tag:
        return False
    return classes <= set((el.get("class") or "").split()) and ids <= {el.get("id")}


def _cascade(
    root: ET.Element,
) -> tuple[Styles, dict[ET.Element, set[str]]]:
    """Find the properties the estimate uses for every element, and why some cannot be followed.

    As in CSS for SVG: presentation attributes count least, then <style>
    rules (by specificity: ids, then classes, then the element name; at
    equal specificity the later rule wins), then style=; !important
    declarations, in rules and then in style=, win over all of these.
    Keywords are read in lower case; initial gives the initial value, and
    unset inherits where the property is inherited. Returns the properties
    per element, and per element a set of reasons not to estimate it:
    "style" when a rule that is not read may match it, "css-transform" when
    a CSS transform other than none is set on it, "css" when a value or a
    property the estimate does not follow (var(), revert, a keyword it does
    not know, letter-spacing, font-stretch, x from CSS, ...) is set on it.
    """
    rules, unread = [], []
    for style in root.iter():
        if _local(style.tag) != "style" or not style.text:
            continue
        # A stylesheet for media other than the screen is not followed, and
        # one in a language other than CSS may be ignored by browsers.
        active = (style.get("media") or "").strip().lower() in SCREEN_MEDIA and style.get("type", "") in CSS_TYPES
        for selectors, body, readable in _style_rules(style.text):
            properties = _declarations(body)
            if not properties:
                continue
            for selector in selectors.split(","):
                compound = _compound(selector)
                if active and readable and compound is not None:
                    rules.append((_specificity(selector, compound), len(rules), compound, properties))
                else:
                    unread.append(_subject(selector))
    rules.sort(key=lambda rule: rule[:2])

    styles, reasons = {}, {}
    for el in root.iter():
        normal, important = {}, {}
        for _, _, compound, properties in rules:
            if _matches(el, compound):
                for name, (value, is_important) in properties.items():
                    (important if is_important else normal)[name] = value
        for name, (value, is_important) in _declarations(el.get("style") or "").items():
            (important if is_important else normal)[name] = value
        css = {**normal, **important}
        own = {
            name: el.get(name).strip().lower()
            for name in STYLE_PROPERTIES + UNFOLLOWED_ATTRIBUTES
            # A negative font-size= is not valid either, and is left out.
            if el.get(name) is not None and not (name == "font-size" and _negative_size(el.get(name)))
        }
        own.update(css)
        reasons[el] = set()
        for name, value in own.items():
            if value == "initial" or (value == "unset" and name not in INHERITED):
                own[name] = INITIAL.get(name, "normal")
            elif value == "unset":
                own[name] = "inherit"
            elif _unknown(value) or (value == "inherit" and name == "transform"):
                reasons[el].add("css")
            if (name in UNFOLLOWED and not _no_effect(name, own[name])) or not _followed(name, own[name]):
                reasons[el].add("css")
            # x, y, dx and dy from CSS move the characters of a text or tspan.
            if name in POSITIONS and name in css and _local(el.tag) in ("text", "tspan"):
                reasons[el].add("css")
        styles[el] = own
        if any(_matches(el, subject) for subject in unread):
            reasons[el].add("style")
        # A var() or revert (as from all) is a value not followed, not a transform.
        if "transform" in css and own["transform"] != "none" and not _unknown(css["transform"]):
            reasons[el].add("css-transform")
    return styles, reasons


def _hidden(el: ET.Element, styles: Styles) -> bool:
    """Whether an element has display none."""
    return (styles[el].get("display") or "").strip() == "none"


def _drawn(el: ET.Element, styles: Styles) -> list[ET.Element]:
    """Return el and the elements inside it that draw text.

    <title>, <desc> and <metadata> draw nothing, and an element with
    display none draws nothing, nor does anything inside it.
    """
    drawn = [el]
    for child in el:
        if _local(child.tag) not in NO_TEXT and not _hidden(child, styles):
            drawn += _drawn(child, styles)
    return drawn


def _drawn_text(el: ET.Element, styles: Styles) -> str:
    """Return the text an element draws: its own and its drawn children's, with all tails."""
    parts = [el.text or ""]
    for child in el:
        if _local(child.tag) not in NO_TEXT and not _hidden(child, styles):
            parts.append(_drawn_text(child, styles))
        parts.append(child.tail or "")
    return "".join(parts)


def _inherited(chain: list[ET.Element], name: str, styles: Styles) -> str | None:
    """Return a property from the nearest element in chain (innermost last) that sets it."""
    for el in reversed(chain):
        value = styles[el].get(name)
        if value is not None and value != "inherit":
            return value
    return None


def _font_size(chain: list[ET.Element], styles: Styles) -> float | None:
    """Return the font size in px, inherited, or None if it is not a plain length."""
    value = _inherited(chain, "font-size", styles)
    return DEFAULT_FONT_SIZE if value is None else _number(value)


def _first(value: str | None) -> float | None:
    """Return the first number of a coordinate list such as "10 20 30", or None."""
    if value is None:
        return None
    parts = re.split(r"[\s,]+", value.strip())
    return _number(parts[0]) if parts and parts[0] else None


def _length(value: str | None, font_size: float) -> float | None:
    """Read a length that may be in em, such as dy="1.2em"; None if it is not one."""
    if value is not None and value.strip().endswith("em"):
        number = _number(value.strip()[:-2])
        return None if number is None else number * font_size
    return _first(value)


def _arguments(text: str) -> list[tuple[str, str]] | None:
    """Read the arguments of a transform as (number, unit); None if they are not valid.

    Read left to right, each from where the one before ends; three are
    enough to tell that a translate has too many.
    """
    found, end = [], 0
    while len(found) < 3:
        pattern = FIRST_ARGUMENT if not found else AFTER_UNIT_ARGUMENT if found[-1][1] else NEXT_ARGUMENT
        argument = pattern.match(text, end)
        if argument is None:
            break
        found.append(argument.groups(""))
        end = argument.end()
    return found if found and not text[end:].strip() else None


def _translation(chain: list[ET.Element], styles: Styles) -> tuple[float, float] | str:
    """Add up the translate(...) of the chain.

    Returns the shift, or why it cannot be followed, as a key of SKIPPED:
    "transform" if any other transform is there, "units" if a translate
    has a unit other than px (such as % or em).
    """
    dx = dy = 0.0
    for el in chain:
        value = (styles[el].get("transform") or "").strip()
        if not value or value == "none":
            continue
        position = 0
        for match in TRANSFORM.finditer(value):
            if match.start() != position or match.group(1) != "translate":
                return "transform"
            found = _arguments(match.group(2))
            if found is None or len(found) not in (1, 2):
                return "transform"
            if any(unit.lower() not in ("", "px") for _, unit in found):
                return "units"
            numbers = [float(number) for number, _ in found]
            dx += numbers[0]
            dy += numbers[1] if len(numbers) == 2 else 0.0
            position = match.end()
        if position != len(value):
            return "transform"
    return dx, dy


def _width(label: str, chain: list[ET.Element], styles: Styles) -> float | None:
    """Estimate the width of a piece of text in the font of chain; None if the size is not a plain length."""
    size = _font_size(chain, styles)
    if size is None:
        return None
    weight = _inherited(chain, "font-weight", styles) or "normal"
    bold = weight in ("bold", "bolder") or (_number(weight) or 0) >= 600
    return len(label) * size * (BOLD_CHAR_WIDTH if bold else CHAR_WIDTH)


Box = tuple[float, float, float, float]


def _chunks(text: ET.Element, chain: list[ET.Element], styles: Styles) -> list[tuple[str, list[Box]]] | None:
    """Split a <text> into chunks, each as (its text, the boxes of its pieces).

    As in SVG, a current text position is kept: x and y on the <text> or a
    <tspan> set it, dx and dy move it, and each piece of text moves it on by
    its estimated width, in its own font. A new chunk starts at every
    absolute x or y; text-anchor moves the whole chunk. Children that draw
    nothing (see _drawn) are left out, but the text after them is not.
    Returns None if a position or font size cannot be read.
    """
    position = [0.0, 0.0]
    chunks: list[dict] = []

    def move(el: ET.Element, el_chain: list[ET.Element]) -> bool:
        # x, y, dx and dy belong to an element's characters: one without
        # any text neither moves the position nor starts a chunk.
        if el is not text and not _drawn_text(el, styles).strip():
            return True
        size = _font_size(el_chain, styles)
        if size is None:
            return False
        if el is text or "x" in el.attrib or "y" in el.attrib:
            chunks.append({"chain": el_chain, "pieces": []})
        for i, name in enumerate(("x", "y")):
            if name in el.attrib:
                value = _first(el.get(name))
                if value is None:
                    return False
                position[i] = value
        for i, name in enumerate(("dx", "dy")):
            if name in el.attrib:
                value = _length(el.get(name), size)
                if value is None:
                    return False
                position[i] += value
        return True

    def add(label: str | None, el_chain: list[ET.Element]) -> bool:
        label = re.sub(r"\s+", " ", label or "")
        if not chunks[-1]["pieces"]:
            label = label.lstrip()
        if not label:
            return True
        width = _width(label, el_chain, styles)
        if width is None:
            return False
        chunks[-1]["pieces"].append([label, position[0], position[1], el_chain, width])
        position[0] += width
        return True

    def walk(el: ET.Element, el_chain: list[ET.Element]) -> bool:
        if not move(el, el_chain) or not add(el.text, el_chain):
            return False
        for child in el:
            drawn = _local(child.tag) not in NO_TEXT and not _hidden(child, styles)
            if (drawn and not walk(child, el_chain + [child])) or not add(child.tail, el_chain):
                return False
        return True

    if not walk(text, chain):
        return None
    result = []
    for chunk in chunks:
        pieces = chunk["pieces"]
        if not pieces:
            continue
        last = pieces[-1]
        last[0] = last[0].rstrip()
        last[4] = _width(last[0], last[3], styles) or 0.0
        start, end = pieces[0][1], last[1] + last[4]
        # As in SVG 2, the anchor of a chunk is the one of its first character.
        anchor = _inherited(pieces[0][3], "text-anchor", styles) or "start"
        shift = -(end - start) / 2 if anchor == "middle" else -(end - start) if anchor == "end" else 0.0
        boxes = []
        for label, x, y, el_chain, width in pieces:
            if not label:
                continue
            size = _font_size(el_chain, styles) or DEFAULT_FONT_SIZE
            top, bottom = BASELINES.get(_inherited(el_chain, "dominant-baseline", styles) or "", ALPHABETIC)
            boxes.append((x + shift, y + top * size, x + shift + width, y + bottom * size))
        result.append(("".join(piece[0] for piece in pieces), boxes))
    return result


def _short(label: str, limit: int = 30) -> str:
    """Shorten a label for a message."""
    return label if len(label) <= limit else label[: limit - 3] + "..."


def _not_estimated(
    chain: list[ET.Element],
    drawn: list[ET.Element],
    styles: Styles,
    reasons: dict[ET.Element, set[str]],
) -> str | None:
    """Tell why a label is laid out in a way the estimate does not follow; None if it is not.

    chain is the <text> with its parents, drawn the <text> with the
    elements inside it that draw text. The answer is a key of SKIPPED.
    """
    elements = chain + drawn[1:]
    if any(_local(el.tag) == "svg" for el in chain[1:]):
        return "nested-svg"
    if any("style" in reasons[el] for el in elements):
        return "style"
    if any(_local(el.tag) == "textPath" for el in drawn):
        return "textPath"
    if any("css-transform" in reasons[el] for el in elements):
        return "css-transform"
    if any("css" in reasons[el] for el in elements):
        return "css"
    if any("textLength" in el.attrib or "rotate" in el.attrib for el in drawn):
        return "layout"
    # A transform on a <tspan> (other than none) is not followed either.
    if any((styles[el].get("transform") or "none").strip() != "none" for el in drawn[1:]):
        return "transform"
    return None


def overlap_report(svg_text: str) -> tuple[list[str], dict[str, int]]:
    """Return the warnings about overlapping labels, and how many labels were not checked, per reason.

    The reasons are the keys of SKIPPED. A <text> that is not drawn
    (display none on it or on a parent) is neither checked nor counted.
    Returns ([], {}) if the file cannot be read.
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return [], {}
    styles, reasons = _cascade(root)
    parents = {child: parent for parent in root.iter() for child in parent}
    boxes, skipped = [], {}
    for el in _painted(root):
        if _local(el.tag) != "text":
            continue
        chain = [el]
        while chain[0] in parents:
            chain.insert(0, parents[chain[0]])
        if any(_hidden(link, styles) for link in chain):
            continue
        reason = _not_estimated(chain, _drawn(el, styles), styles, reasons)
        shift = chunks = None
        if reason is None:
            shift = _translation(chain, styles)
            reason = shift if isinstance(shift, str) else None
        if reason is None:
            chunks = _chunks(el, chain, styles)
            reason = "units" if chunks is None else None
        if reason is not None:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        for label, chunk_boxes in chunks:
            chunk = len(boxes)
            for box in chunk_boxes:
                moved = (
                    box[0] + shift[0],
                    box[1] + shift[1],
                    box[2] + shift[0],
                    box[3] + shift[1],
                )
                boxes.append((label, moved, chunk))

    # Overlap is judged per pair of whole labels (chunks): the overlapping
    # areas of their pieces are added up and compared with the smaller label.
    labels: dict[int, str] = {}
    areas: dict[int, float] = {}
    for label, box, chunk in boxes:
        labels[chunk] = label
        areas[chunk] = areas.get(chunk, 0.0) + (box[2] - box[0]) * (box[3] - box[1])
    shared: dict[tuple[int, int], float] = {}
    for i, (_, a, chunk_a) in enumerate(boxes):
        for _, b, chunk_b in boxes[i + 1 :]:
            # Pieces of one chunk touch each other; that is not an overlap.
            if chunk_a == chunk_b:
                continue
            width = min(a[2], b[2]) - max(a[0], b[0])
            height = min(a[3], b[3]) - max(a[1], b[1])
            if width > 0 and height > 0:
                pair = (min(chunk_a, chunk_b), max(chunk_a, chunk_b))
                shared[pair] = shared.get(pair, 0.0) + width * height
    warnings = []
    for (chunk_a, chunk_b), area in sorted(shared.items()):
        if area > MAX_OVERLAP * min(areas[chunk_a], areas[chunk_b]):
            warnings.append(f"labels overlap: {_short(labels[chunk_a])!r} and {_short(labels[chunk_b])!r}")
    return warnings, skipped


def overlaps(svg_text: str) -> tuple[list[str], int]:
    """Return the warnings about overlapping labels, and how many labels were not checked.

    The boxes are estimates (see the constants above). Labels the estimate
    does not follow (see SKIPPED) are not checked but counted. Returns
    ([], 0) if the file cannot be read.
    """
    warnings, skipped = overlap_report(svg_text)
    return warnings, sum(skipped.values())


def main(args: list[str]) -> int:
    """Check each file; print the problems and warnings; return the exit status."""
    strict = "--strict" in args
    paths = [arg for arg in args if arg != "--strict"]
    if not paths:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    status = 0
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            svg_text = handle.read()
        problems = check(svg_text)
        warnings, skipped = overlap_report(svg_text)
        for problem in problems:
            print(f"{path}: {problem}")
        for warning in warnings:
            print(f"{path}: warning: {warning}")
        if skipped:
            kinds = ", ".join(f"{count} {SKIPPED[reason]}" for reason, count in sorted(skipped.items()))
            print(f"{path}: note: {sum(skipped.values())} label(s) not checked for overlap: {kinds}")
        if problems or (strict and warnings):
            status = 1
        elif not warnings:
            print(f"{path}: ok")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
