/* Liten markdown-renderare för assistenternas svar.
 * All text escapas först, så att inget råa HTML- eller skriptinslag kan släppas igenom.
 * Stöder: rubriker, **fet**, *kursiv*, `kod`, kodblock, punkt- och nummerlistor,
 * och länkar som bara går till http(s).
 */
(function (root) {
  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function inline(text) {
    // Kod och länkar läggs i platshållare först, så att formateringen inte skriver om dem.
    const holders = [];
    const hold = (html) => {
      holders.push(html);
      return "\u0000" + (holders.length - 1) + "\u0000";
    };
    const link = (url, label) =>
      hold(`<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`);

    let t = esc(text).replace(/`([^`]+)`/g, (_, code) => hold(`<code>${code}</code>`));
    t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => link(url, label));
    t = t.replace(/(^|\s)(https?:\/\/[^\s<]+)/g, (_, pre, url) => pre + link(url, url));

    t = t.replace(/(^|\s)@([A-Za-zÅÄÖåäö][\wÅÄÖåäö]*)/g, "$1<strong>@$2</strong>");
    t = t.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");
    t = t.replace(/___([^_]+)___/g, "<strong><em>$1</em></strong>");
    t = t.replace(/\*\*_([^_*]+)_\*\*/g, "<strong><em>$1</em></strong>");
    t = t.replace(/_\*\*([^*_]+)\*\*_/g, "<strong><em>$1</em></strong>");
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    t = t.replace(/(^|[^\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>");

    return t.replace(/\u0000(\d+)\u0000/g, (_, i) => holders[Number(i)]);
  }

  function render(markdown) {
    const lines = String(markdown).replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let para = [];
    let i = 0;

    const flush = () => {
      if (para.length) {
        out.push(`<p>${para.map(inline).join("<br>")}</p>`);
        para = [];
      }
    };

    while (i < lines.length) {
      const line = lines[i];

      if (/^```/.test(line)) {
        flush();
        const code = [];
        i++;
        while (i < lines.length && !/^```/.test(lines[i])) {
          code.push(lines[i]);
          i++;
        }
        i++;
        out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
        continue;
      }

      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flush();
        const level = Math.min(heading[1].length + 2, 6);
        out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
        i++;
        continue;
      }

      if (/^\s*[-*]\s+/.test(line)) {
        flush();
        const items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
          items.push(`<li>${inline(lines[i].replace(/^\s*[-*]\s+/, ""))}</li>`);
          i++;
        }
        out.push(`<ul>${items.join("")}</ul>`);
        continue;
      }

      if (/^\s*\d+[.)]\s+/.test(line)) {
        flush();
        const items = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          items.push(`<li>${inline(lines[i].replace(/^\s*\d+[.)]\s+/, ""))}</li>`);
          i++;
        }
        out.push(`<ol>${items.join("")}</ol>`);
        continue;
      }

      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
        flush();
        const cells = (l) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
        const head = cells(line);
        i += 2;
        const rows = [];
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
          rows.push(cells(lines[i]));
          i++;
        }
        const th = head.map((c) => `<th>${inline(c)}</th>`).join("");
        const tr = rows
          .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`)
          .join("");
        out.push(`<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`);
        continue;
      }

      if (line.trim() === "") {
        flush();
        i++;
        continue;
      }

      para.push(line);
      i++;
    }
    flush();
    return out.join("");
  }

  const api = { render, escape: esc };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.renderMarkdown = render;
  }
})(typeof window !== "undefined" ? window : globalThis);
