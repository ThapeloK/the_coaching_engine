import type { ReactNode } from "react";

/**
 * Render the operations brief inline, without pulling in a markdown library.
 *
 * WHY NOT react-markdown
 *
 * One new dependency plus its remark and rehype tree, added the night before a
 * pitch, to render a document whose grammar is narrow and known. Across real
 * runs Manus writes headings, paragraphs, inline bold and, whenever the brief
 * compares teams, a table. Lists appear occasionally. All of those are handled
 * here; anything else degrades to readable plain text rather than breaking the
 * page.
 *
 * WHY IT IS SAFE
 *
 * Nothing here sets innerHTML. Every branch returns React elements, so markup
 * that arrives inside the brief is displayed as characters rather than parsed.
 * That matters more than usual: this text is written by an external agent from
 * data the product supplied, and it lands in a manager's console.
 */

/** Inline pass: bold, code, and nothing else that can smuggle markup through. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  // Split on **bold** and `code`, keeping the delimiters so they can be typed.
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  parts.forEach((part, i) => {
    if (!part) return;
    const key = `${keyPrefix}-${i}`;
    if (part.startsWith("**") && part.endsWith("**")) {
      out.push(
        <strong key={key} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>,
      );
    } else if (part.startsWith("`") && part.endsWith("`")) {
      out.push(
        <code key={key} className="rounded bg-muted px-1 py-0.5 text-[0.9em]">
          {part.slice(1, -1)}
        </code>,
      );
    } else {
      out.push(<span key={key}>{part}</span>);
    }
  });
  return out;
}

export function BriefMarkdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];

  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let table: { rows: string[][]; headerSeen: boolean } | null = null;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const key = `p-${blocks.length}`;
    blocks.push(
      <p key={key} className="text-sm leading-relaxed text-muted-foreground">
        {inline(paragraph.join(" "), key)}
      </p>,
    );
    paragraph = [];
  };

  const flushList = () => {
    if (list === null) return;
    const key = `l-${blocks.length}`;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag
        key={key}
        className={`ml-5 space-y-1 text-sm leading-relaxed text-muted-foreground ${
          list.ordered ? "list-decimal" : "list-disc"
        }`}
      >
        {list.items.map((item, i) => (
          <li key={`${key}-${i}`}>{inline(item, `${key}-${i}`)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };

  const flushTable = () => {
    if (table === null || table.rows.length === 0) {
      table = null;
      return;
    }
    const key = `t-${blocks.length}`;
    const [head, ...body] = table.rows;
    const hasHeader = table.headerSeen && body.length > 0;
    const rows = hasHeader ? body : table.rows;
    blocks.push(
      // Scrolls inside itself: a four column table in a console sidebar must
      // never make the whole page scroll sideways.
      <div key={key} className="-mx-1 overflow-x-auto px-1">
        <table className="w-full min-w-[34rem] border-collapse text-sm">
          {hasHeader && (
            <thead>
              <tr>
                {head.map((cell, i) => (
                  <th
                    key={`${key}-h-${i}`}
                    scope="col"
                    className="border-b px-2 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                  >
                    {inline(cell, `${key}-h-${i}`)}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {rows.map((row, r) => (
              <tr key={`${key}-r-${r}`} className="border-b last:border-0">
                {row.map((cell, c) => (
                  <td
                    key={`${key}-r-${r}-${c}`}
                    className="px-2 py-1.5 align-top leading-relaxed text-muted-foreground"
                  >
                    {inline(cell, `${key}-r-${r}-${c}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
    table = null;
  };

  const flush = () => {
    flushParagraph();
    flushList();
    flushTable();
  };

  for (const raw of lines) {
    const line = raw.trim();

    if (line === "") {
      flush();
      continue;
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      const level = heading[1].length;
      const text = heading[2];
      const key = `h-${blocks.length}`;
      // The brief's own h1 repeats the card's title, so it is set at the same
      // size as an h2 rather than shouting over the page it sits inside.
      const className =
        level <= 2
          ? "mt-4 text-base font-semibold tracking-tight text-foreground first:mt-0"
          : "mt-3 text-sm font-semibold text-foreground first:mt-0";
      blocks.push(
        <p key={key} className={className}>
          {inline(text, key)}
        </p>,
      );
      continue;
    }

    // A horizontal rule, and a table's separator row, both just become a line.
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
      flush();
      blocks.push(<hr key={`hr-${blocks.length}`} className="my-3 border-t" />);
      continue;
    }

    const bullet = /^[-*+]\s+(.*)$/.exec(line);
    if (bullet) {
      flushParagraph();
      if (list === null || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(bullet[1]);
      continue;
    }

    const numbered = /^\d+[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      flushParagraph();
      if (list === null || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(numbered[1]);
      continue;
    }

    // Tables. Manus reaches for one whenever the brief compares teams, so this
    // is a common case rather than an exotic one, and flattening it to joined
    // cells turned the header row into a line reading
    // "Team · Pattern · Classification · Meaning", which is nonsense on its
    // own. Rows are gathered here and rendered as a real table below.
    if (line.startsWith("|") && line.endsWith("|")) {
      flushParagraph();
      flushList();
      const cells = line.slice(1, -1).split("|").map((c) => c.trim());
      // The |---|---| separator carries no content; it only marks the row
      // above as the header.
      if (cells.every((c) => /^:?-{2,}:?$/.test(c))) {
        if (table !== null) table.headerSeen = true;
        continue;
      }
      if (table === null) table = { rows: [], headerSeen: false };
      table.rows.push(cells);
      continue;
    }

    flushList();
    flushTable();
    paragraph.push(line);
  }

  flush();
  return <div className="space-y-2.5">{blocks}</div>;
}
