/**
 * Get the brief out of the browser and into whatever the manager actually uses.
 *
 * A duty manager does not want a document that lives on a web page. They want
 * to send it to the GM, and the three things they will really do are paste it
 * into an email, attach a file, or print it. So there are three exports and no
 * more, each matching one of those.
 *
 * WHY NOT A .md FILE
 *
 * Markdown is the obvious download and the wrong one. A general manager who
 * opens operations-brief.md on Windows gets Notepad and a wall of asterisks and
 * pipe characters. The download is therefore a single self-contained HTML file:
 * it opens in any browser by double-clicking, it looks like a document, and
 * Ctrl+P turns it into a PDF without anybody installing anything. The markdown
 * still goes to the clipboard, because that is what pastes cleanly into mail
 * and Slack.
 *
 * Everything here is client-side. No new dependency, no server round trip, and
 * no upload of a document that is already in front of the person exporting it.
 */

/** Escape before interpolating into the exported HTML. The brief is written by
 * an external agent, and the export is a file somebody will open. */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** The same narrow grammar BriefMarkdown renders, turned into plain HTML.
 * Kept deliberately small: headings, paragraphs, bold, lists and tables. */
function markdownToHtml(source: string): string {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let table: { rows: string[][]; headerSeen: boolean } | null = null;

  const inline = (text: string) =>
    escapeHtml(text)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    out.push(`<p>${inline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!list) return;
    const tag = list.ordered ? "ol" : "ul";
    out.push(
      `<${tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${tag}>`,
    );
    list = null;
  };
  const flushTable = () => {
    if (!table || table.rows.length === 0) {
      table = null;
      return;
    }
    const [head, ...body] = table.rows;
    const hasHeader = table.headerSeen && body.length > 0;
    const rows = hasHeader ? body : table.rows;
    const thead = hasHeader
      ? `<thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead>`
      : "";
    const tbody = rows
      .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`)
      .join("");
    out.push(`<table>${thead}<tbody>${tbody}</tbody></table>`);
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
      const level = Math.min(heading[1].length + 1, 4);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
      flush();
      out.push("<hr>");
      continue;
    }
    const bullet = /^[-*+]\s+(.*)$/.exec(line);
    if (bullet) {
      flushParagraph();
      flushTable();
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(bullet[1]);
      continue;
    }
    const numbered = /^\d+[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      flushParagraph();
      flushTable();
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(numbered[1]);
      continue;
    }
    if (line.startsWith("|") && line.endsWith("|")) {
      flushParagraph();
      flushList();
      const cells = line.slice(1, -1).split("|").map((c) => c.trim());
      if (cells.every((c) => /^:?-{2,}:?$/.test(c))) {
        if (table) table.headerSeen = true;
        continue;
      }
      if (!table) table = { rows: [], headerSeen: false };
      table.rows.push(cells);
      continue;
    }
    flushList();
    flushTable();
    paragraph.push(line);
  }
  flush();
  return out.join("\n");
}

/** A standalone document: no stylesheet to fetch, no fonts to load, no
 * network. It has to look right on a laptop that has never seen this product,
 * possibly offline, possibly a year from now. */
export function briefToHtml(markdown: string, commissionedAt?: string): string {
  const written = commissionedAt
    ? new Date(commissionedAt).toLocaleString("en-IE", {
        dateStyle: "long",
        timeStyle: "short",
      })
    : null;
  return `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Hotel Operations Brief</title>
<style>
  /* An explicit background, not just a colour. color-scheme alone does not
     stop a browser in dark mode painting its own dark ground behind the page,
     and this document sets dark text, so without this it opens as dark on
     dark and is unreadable. It is a file somebody will open on a machine this
     product knows nothing about, so it commits to one look and states it. */
  :root { color-scheme: light; }
  html { background: #FFFFFF; }
  body { font: 15px/1.65 -apple-system, "Segoe UI", Inter, system-ui, sans-serif;
         color: #1A2233; background: #FFFFFF;
         max-width: 46rem; margin: 3rem auto; padding: 0 1.5rem; }
  h1, h2, h3, h4 { line-height: 1.25; margin: 1.8em 0 .6em; }
  h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; } h3 { font-size: 1.02rem; }
  p, li { color: #333B49; }
  strong { color: #1A2233; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: .94em; }
  th { text-align: left; font-size: .74rem; letter-spacing: .05em;
       text-transform: uppercase; color: #5A6472; border-bottom: 1px solid #C8CDD6;
       padding: .5em .6em; }
  td { padding: .5em .6em; vertical-align: top; border-bottom: 1px solid #E6E9ED; }
  code { background: #F1F3F6; padding: .1em .3em; border-radius: 3px; }
  .mark { display: flex; align-items: center; gap: .6rem; margin-bottom: 2.2rem; }
  .mark span { font-weight: 600; }
  .mark span em { font-style: normal; font-weight: 400; color: #5A6472; }
  footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #E6E9ED;
           font-size: .8rem; color: #5A6472; }
  @media print { body { margin: 0; max-width: none; } }
</style>
<div class="mark">
  <svg viewBox="0 0 200 200" width="26" height="26" fill="none" aria-hidden="true">
    <path d="M 142.43 57.57 A 60 60 0 1 0 65.59 149.15" stroke="#0E7C86"
          stroke-width="30" stroke-linecap="round"/>
    <path d="M 65.59 149.15 A 60 60 0 0 0 142.43 142.43" stroke="#5B4B8A"
          stroke-width="30" stroke-linecap="round"/>
  </svg>
  <span>The Coaching <em>Engine</em></span>
</div>
${markdownToHtml(markdown)}
<footer>
  Written from k-anonymised team patterns. No individual was named in the data
  this was written from.${written ? ` Commissioned ${escapeHtml(written)}.` : ""}
</footer>
</html>`;
}

function saveFile(contents: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoking immediately can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Dated, because a GM will end up with several of these in one folder. */
export function briefFilename(commissionedAt?: string, extension = "html") {
  const when = commissionedAt ? new Date(commissionedAt) : new Date();
  const stamp = Number.isNaN(when.getTime())
    ? new Date().toISOString().slice(0, 10)
    : when.toISOString().slice(0, 10);
  return `operations-brief-${stamp}.${extension}`;
}

export function downloadBrief(markdown: string, commissionedAt?: string) {
  saveFile(
    briefToHtml(markdown, commissionedAt),
    briefFilename(commissionedAt),
    "text/html;charset=utf-8",
  );
}

export async function copyBrief(markdown: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(markdown);
    return true;
  } catch {
    return false;
  }
}

/**
 * Print without printing the console around it.
 *
 * window.print() on this page would put the sidebar, the nav and the pattern
 * list on the page too. Writing the standalone document into a hidden iframe
 * and printing that gives the browser exactly the brief, which is also how the
 * viewer gets a PDF: every print dialog can save one.
 */
export function printBrief(markdown: string, commissionedAt?: string) {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(frame);
  const doc = frame.contentDocument;
  if (!doc) {
    frame.remove();
    return;
  }
  doc.open();
  doc.write(briefToHtml(markdown, commissionedAt));
  doc.close();
  const run = () => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
    setTimeout(() => frame.remove(), 60_000);
  };
  if (doc.readyState === "complete") run();
  else frame.onload = run;
}
