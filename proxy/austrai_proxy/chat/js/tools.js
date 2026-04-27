/**
 * AUSTR.AI — Werkzeuge View (stand-alone tools, no chat).
 *
 * Mounted into #tool-view. Shows the same tool cards as the welcome view,
 * but a tool invocation here keeps the result local: it is displayed below
 * the cards and never creates a conversation or sidebar entry. Ideal for
 * "quick-anonymise one document and be done with it" without a full chat.
 *
 * Routing:
 *   fileInput.dataset.source = 'tools'
 *   → upload.js routes the result to `signals.toolResult` (and sets
 *     `signals.toolLoading` while working) instead of creating a chat.
 *
 * Rendering:
 *   - Redacted images/PDFs are rendered as native <img> + <a target=_blank>
 *     to avoid the markdown link-parser breaking on very long data-URLs.
 *   - Anonymization results show the FULL extracted + anonymized text in a
 *     split view. The anonymized pane is an editable <textarea> so the user
 *     can still tweak individual terms before copying or downloading.
 */

import { h, render, Fragment } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, toast } from './state.js';

const html = htm.bind(h);

const SVG_TEXT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28"><path d="M4 7V4h16v3"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>';
const SVG_DOC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
const SVG_EXCEL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/></svg>';
const SVG_REDACT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>';
const SVG_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
const SVG_COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>';
const SVG_DOWNLOAD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
const SVG_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>';

function Svg({ src }) { return html`<span dangerouslySetInnerHTML=${{ __html: src }} />`; }

function handleToolClick(tool) {
  const fileInput = document.getElementById('file-input');
  if (!fileInput) return;

  if (tool === 'text-anon') {
    const chatBtn = document.querySelector('.aai-sidebar-nav-btn[data-mode="chat"]');
    if (chatBtn) chatBtn.click();
    setTimeout(() => {
      const msgInput = document.getElementById('msg-input');
      if (msgInput) {
        msgInput.focus();
        const orig = msgInput.placeholder;
        msgInput.placeholder = signals.language.value === 'de'
          ? 'Text zum Anonymisieren hier einfügen und Enter drücken …'
          : 'Paste text to anonymize and press Enter …';
        setTimeout(() => { msgInput.placeholder = orig; }, 6000);
      }
    }, 100);
    return;
  }

  fileInput.dataset.source = 'tools';
  if (tool === 'excel') {
    fileInput.accept = '.xlsx,.csv,.xls';
    fileInput.dataset.mode = 'anonymize';
  } else if (tool === 'redact') {
    fileInput.accept = '.png,.jpg,.jpeg,.tiff,.bmp,.webp,.pdf';
    fileInput.dataset.mode = 'redact';
  } else {
    fileInput.accept = '.pdf,.docx,.xlsx,.txt,.csv,.png,.jpg,.jpeg,.mp3,.wav,.m4a';
    fileInput.dataset.mode = 'anonymize';
  }
  fileInput.click();
}

/* ---- Blob-URL Helper ----
 *
 * Safari (und zunehmend auch Chrome) verweigert sehr große data-URLs in
 * neuen Tabs. `URL.createObjectURL(blob)` produziert eine echte `blob:` URL
 * ohne Länge-Limit — darum rendern wir geschwärzte Bilder/PDFs über einen
 * Blob statt über eine data-URL.
 */
function base64ToBlobUrl(base64, mimeType) {
  try {
    const bin = atob(base64 || '');
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([bytes], { type: mimeType || 'application/octet-stream' }));
  } catch (err) {
    console.error('base64ToBlobUrl failed:', err);
    return null;
  }
}

/* ---- Redact result panel ---- */

function RedactPanel({ result, filename, onClose }) {
  const isDE = signals.language.value === 'de';
  const mimeType = result.mime_type || 'image/png';
  const isPdf = mimeType === 'application/pdf';
  const count = result.entities_redacted || 0;

  // Blob-URL lebt nur so lange wie das Panel — wir erzeugen sie einmal pro
  // neues Result und revoken sie beim Unmount / neuem Result, damit der
  // Speicher nicht vollläuft.
  const [blobUrl, setBlobUrl] = useState(null);
  useEffect(() => {
    const url = base64ToBlobUrl(result.redacted_base64, mimeType);
    setBlobUrl(url);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [result]);

  function openInNewTab() {
    if (!blobUrl) return;
    const a = document.createElement('a');
    a.href = blobUrl;
    a.target = '_blank';
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function downloadFile() {
    if (!blobUrl) return;
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename.replace(/(\.[^.]+)?$/, (ext) => `_redacted${ext || '.png'}`);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  return html`
    <div class="aai-tool-result">
      <div class="aai-tool-result-header">
        <div class="aai-tool-result-title">
          <strong>${filename}</strong>
          <span class="aai-tool-result-meta">${isDE
            ? `${count} Bereich${count === 1 ? '' : 'e'} geschwärzt`
            : `${count} area${count === 1 ? '' : 's'} redacted`}</span>
        </div>
        <button class="aai-tool-result-close" onClick=${onClose}
          title=${isDE ? 'Ergebnis schließen' : 'Close result'}><${Svg} src=${SVG_CLOSE} /></button>
      </div>
      <div class="aai-tool-result-body">
        ${isPdf ? html`
          <div class="aai-redact-placeholder">
            <p>${isDE ? 'Geschwärztes PDF vorbereitet — im neuen Tab öffnen oder herunterladen.' : 'Redacted PDF ready — open in a new tab or download.'}</p>
          </div>
        ` : html`
          <div class="aai-redact-preview">
            ${blobUrl ? html`<img src=${blobUrl} alt=${filename} onClick=${openInNewTab} style="cursor: zoom-in" />` : html`<div class="aai-spinner aai-spinner--lg"></div>`}
          </div>
        `}
        <div class="aai-tool-actions">
          <button class="aai-btn aai-btn--primary" onClick=${openInNewTab} disabled=${!blobUrl}>
            <${Svg} src=${SVG_OPEN} />
            <span>${isDE ? 'Im neuen Tab öffnen' : 'Open in new tab'}</span>
          </button>
          <button class="aai-btn aai-btn--ghost" onClick=${downloadFile} disabled=${!blobUrl}>
            <${Svg} src=${SVG_DOWNLOAD} />
            <span>${isDE ? 'Herunterladen' : 'Download'}</span>
          </button>
        </div>
      </div>
    </div>
  `;
}

/* ---- Anonymization result panel ---- */

function AnonymizePanel({ result, filename, onClose }) {
  const isDE = signals.language.value === 'de';
  const [editedText, setEditedText] = useState(result.anonymized_text || '');

  // Reset editable text if a new result lands (parent component stays mounted).
  useEffect(() => {
    setEditedText(result.anonymized_text || '');
  }, [result]);

  const entities = result.entity_count || 0;
  const pages = result.pages;
  const chars = result.chars ?? (result.extracted_text || '').length;
  const mappings = result.mappings || {};
  const mapCount = Object.keys(mappings).length;
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];

  function copyToClipboard() {
    navigator.clipboard?.writeText(editedText).then(
      () => toast(isDE ? 'In Zwischenablage kopiert ✓' : 'Copied to clipboard ✓', 'success', 2000),
      () => toast(isDE ? 'Kopieren fehlgeschlagen' : 'Copy failed', 'error', 3000),
    );
  }

  function downloadTxt() {
    const blob = new Blob([editedText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename.replace(/\.[^.]+$/, '') + '_anonymized.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const meta = [
    `${isDE ? 'Typ' : 'Type'}: ${result.type || 'document'}`,
    `${isDE ? 'Entitäten' : 'Entities'}: ${entities}`,
    pages ? `${isDE ? 'Seiten' : 'Pages'}: ${pages}` : null,
    chars ? `${isDE ? 'Zeichen' : 'Chars'}: ${chars}` : null,
  ].filter(Boolean).join(' · ');

  return html`
    <div class="aai-tool-result aai-tool-result--anon">
      <div class="aai-tool-result-header">
        <div class="aai-tool-result-title">
          <strong>${filename}</strong>
          <span class="aai-tool-result-meta">${meta}</span>
        </div>
        <button class="aai-tool-result-close" onClick=${onClose}
          title=${isDE ? 'Ergebnis schließen' : 'Close result'}><${Svg} src=${SVG_CLOSE} /></button>
      </div>

      ${warnings.length ? html`
        <div class="aai-tool-warnings">
          ${warnings.map((w) => html`<div>ⓘ ${w}</div>`)}
        </div>
      ` : null}

      <div class="aai-anon-split">
        <div class="aai-anon-pane">
          <div class="aai-anon-pane-label">${isDE ? 'Original' : 'Original'}</div>
          <pre class="aai-anon-pane-content">${result.extracted_text || (isDE ? '(kein Text extrahiert)' : '(no text extracted)')}</pre>
        </div>
        <div class="aai-anon-pane">
          <div class="aai-anon-pane-label">
            <span>${isDE ? 'Anonymisiert' : 'Anonymized'}</span>
            <span class="aai-anon-pane-hint">${isDE
              ? 'editierbar — du kannst zusätzliche Begriffe ersetzen'
              : 'editable — you can replace additional terms'}</span>
          </div>
          <textarea
            class="aai-anon-pane-content aai-anon-pane-edit"
            value=${editedText}
            onInput=${(e) => setEditedText(e.target.value)}
            spellcheck="false"
          ></textarea>
        </div>
      </div>

      <div class="aai-tool-actions">
        <button class="aai-btn aai-btn--primary" onClick=${copyToClipboard}>
          <${Svg} src=${SVG_COPY} />
          <span>${isDE ? 'Anonymisierten Text kopieren' : 'Copy anonymized text'}</span>
        </button>
        <button class="aai-btn aai-btn--ghost" onClick=${downloadTxt}>
          <${Svg} src=${SVG_DOWNLOAD} />
          <span>${isDE ? 'Als .txt herunterladen' : 'Download as .txt'}</span>
        </button>
      </div>

      ${mapCount > 0 ? html`
        <details class="aai-anon-mappings">
          <summary>${isDE ? 'Zuordnungen' : 'Mappings'} (${mapCount})</summary>
          <ul>
            ${Object.entries(mappings).map(([code, orig]) => html`
              <li><code class="aai-code-orig">${orig}</code> → <code class="aai-code-anon">${code}</code></li>
            `)}
          </ul>
        </details>
      ` : null}
    </div>
  `;
}

/* ---- Loading overlay ---- */

function LoadingPanel({ loading }) {
  const isDE = signals.language.value === 'de';
  const label = loading.kind === 'redact'
    ? (isDE ? 'Schwärze sensible Bereiche …' : 'Redacting sensitive areas …')
    : (isDE ? 'Extrahiere und anonymisiere Text …' : 'Extracting and anonymizing text …');
  return html`
    <div class="aai-tool-result aai-tool-result--loading">
      <div class="aai-tool-loading">
        <div class="aai-spinner aai-spinner--lg" aria-hidden="true"></div>
        <div class="aai-tool-loading-text">
          <strong>${loading.filename}</strong>
          <span>${label}</span>
        </div>
      </div>
    </div>
  `;
}

/* ---- Main view ---- */

function ToolsView() {
  const isDE = signals.language.value === 'de';
  const result = signals.toolResult.value;
  const loading = signals.toolLoading.value;

  function closeResult() { signals.toolResult.value = null; }

  return html`
    <div class="aai-welcome aai-tools-view">
      <div class="aai-welcome-hero">
        <h1>${isDE ? 'Werkzeuge' : 'Tools'}</h1>
        <p>${isDE
          ? 'Nutze die Werkzeuge direkt, ohne einen Chat zu starten. Das Ergebnis erscheint hier unterhalb und bleibt lokal — es wird weder eine Konversation angelegt noch etwas in der Seitenleiste gespeichert.'
          : 'Use the tools standalone, without starting a chat. The result appears below and stays local — no conversation is created and nothing is saved to the sidebar.'}</p>
      </div>

      <div class="aai-welcome-tools" style="grid-template-columns: repeat(2, 1fr)">
        <div class="aai-tool-card" onClick=${() => handleToolClick('text-anon')}>
          <div class="aai-tool-card-icon aai-tool-card-icon--text"><${Svg} src=${SVG_TEXT} /></div>
          <h3>${isDE ? 'Text anonymisieren' : 'Anonymize Text'}</h3>
          <p>${isDE ? 'Führt zum Chat mit Anonymisierungs-Vorschau' : 'Switches to chat with live anonymization preview'}</p>
        </div>
        <div class="aai-tool-card" onClick=${() => handleToolClick('excel')}>
          <div class="aai-tool-card-icon" style="background:rgba(217,119,6,0.08);color:#D97706"><${Svg} src=${SVG_EXCEL} /></div>
          <h3>${isDE ? 'Excel analysieren' : 'Analyze Excel'}</h3>
          <p>${isDE ? 'Tabellen hochladen — alle Begriffe werden anonymisiert, Zahlen bleiben erhalten' : 'Upload spreadsheets — all terms anonymized, numbers preserved'}</p>
        </div>
        <div class="aai-tool-card" onClick=${() => handleToolClick('anonymize')}>
          <div class="aai-tool-card-icon aai-tool-card-icon--doc"><${Svg} src=${SVG_DOC} /></div>
          <h3>${isDE ? 'Dokument anonymisieren' : 'Anonymize Document'}</h3>
          <p>${isDE ? 'PDF, DOCX, TXT — Text wird extrahiert, anonymisiert und angezeigt' : 'PDF, DOCX, TXT — text is extracted, anonymized and shown here'}</p>
        </div>
        <div class="aai-tool-card" onClick=${() => handleToolClick('redact')}>
          <div class="aai-tool-card-icon aai-tool-card-icon--redact"><${Svg} src=${SVG_REDACT} /></div>
          <h3>${isDE ? 'Bild schwärzen' : 'Redact Image'}</h3>
          <p>${isDE ? 'Bilder und PDFs mit sensiblen Inhalten pixelgenau schwärzen' : 'Pixel-accurate redaction of sensitive content in images and PDFs'}</p>
        </div>
      </div>

      ${loading ? html`<${LoadingPanel} loading=${loading} />` : null}
      ${!loading && result && result.kind === 'redact' ? html`<${RedactPanel}
        result=${result.result} filename=${result.filename} onClose=${closeResult} />` : null}
      ${!loading && result && result.kind === 'anonymize' ? html`<${AnonymizePanel}
        result=${result.result} filename=${result.filename} onClose=${closeResult} />` : null}
    </div>
  `;
}

export function init() {
  const container = document.getElementById('tool-view');
  if (!container) return;
  render(html`<${ToolsView} />`, container);
}
