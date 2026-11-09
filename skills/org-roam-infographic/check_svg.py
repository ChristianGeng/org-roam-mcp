"""Check an infographic SVG against the rules of the org-roam-infographic skill.

Usage: python check_svg.py FILE.svg [FILE.svg ...]

Prints one line per problem and exits 1 if there is any, 0 if the file is
fine. It checks the structure only; rendering the file and looking at it is
still needed (see SKILL.md, step 4). Uses the standard library only.
"""

import re
import sys
import xml.etree.ElementTree as ET


SVG_NS = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
MAX_WIDTH = 1200
FORBIDDEN_TAGS = {"script", "foreignObject", "image"}
EXTERNAL_URL = re.compile(r"(?:https?:)?//|@import|@font-face", re.IGNORECASE)


def _local(tag: str) -> str:
    """Return the tag name without its XML namespace."""
    return tag.split("}", 1)[-1]


def _number(value: str | None) -> float | None:
    """Read a length such as "720" or "720px"; None if it is not one."""
    if value is None:
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\s*", value)
    return float(match.group(1)) if match else None


def _width(root: ET.Element) -> float | None:
    """Return the picture's width from width= or else from the viewBox."""
    width = _number(root.get("width"))
    if width is not None:
        return width
    view_box = root.get("viewBox")
    if view_box:
        parts = view_box.replace(",", " ").split()
        if len(parts) == 4:
            return _number(parts[2])
    return None


def _covers_picture(rect: ET.Element, width: float | None, height: float | None) -> bool:
    """Whether a <rect> is a filled background card over the whole picture."""
    if rect.get("fill") in (None, "none", "transparent"):
        return False
    if _number(rect.get("x") or "0") != 0 or _number(rect.get("y") or "0") != 0:
        return False
    w, h = rect.get("width"), rect.get("height")
    if w == "100%" and h == "100%":
        return True
    return width is not None and height is not None and _number(w) == width and _number(h) == height


def check(svg_text: str) -> list[str]:
    """Return the problems found in one SVG document; empty if none."""
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as error:
        return [f"not well-formed XML: {error}"]
    if _local(root.tag) != "svg":
        return [f"the root element is <{_local(root.tag)}>, not <svg>"]

    problems = []
    width = _width(root)
    height = _number(root.get("height"))
    if root.get("viewBox") is None:
        problems.append("no viewBox on <svg>")
    if width is None:
        problems.append("no width: set width= or a viewBox")
    elif width > MAX_WIDTH:
        problems.append(f"width {width:g} px is over {MAX_WIDTH} px")

    elements = list(root.iter())
    tags = [_local(el.tag) for el in elements]
    for tag in sorted(FORBIDDEN_TAGS.intersection(tags)):
        problems.append(f"<{tag}> is not allowed (one self-contained file, text as text)")

    for el in elements:
        for attr in ("href", XLINK_HREF):
            href = el.get(attr)
            if href and not href.startswith("#"):
                problems.append(f"external reference {href!r} in <{_local(el.tag)}>")
        if _local(el.tag) == "style" and el.text and EXTERNAL_URL.search(el.text):
            problems.append("the <style> loads something from outside (url, @import or @font-face)")
        style = el.get("style")
        if style and "url(" in style and "url(#" not in style:
            problems.append(f"style={style!r} in <{_local(el.tag)}> loads something from outside")

    if "text" not in tags:
        problems.append("no <text>: labels must be text, not paths")
    if "title" not in tags:
        problems.append("no <title> with the message")
    if not any(_local(el.tag) == "rect" and _covers_picture(el, width, height) for el in elements):
        problems.append("no filled background card over the whole picture (needed for dark pages)")
    return problems


def main(paths: list[str]) -> int:
    """Check each file; print the problems; return the exit status."""
    if not paths:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    status = 0
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            problems = check(handle.read())
        for problem in problems:
            print(f"{path}: {problem}")
        if problems:
            status = 1
        else:
            print(f"{path}: ok")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
