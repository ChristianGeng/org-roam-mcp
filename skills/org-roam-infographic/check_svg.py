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


def _style(el: ET.Element, name: str) -> str | None:
    """Return a presentation property of one element, from style= or the attribute."""
    for part in (el.get("style") or "").split(";"):
        key, _, value = part.partition(":")
        if key.strip() == name and value.strip():
            return value.strip()
    return el.get(name)


def _inherited(chain: list[ET.Element], name: str) -> str | None:
    """Return a property from the nearest element in chain (innermost last) that sets it."""
    for el in reversed(chain):
        value = _style(el, name)
        if value is not None and value != "inherit":
            return value
    return None


def _font_size(chain: list[ET.Element]) -> float | None:
    """Return the font size in px, inherited, or None if it is not a plain length."""
    value = _inherited(chain, "font-size")
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


def _translation(chain: list[ET.Element]) -> tuple[float, float] | None:
    """Add up the translate(...) of the chain; None if any other transform is there."""
    dx = dy = 0.0
    for el in chain:
        value = el.get("transform")
        if not value:
            continue
        position = 0
        for match in TRANSFORM.finditer(value):
            if match.start() != position or match.group(1) != "translate":
                return None
            numbers = [float(n) for n in re.findall(NUMBER, match.group(2))]
            if len(numbers) not in (1, 2):
                return None
            dx += numbers[0]
            dy += numbers[1] if len(numbers) == 2 else 0.0
            position = match.end()
        if position != len(value):
            return None
    return dx, dy


def _width(label: str, chain: list[ET.Element]) -> float | None:
    """Estimate the width of a piece of text in the font of chain; None if the size is not a plain length."""
    size = _font_size(chain)
    if size is None:
        return None
    weight = _inherited(chain, "font-weight") or "normal"
    bold = weight in ("bold", "bolder") or (weight.isdigit() and int(weight) >= 600)
    return len(label) * size * (BOLD_CHAR_WIDTH if bold else CHAR_WIDTH)


Box = tuple[float, float, float, float]


def _chunks(text: ET.Element, chain: list[ET.Element]) -> list[tuple[str, list[Box]]] | None:
    """Split a <text> into chunks, each as (its text, the boxes of its pieces).

    As in SVG, a current text position is kept: x and y on the <text> or a
    <tspan> set it, dx and dy move it, and each piece of text moves it on by
    its estimated width, in its own font. A new chunk starts at every
    absolute x or y; text-anchor moves the whole chunk. Returns None if a
    position or font size cannot be read.
    """
    position = [0.0, 0.0]
    chunks: list[dict] = []

    def move(el: ET.Element, el_chain: list[ET.Element]) -> bool:
        size = _font_size(el_chain)
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
        width = _width(label, el_chain)
        if width is None:
            return False
        chunks[-1]["pieces"].append([label, position[0], position[1], el_chain, width])
        position[0] += width
        return True

    def walk(el: ET.Element, el_chain: list[ET.Element]) -> bool:
        if not move(el, el_chain) or not add(el.text, el_chain):
            return False
        for child in el:
            if not walk(child, el_chain + [child]) or not add(child.tail, el_chain):
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
        last[4] = _width(last[0], last[3]) or 0.0
        start, end = pieces[0][1], last[1] + last[4]
        anchor = _inherited(chunk["chain"], "text-anchor") or "start"
        shift = -(end - start) / 2 if anchor == "middle" else -(end - start) if anchor == "end" else 0.0
        boxes = []
        for label, x, y, el_chain, width in pieces:
            if not label:
                continue
            size = _font_size(el_chain) or DEFAULT_FONT_SIZE
            top, bottom = BASELINES.get(_inherited(el_chain, "dominant-baseline") or "", ALPHABETIC)
            boxes.append((x + shift, y + top * size, x + shift + width, y + bottom * size))
        result.append(("".join(piece[0] for piece in pieces), boxes))
    return result


def _short(label: str, limit: int = 30) -> str:
    """Shorten a label for a message."""
    return label if len(label) <= limit else label[: limit - 3] + "..."


def overlaps(svg_text: str) -> tuple[list[str], int]:
    """Return the warnings about overlapping labels, and how many labels were not checked.

    The boxes are estimates (see the constants above). A <text> with a
    rotate, scale, matrix or skew transform, with textLength, or with a
    position or font size that is not a plain number, is not checked but
    counted. Returns ([], 0) if the file cannot be read.
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return [], 0
    parents = {child: parent for parent in root.iter() for child in parent}
    boxes, skipped = [], 0
    for el in _painted(root):
        if _local(el.tag) != "text":
            continue
        chain = [el]
        while chain[0] in parents:
            chain.insert(0, parents[chain[0]])
        shift = _translation(chain)
        chunks = _chunks(el, chain)
        if shift is None or chunks is None or any("textLength" in t.attrib for t in el.iter()):
            skipped += 1
            continue
        for label, chunk_boxes in chunks:
            chunk = len(boxes)
            for box in chunk_boxes:
                moved = (box[0] + shift[0], box[1] + shift[1], box[2] + shift[0], box[3] + shift[1])
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
        warnings, skipped = overlaps(svg_text)
        for problem in problems:
            print(f"{path}: {problem}")
        for warning in warnings:
            print(f"{path}: warning: {warning}")
        if skipped:
            print(
                f"{path}: note: {skipped} label(s) not checked for overlap "
                "(rotate, scale, matrix, skew, textLength, or a position or font size in % or em)"
            )
        if problems or (strict and warnings):
            status = 1
        elif not warnings:
            print(f"{path}: ok")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
