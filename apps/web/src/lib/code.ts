/**
 * Helpers for code shown in the UI: line ranges, coverage per file, a pull request's
 * changed files, the file tree, and a small syntax highlighter for Python and
 * JavaScript/TypeScript (no dependency, no HTML strings: it returns tokens that React
 * renders as text, so nothing in a file can inject markup).
 */

export type Range = [number, number];

function obj(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function num(v: unknown, fallback = 0): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

/** `[[28, 38], [40, 40]]` from the API, keeping only well-formed pairs. */
export function readRanges(raw: unknown): Range[] {
  if (!Array.isArray(raw)) return [];
  const out: Range[] = [];
  for (const r of raw) {
    if (Array.isArray(r) && typeof r[0] === "number" && typeof r[1] === "number") out.push([r[0], Math.max(r[0], r[1])]);
    else if (typeof r === "number") out.push([r, r]);
  }
  return out;
}

/** "28 to 38, 40": ranges in words, the way a person reads them. */
export function formatRanges(ranges: Range[], max = 6): string {
  if (!ranges.length) return "none";
  const parts = ranges.slice(0, max).map(([a, b]) => (a === b ? `${a}` : `${a} to ${b}`));
  const more = ranges.length - max;
  return more > 0 ? `${parts.join(", ")} and ${more} more` : parts.join(", ");
}

/** Sorted line numbers folded into ranges: [1,2,3,7] becomes [[1,3],[7,7]]. */
export function toRanges(lines: number[]): Range[] {
  const sorted = [...new Set(lines)].sort((a, b) => a - b);
  const out: Range[] = [];
  for (const n of sorted) {
    const last = out[out.length - 1];
    if (last && n === last[1] + 1) last[1] = n;
    else out.push([n, n]);
  }
  return out;
}

export function inRanges(line: number, ranges: Range[]): boolean {
  return ranges.some(([a, b]) => line >= a && line <= b);
}

export interface FileCoverageView {
  path: string;
  percent: number;
  linesTotal: number;
  linesCovered: number;
  missing: Range[];
}

/** The per-file rows of a coverage report. */
export function readCoverageFiles(raw: unknown): FileCoverageView[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((f) => {
      const o = obj(f);
      return {
        path: typeof o.path === "string" ? o.path : "",
        percent: num(o.percent, 100),
        linesTotal: num(o.lines_total),
        linesCovered: num(o.lines_covered),
        missing: readRanges(o.missing),
      };
    })
    .filter((f) => f.path);
}

export interface ChangedFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
  changed: Range[];
  previousPath: string | null;
}

/** A pull request's changed files. */
export function readChangedFiles(raw: unknown): ChangedFile[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((f) => {
      const o = obj(f);
      return {
        path: typeof o.path === "string" ? o.path : "",
        status: typeof o.status === "string" ? o.status : "modified",
        additions: num(o.additions),
        deletions: num(o.deletions),
        changed: readRanges(o.changed_lines),
        previousPath: typeof o.previous_path === "string" ? o.previous_path : null,
      };
    })
    .filter((f) => f.path);
}

export interface TreeNode {
  name: string;
  path: string;
  dir: boolean;
  children: TreeNode[];
}

/** A nested tree from flat paths; folders first, then names in order. */
export function buildTree(paths: string[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", dir: true, children: [] };
  for (const p of paths) {
    const parts = p.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join("/");
      const dir = i < parts.length - 1;
      let child = node.children.find((c) => c.name === part && c.dir === dir);
      if (!child) {
        child = { name: part, path, dir, children: [] };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sort = (n: TreeNode) => {
    n.children.sort((a, b) => (a.dir === b.dir ? a.name.localeCompare(b.name) : a.dir ? -1 : 1));
    n.children.forEach(sort);
  };
  sort(root);
  return root.children;
}

export type TokenType = "keyword" | "string" | "comment" | "number" | "function" | "decorator" | "plain";
export interface Token {
  type: TokenType;
  text: string;
}

const PY = new Set(
  "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield self".split(" "),
);
const JS = new Set(
  "as async await break case catch class const continue default delete do else export extends false finally for from function if import in instanceof interface let new null of return static super switch this throw true try type typeof undefined var void while yield expect describe it test".split(" "),
);

export function languageOf(path: string | null | undefined): "python" | "javascript" | null {
  if (!path) return null;
  if (/\.py$/i.test(path)) return "python";
  if (/\.(m|c)?[jt]sx?$/i.test(path)) return "javascript";
  return null;
}

/** One line of code as tokens. Strings and comments that span lines are not tracked. */
export function highlightLine(line: string, lang: "python" | "javascript" | "typescript" | string | null): Token[] {
  if (lang !== "python" && lang !== "javascript" && lang !== "typescript") return [{ type: "plain", text: line }];
  const py = lang === "python";
  const keywords = py ? PY : JS;
  const tokens: Token[] = [];
  const push = (type: TokenType, text: string) => {
    if (!text) return;
    const last = tokens[tokens.length - 1];
    if (last && last.type === type && type === "plain") last.text += text;
    else tokens.push({ type, text });
  };
  let i = 0;
  while (i < line.length) {
    const rest = line.slice(i);
    const comment = py ? /^#.*/.exec(rest) : /^\/\/.*/.exec(rest);
    if (comment) {
      push("comment", comment[0]);
      break;
    }
    const str = /^(?:[rbfuRBFU]{0,2})("""|'''|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|`(?:\\.|[^`\\])*`?)/.exec(rest);
    if (str && (py || !/^[rbfuRBFU]/.test(rest) || rest[0] === '"' || rest[0] === "'" || rest[0] === "`")) {
      if (str[1] === '"""' || str[1] === "'''") {
        const end = rest.indexOf(str[1], str[0].length);
        const text = end >= 0 ? rest.slice(0, end + 3) : rest;
        push("string", text);
        i += text.length;
        continue;
      }
      push("string", str[0]);
      i += str[0].length;
      continue;
    }
    const decorator = py ? /^@[A-Za-z_][\w.]*/.exec(rest) : null;
    if (decorator) {
      push("decorator", decorator[0]);
      i += decorator[0].length;
      continue;
    }
    const number = /^\d[\d_]*(?:\.\d+)?(?:e[+-]?\d+)?/i.exec(rest);
    if (number && !/[\w]/.test(line[i - 1] ?? "")) {
      push("number", number[0]);
      i += number[0].length;
      continue;
    }
    const word = /^[A-Za-z_$][\w$]*/.exec(rest);
    if (word) {
      const w = word[0];
      const after = line.slice(i + w.length);
      if (keywords.has(w)) push("keyword", w);
      else if (/^\s*\(/.test(after)) push("function", w);
      else push("plain", w);
      i += w.length;
      continue;
    }
    push("plain", line[i] as string);
    i += 1;
  }
  return tokens;
}

/**
 * Every line of a file as tokens, carrying Python's triple-quoted strings (docstrings)
 * across lines, which a line-by-line pass cannot see.
 */
export function highlightCode(code: string, lang: string | null): Token[][] {
  const out: Token[][] = [];
  let open: string | null = null;
  for (const line of code.split("\n")) {
    let tokens: Token[];
    if (open) {
      const end = line.indexOf(open);
      if (end < 0) {
        out.push(line ? [{ type: "string", text: line }] : []);
        continue;
      }
      const head: Token = { type: "string", text: line.slice(0, end + 3) };
      tokens = [head, ...highlightLine(line.slice(end + 3), lang)].filter((t) => t.text);
      open = null;
    } else {
      tokens = highlightLine(line, lang);
    }
    const last = [...tokens].reverse().find((t) => t.type === "string");
    if (last) {
      const delim = /^[rbfuRBFU]{0,2}("""|''')/.exec(last.text)?.[1];
      if (delim && (last.text.length < 6 || !last.text.endsWith(delim) || last.text.replace(/^[rbfuRBFU]{0,2}/, "").length < 6)) {
        // A triple-quoted string that opens here and does not close on this line.
        if (tokens[tokens.length - 1] === last) open = delim;
      }
    }
    out.push(tokens);
  }
  return out;
}
