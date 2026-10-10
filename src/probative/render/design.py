"""The shared artifact design system (PROBATIVE_PHASE_SPECS.md S4), for the three
single-file HTML renderers (PB9, PB19, PB29). No build step, no CDN, no external
fonts: everything is inline.

Light tokens live on `:root`; dark tokens are defined twice, once for the system
preference (unless the user picked light) and once for an explicit
`data-theme="dark"`, so a colour is never defined only inside a media query.
Severity (and, in PB19/PB29, provenance tier) is never carried by hue alone: a
text label, a glyph and a border pattern travel with it.
"""

from __future__ import annotations

_LIGHT = """\
  --bg: #fbfbf9; --surface: #ffffff; --fg: #1b1f24; --muted: #5b636b; --line: #d9d9d4;
  --block: #b3261e; --warn: #8a5a00; --note: #3d5a80; --focus: #0b57d0;
  --mark: #fff0b3; --mark-fg: #1b1f24; --block-bg: #fdecea; --warn-bg: #fff4de; --note-bg: #e8eff7;
"""
_DARK = """\
  --bg: #14171a; --surface: #1c2024; --fg: #e8eaed; --muted: #a0a8b0; --line: #343a40;
  --block: #ff8a80; --warn: #f2c46d; --note: #9fb8d9; --focus: #8ab4f8;
  --mark: #5c4b00; --mark-fg: #fff7d6; --block-bg: #3a1f1d; --warn-bg: #3a2f17; --note-bg: #1f2a38;
"""

BASE_CSS = f""":root {{
{_LIGHT}  color-scheme: light dark;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
{_DARK}  }}
}}
:root[data-theme="dark"] {{
{_DARK}}}
:root[data-theme="light"] {{ color-scheme: light; }}
:root[data-theme="dark"] {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}}
main {{ max-width: 62rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }}
h1 {{ font-size: 1.5rem; margin: 0 0 .25rem; overflow-wrap: anywhere; }}
h2 {{ font-size: 1.2rem; margin: 2rem 0 .5rem; border-bottom: 1px solid var(--line); }}
h3 {{ font-size: 1.05rem; margin: 1.25rem 0 .25rem; }}
h4 {{ font-size: .98rem; margin: 1rem 0 .25rem; font-weight: 600; }}
.muted {{ color: var(--muted); }}
:focus-visible {{ outline: 3px solid var(--focus); outline-offset: 2px; }}
table {{ border-collapse: collapse; width: 100%; background: var(--surface); }}
th, td {{
  border: 1px solid var(--line); padding: .4rem .6rem; text-align: left; vertical-align: top;
}}
td.n, th.n {{ text-align: right; font-variant-numeric: tabular-nums; }}
.scroll {{ overflow-x: auto; }}
button {{
  font: inherit; color: var(--fg); background: var(--surface); border: 1px solid var(--line);
  border-radius: .4rem; padding: .25rem .7rem; cursor: pointer;
}}
button[aria-pressed="true"] {{ border-color: var(--fg); font-weight: 600; }}
.sev {{ font-weight: 700; letter-spacing: .02em; }}
.sev-block {{ color: var(--block); }}
.sev-warn {{ color: var(--warn); }}
.sev-note {{ color: var(--note); }}
"""
