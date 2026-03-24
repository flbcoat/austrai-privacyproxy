/**
 * AUSTR.AI — Lightweight Markdown Renderer
 * Converts markdown to safe HTML (no XSS).
 * Handles: headings, bold, italic, code, lists, tables, blockquotes, links, hr.
 */

function esc(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function renderMarkdown(text) {
  if (!text) return '';
  // Split by fenced code blocks first
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map(part => {
    if (part.startsWith('```')) {
      const m = part.match(/^```(\w*)\n?([\s\S]*?)```$/);
      if (m) {
        const lang = esc(m[1]);
        const code = esc(m[2].trimEnd());
        return `<pre class="aai-codeblock" data-lang="${lang}"><div class="aai-codeblock-header"><span>${lang || 'code'}</span><button class="aai-copy-code">Copy</button></div><code>${code}</code></pre>`;
      }
    }
    return renderBlocks(part);
  }).join('');
}

function renderBlocks(text) {
  const lines = text.split('\n');
  let html = '';
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Table
    if (line.match(/^\|.+\|$/) && i + 1 < lines.length && lines[i + 1]?.match(/^\|[\s\-:|]+\|$/)) {
      const tableLines = [];
      while (i < lines.length && lines[i].match(/^\|.+\|$/)) {
        tableLines.push(lines[i]);
        i++;
      }
      html += renderTable(tableLines);
      continue;
    }

    // HR
    if (line.match(/^[-*_]{3,}\s*$/)) { html += '<hr>'; i++; continue; }

    // Heading
    const hm = line.match(/^(#{1,6})\s+(.+)/);
    if (hm) { html += `<h${hm[1].length}>${inline(hm[2])}</h${hm[1].length}>`; i++; continue; }

    // Blockquote
    if (line.match(/^>\s?/)) {
      const qLines = [];
      while (i < lines.length && lines[i].match(/^>\s?/)) {
        qLines.push(lines[i].replace(/^>\s?/, ''));
        i++;
      }
      html += `<blockquote>${qLines.map(l => inline(l)).join('<br>')}</blockquote>`;
      continue;
    }

    // Unordered list
    if (line.match(/^[\s]*[-*+]\s+/)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^[\s]*[-*+]\s+/)) {
        items.push(lines[i].replace(/^[\s]*[-*+]\s+/, ''));
        i++;
      }
      html += '<ul>' + items.map(it => `<li>${inline(it)}</li>`).join('') + '</ul>';
      continue;
    }

    // Ordered list
    if (line.match(/^\s*\d+\.\s+/)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^\s*\d+\.\s+/)) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      html += '<ol>' + items.map(it => `<li>${inline(it)}</li>`).join('') + '</ol>';
      continue;
    }

    // Empty line
    if (line.trim() === '') { i++; continue; }

    // Paragraph (collect consecutive non-special lines)
    const pLines = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].match(/^```/) &&
      !lines[i].match(/^#{1,6}\s/) &&
      !lines[i].match(/^>\s?/) &&
      !lines[i].match(/^[\s]*[-*+]\s+/) &&
      !lines[i].match(/^\s*\d+\.\s+/) &&
      !lines[i].match(/^\|.+\|$/) &&
      !lines[i].match(/^[-*_]{3,}\s*$/)
    ) {
      pLines.push(lines[i]);
      i++;
    }
    html += `<p>${pLines.map(l => inline(l)).join('<br>')}</p>`;
  }

  return html;
}

function renderTable(tableLines) {
  if (tableLines.length < 2) return tableLines.map(l => `<p>${inline(l)}</p>`).join('');
  const parseRow = line => line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
  const headers = parseRow(tableLines[0]);
  const bodyRows = tableLines.slice(2);
  let html = '<table class="aai-table"><thead><tr>';
  headers.forEach(h => { html += `<th>${inline(h)}</th>`; });
  html += '</tr></thead><tbody>';
  bodyRows.forEach(row => {
    const cells = parseRow(row);
    html += '<tr>';
    for (let j = 0; j < headers.length; j++) html += `<td>${inline(cells[j] || '')}</td>`;
    html += '</tr>';
  });
  html += '</tbody></table>';
  return html;
}

function inline(text) {
  text = esc(text);
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/_(.+?)_/g, '<em>$1</em>');
  text = text.replace(/~~(.+?)~~/g, '<del>$1</del>');
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return text;
}
