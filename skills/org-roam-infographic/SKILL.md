---
name: org-roam-infographic
description: Use when the user asks for an infographic, chart, timeline or diagram made from their org-roam notes. Reads the notes through the org-roam MCP server and draws the picture with code, as one SVG file (or one self-contained HTML file when it needs interaction), so every number and label is exact and the file can be edited. Sends nothing anywhere.
---

# Infographics from org-roam notes

Draw infographics from the user's org-roam notes **with code**: an SVG file
(the default) or one self-contained HTML file. Image models draw text and
numbers badly; code draws them exactly, and the result can be edited later.
Use an image model only for illustrative pictures, never for numbers.

The notes are the user's. This skill sends nothing anywhere: no image API,
no upload, no web request. Everything happens with the org-roam MCP server
and local files.

## 1. Gather

- Find the note or notes the user names with `org_roam_find`, then read
  them with `org_roam_read_node`. Use `org_roam_backlinks` and
  `org_roam_bfs` when the user wants the notes around a topic.
- Take numbers, dates and claims **only** from the notes, or from sources
  the user gives you. For each one, keep the node it came from.
- If a number is missing or unclear, ask. Never estimate or fill in a value.

## 2. Choose a form

Pick the form that fits the content. One message per infographic.

| Content | Form |
|---|---|
| Dates and events | Timeline |
| Numbers over time | Line chart (many points) or bar chart (few points) |
| Numbers by category | Bar chart, sorted by value unless the order means something |
| A compared with B | Comparison table or cards |
| Steps in order | Process or flow diagram |
| How notes link | Small map of linked notes: the notes from `org_roam_bfs`, the links between them from `org_roam_backlinks` for each of those notes (or the `id:` links in their text) |

At most 5 to 7 items per chart. If there are more, show the most important
ones and say what was left out, or make two infographics.

## 3. Draw

**SVG (the default):**

- One file. No external fonts, images, stylesheets or scripts, and no
  `<foreignObject>`.
- At most about 1200 px wide; set `width`, `height` and `viewBox` on
  `<svg>`.
- Text as `<text>`, never as paths, so it stays searchable and editable.
  Add `<title>` and `<desc>` with the message and the numbers.
- Readable on a light and on a dark page: draw the infographic on its own
  filled background card, a `<rect>` that covers the whole `viewBox`, drawn
  first, before any text.
- No `url(...)` to anything outside the file; only `url(#id)` for
  gradients and the like defined in the same file.

**HTML (only when it needs interaction):** one self-contained file with
inline SVG, CSS and script, and no requests to other servers.

**Style:**

- A small fixed palette: one main colour, one colour to highlight, greys
  for text, axes and grid. For example: main `#2f6f9f`, highlight
  `#c05621`, text `#1f2933`, secondary text `#52606d`, axes `#9aa5b1`,
  background `#f8fafc`.
- Font stack: `"DejaVu Sans", "Helvetica Neue", Arial, sans-serif`.
- Labels on the data (the value above each bar, the name at the end of
  each line), not in a legend, where possible.
- Numbers right-aligned in tables; units on every number or in the axis
  title; the same number of decimals throughout.
- Use the language of the note: German labels for a German note, English
  labels for an English note.

**Every infographic has:** a title that states the message, the key
numbers, units, and a short source line that names the notes and the date,
for example: `Source: org-roam notes reading-circle, club-budget; 2026-11-09`.

## 4. Check

- Every number, date and label in the picture appears in the notes (or in
  a source the user gave). Compare them one by one.
- Run the structure check, `check_svg.py`, which is next to this
  `SKILL.md` (it needs only Python 3.10+ and its standard library):
  `python3 <this skill's folder>/check_svg.py <file.svg>`.
  It reports external references and `url(...)`s, scripts and images, a
  missing `width`, `height`, `viewBox`, `<title>` or `<desc>`, text drawn
  as paths only, a missing or late background card, and a width over
  1200 px.
- Render the file once and look at it, for example with
  `rsvg-convert -o check.png file.svg`, or with a headless browser:
  `google-chrome --headless=new --screenshot=check.png file.svg`.
  Look for overlapping or cut-off text, and check it on a light and a dark
  background. Fix it and render again. Never open a window on the user's
  screen for this.

## 5. Save with the note

- Write the file next to the note's file, or into the folder the user's
  org-roam uses for attachments. Name it after the note and the date, for
  example `reading-circle-members-2026-11-09.svg`.
- Never overwrite a file. If the name exists, add `-2`, `-3`, and so on.
- Add an Org link to the file in the note (`[[file:reading-circle-members-2026-11-09.svg]]`)
  **only when the user asks**. Then run `org_roam_sync`.
- Tell the user the file's path and what the picture shows.

## Example

`docs/examples.md` in the org-roam-mcp repository shows a synthetic note with
five dates and numbers, and the SVG this skill makes from it.
