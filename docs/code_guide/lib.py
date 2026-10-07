"""Helpers for the code guide: pull real source out of the app files (with
their line numbers), highlight it, and wrap it in the page's markup."""

import ast
import html
import json
import os
import re

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import JavascriptLexer, JsonLexer, PythonLexer

APP = "/home/frappe/frappe-bench/apps/custom_crm_updates/custom_crm_updates"
SHOWN = set()  # "file::qualname" of every Python def shown, for the coverage check


def path(rel):
	return os.path.join(APP, rel)


def read(rel):
	with open(path(rel), encoding="utf-8") as f:
		return f.read()


def esc(s):
	return html.escape(s, quote=False)


def _block(code, lexer, start, caption):
	fmt = HtmlFormatter(linenos="inline", linenostart=start, nowrap=False, cssclass="hl", wrapcode=True)
	# tabs would align to stops measured from the line-number gutter
	body = highlight(code.expandtabs(4), lexer, fmt)
	return f'<figure class="code"><figcaption><span class="file">{esc(caption)}</span></figcaption>{body}</figure>'


def _node_source(src, node):
	lines = src.splitlines()
	start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno)
	return "\n".join(lines[start - 1 : node.end_lineno]), start, node.end_lineno


def _find(tree, qualname):
	parts = qualname.split(".")
	scope = tree.body
	node = None
	for part in parts:
		node = next(
			n
			for n in scope
			if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == part)
			or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == part for t in n.targets))
		)
		scope = getattr(node, "body", [])
	return node


def py(rel, *qualnames, caption=None):
	"""Show Python definitions/assignments, each with its real line numbers.
	Consecutive items are shown in one block per item."""
	src = read(rel)
	tree = ast.parse(src)
	out = []
	for q in qualnames:
		node = _find(tree, q)
		code, a, b = _node_source(src, node)
		if isinstance(node, ast.FunctionDef):
			SHOWN.add(f"{rel}::{q}")
		out.append(_block(code, PythonLexer(), a, caption or f"{rel} · lines {a}–{b}"))
	return "\n".join(out)


def py_lines(rel, a, b, caption=None):
	code = "\n".join(read(rel).splitlines()[a - 1 : b])
	return _block(code, PythonLexer(), a, caption or f"{rel} · lines {a}–{b}")


def js(rel, a=None, b=None):
	lines = read(rel).splitlines()
	a = a or 1
	b = b or len(lines)
	return _block("\n".join(lines[a - 1 : b]), JavascriptLexer(), a, f"{rel} · lines {a}–{b}")


def json_field(rel, fieldname):
	doc = json.loads(read(rel))
	field = next(f for f in doc["fields"] if f["fieldname"] == fieldname)
	return _block(json.dumps(field, indent=1), JsonLexer(), 1, f"{rel} · field “{fieldname}”")


def doctype_table(rel):
	doc = json.loads(read(rel))
	rows = []
	for f in doc["fields"]:
		if f["fieldtype"] in ("Section Break", "Column Break", "Tab Break"):
			continue
		flags = [k for k, label in (("reqd", "required"), ("read_only", "read-only"), ("in_list_view", "in grid")) if f.get(k)]
		opts = f.get("options", "")
		opts = ", ".join(o for o in opts.split("\n") if o) if f["fieldtype"] == "Select" else opts
		rows.append(
			f"<tr><td><code>{esc(f['fieldname'])}</code></td><td>{esc(f.get('label', ''))}</td>"
			f"<td>{esc(f['fieldtype'])}</td><td>{esc(opts)}</td><td>{esc(', '.join(flags))}</td></tr>"
		)
	head = "<tr><th>Fieldname</th><th>Label</th><th>Type</th><th>Options</th><th>Flags</th></tr>"
	return f'<div class="table-box"><table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def all_python_defs(rel):
	"""file::qualname of every function and method in a file."""
	tree = ast.parse(read(rel))
	found = []
	for n in tree.body:
		if isinstance(n, ast.FunctionDef):
			found.append(f"{rel}::{n.name}")
		elif isinstance(n, ast.ClassDef):
			found += [f"{rel}::{n.name}.{m.name}" for m in n.body if isinstance(m, ast.FunctionDef)]
	return found


def count_lines(rel):
	return len(read(rel).splitlines())


CSS = r"""
/* Layout: the same drawing-set identity as the presentation guide, plus a
   sticky contents rail on wide screens and full-width code sheets. */
:root {
  --bg: #f2f3f5; --surface: #fcfcfd; --surface-2: #eaedf1;
  --ink: #141820; --ink-2: #444d5c; --muted: #687080; --line: #d8dce3;
  --accent: #1d4f9c; --accent-soft: #e2eaf7; --signal: #8f5600; --signal-soft: #fbefd9;
  --c-lead: #2a78d6; --c-opp: #eb6834; --c-tender: #1baf7a; --c-cust: #eda100;
  --code-bg: #f6f7f9; --code-line: #e6e9ee;
  --t-kw: #7b30b8; --t-str: #1d7a3a; --t-com: #6b7280; --t-fn: #1d4f9c; --t-num: #a8530a; --t-bi: #0e7490; --t-op: #444d5c;
  --f-display: "Barlow Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
  --f-body: "Source Sans 3", "Segoe UI", system-ui, -apple-system, sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1217; --surface: #171b22; --surface-2: #1f242d;
    --ink: #eef1f6; --ink-2: #b9c0cc; --muted: #8a919e; --line: #2b313b;
    --accent: #8db3f2; --accent-soft: #1b2940; --signal: #f0a742; --signal-soft: #2e2414;
    --c-lead: #3987e5; --c-opp: #d95926; --c-tender: #199e70; --c-cust: #c98500;
    --code-bg: #12161c; --code-line: #232831;
    --t-kw: #c792ea; --t-str: #9ece6a; --t-com: #8a919e; --t-fn: #8db3f2; --t-num: #f0a742; --t-bi: #7dcfff; --t-op: #b9c0cc;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1217; --surface: #171b22; --surface-2: #1f242d;
  --ink: #eef1f6; --ink-2: #b9c0cc; --muted: #8a919e; --line: #2b313b;
  --accent: #8db3f2; --accent-soft: #1b2940; --signal: #f0a742; --signal-soft: #2e2414;
  --c-lead: #3987e5; --c-opp: #d95926; --c-tender: #199e70; --c-cust: #c98500;
  --code-bg: #12161c; --code-line: #232831;
  --t-kw: #c792ea; --t-str: #9ece6a; --t-com: #8a919e; --t-fn: #8db3f2; --t-num: #f0a742; --t-bi: #7dcfff; --t-op: #b9c0cc;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--f-body); font-size: 16px; line-height: 1.6; padding-inline: 20px; padding-block: 28px 64px; }
[hidden] { display: none !important; }
img { max-width: 100%; }
.page { max-width: 1240px; margin: 0 auto; display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 40px; align-items: start; }
.rail { position: sticky; top: 16px; max-height: calc(100vh - 32px); overflow-y: auto; font-size: .88rem; display: grid; gap: 2px; padding-right: 6px; }
.rail .rail-title { font-family: var(--f-mono); font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin: 10px 0 4px; }
.rail a { color: var(--ink-2); text-decoration: none; padding: 3px 8px; border-radius: 5px; display: grid; grid-template-columns: 30px minmax(0, 1fr); }
.rail a span { font-family: var(--f-mono); font-size: .72rem; color: var(--muted); padding-top: 2px; }
.rail a:hover { background: var(--surface-2); color: var(--accent); }
main { display: grid; gap: 64px; min-width: 0; }
h1, h2, h3, h4 { font-family: var(--f-display); text-wrap: balance; line-height: 1.1; margin: 0; }
h1 { font-size: clamp(2.4rem, 5.5vw, 3.8rem); text-transform: uppercase; letter-spacing: .01em; }
h2 { font-size: clamp(1.6rem, 3vw, 2.2rem); text-transform: uppercase; letter-spacing: .02em; }
h3 { font-size: 1.25rem; text-transform: uppercase; letter-spacing: .03em; font-weight: 600; }
h4 { font-family: var(--f-body); font-size: 1rem; font-weight: 700; }
p { margin: 0; }
.prose { display: grid; gap: 12px; max-width: 74ch; }
.prose ul, .prose ol { margin: 0; padding-left: 1.3em; display: grid; gap: 6px; }
code { font-family: var(--f-mono); font-size: .86em; background: var(--surface-2); padding: .06em .32em; border-radius: 4px; overflow-wrap: anywhere; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.titleblock { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); border: 2px solid var(--ink); background: var(--surface); }
.tb-main { padding: 26px; display: grid; gap: 12px; border-right: 2px solid var(--ink); }
.tb-main .lede { font-size: 1.12rem; color: var(--ink-2); max-width: 56ch; }
.eyebrow { font-family: var(--f-mono); font-size: .74rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
.tb-meta { display: grid; grid-template-columns: auto minmax(0, 1fr); }
.tb-meta div { padding: 9px 14px; border-bottom: 1px solid var(--line); font-size: .92rem; }
.tb-meta div:nth-child(odd) { font-family: var(--f-mono); font-size: .68rem; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); border-right: 1px solid var(--line); display: flex; align-items: center; }
.tb-meta div:nth-last-child(-n+2) { border-bottom: 0; }

.sheet { display: grid; gap: 20px; scroll-margin-top: 12px; min-width: 0; }
.sheet-head { display: grid; gap: 8px; border-top: 2px solid var(--ink); padding-top: 14px; }
.sheet-no { font-family: var(--f-mono); font-size: .76rem; letter-spacing: .14em; color: var(--muted); text-transform: uppercase; }
.sheet-head > p { color: var(--ink-2); max-width: 74ch; }

.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 20px; min-width: 0; display: grid; gap: 12px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.meta-row { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { font-family: var(--f-mono); font-size: .76rem; border: 1px solid var(--line); background: var(--surface); padding: 2px 9px; border-radius: 999px; color: var(--ink-2); }
.chip.user { border-color: var(--accent); color: var(--accent); }
.label { font-family: var(--f-mono); font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }

.step { display: grid; gap: 16px; padding: 22px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; min-width: 0; scroll-margin-top: 12px; }
.step-head { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 14px; align-items: start; }
.step-no { font-family: var(--f-display); font-weight: 700; font-size: 2rem; line-height: 1; color: var(--accent); min-width: 2ch; }
.step-head h3 { font-size: 1.4rem; }
.step-head p { color: var(--ink-2); margin-top: 6px; }
.why { border-left: 3px solid var(--signal); background: var(--signal-soft); padding: 10px 14px; border-radius: 0 6px 6px 0; display: grid; gap: 4px; max-width: 80ch; }
.why b { font-family: var(--f-mono); font-size: .72rem; letter-spacing: .1em; text-transform: uppercase; color: var(--signal); font-weight: 500; }
.explain { display: grid; gap: 8px; max-width: 80ch; }
.explain ol, .explain ul { margin: 0; padding-left: 1.3em; display: grid; gap: 6px; }

figure.code { margin: 0; min-width: 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--code-bg); }
figure.code figcaption { font-family: var(--f-mono); font-size: .74rem; color: var(--muted); padding: 7px 12px; border-bottom: 1px solid var(--code-line); background: var(--surface-2); }
figure.code .hl { overflow-x: auto; }
figure.code pre { margin: 0; padding: 12px 0; font-family: var(--f-mono); font-size: .82rem; line-height: 1.6; tab-size: 4; -moz-tab-size: 4; }
figure.code code { background: none; padding: 0 14px 0 0; font-size: inherit; overflow-wrap: normal; display: block; min-width: max-content; }
.hl .linenos { color: var(--muted); opacity: .7; padding: 0 14px 0 12px; user-select: none; display: inline-block; min-width: 4.2em; text-align: right; }
.hl .k, .hl .kn, .hl .kd, .hl .kc, .hl .kr, .hl .ow, .hl .kp { color: var(--t-kw); }
.hl .s, .hl .s1, .hl .s2, .hl .sa, .hl .se, .hl .si, .hl .sb, .hl .sh, .hl .dl, .hl .sr { color: var(--t-str); }
.hl .sd { color: var(--t-com); }
.hl .c, .hl .c1, .hl .cm, .hl .ch, .hl .cs { color: var(--t-com); font-style: italic; }
.hl .nf, .hl .nc, .hl .fm { color: var(--t-fn); font-weight: 500; }
.hl .m, .hl .mi, .hl .mf { color: var(--t-num); }
.hl .nb, .hl .bp, .hl .nd { color: var(--t-bi); }
.hl .o { color: var(--t-op); }
.hl .nt { color: var(--t-fn); }
.hl .kc + .p, .hl .p { color: var(--ink); }

table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { text-align: left; vertical-align: top; padding: 9px 11px; border-bottom: 1px solid var(--line); }
th { font-family: var(--f-mono); font-weight: 500; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); background: var(--surface-2); }
tbody tr:last-child td { border-bottom: 0; }
.table-box { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; overflow-x: auto; }
.table-box table { min-width: 680px; }

.flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: 6px; }
.flow .node { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; font-size: .86rem; display: grid; gap: 2px; min-width: 120px; flex: 1 1 120px; }
.flow .node b { font-family: var(--f-mono); font-size: .78rem; font-weight: 500; }
.flow .node span { color: var(--ink-2); font-size: .8rem; }
.flow .node.ours { border-color: var(--accent); background: var(--accent-soft); }
.flow .arrow { align-self: center; color: var(--muted); }
.diagram { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px; overflow-x: auto; }
.diagram svg { display: block; width: 100%; min-width: 820px; height: auto; color: var(--ink); font-family: var(--f-body); }
figure.fig { margin: 0; display: grid; gap: 8px; min-width: 0; }
figure.fig figcaption { color: var(--ink-2); font-size: .9rem; max-width: 80ch; }

footer { color: var(--muted); font-size: .85rem; border-top: 1px solid var(--line); padding-top: 14px; }

@media (max-width: 980px) {
  .page { grid-template-columns: minmax(0, 1fr); }
  .rail { position: static; max-height: none; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); border: 1px solid var(--line); background: var(--surface); border-radius: 8px; padding: 10px; }
  .rail .rail-title { grid-column: 1 / -1; }
}
@media (max-width: 760px) {
  .titleblock { grid-template-columns: minmax(0, 1fr); }
  .tb-main { border-right: 0; border-bottom: 2px solid var(--ink); }
  .grid-2 { grid-template-columns: minmax(0, 1fr); }
  .step { padding: 16px; }
}
@media (max-width: 480px) { body { padding-inline: 16px; } }
"""
