/**
 * AUSTR.AI — File Upload & Drag-Drop (Preact)
 * - "attach" mode → adds file as chat attachment
 * - "anonymize" mode → shows anonymization result in chat
 * - "redact" mode → shows redacted image for download
 *
 * Drag-drop is a singleton Preact overlay rendered into document.body.
 * The circular import with chat.js (renderAttachments) will be removed
 * in Phase 10 when chat.js switches to reactive <AttachmentList>.
 */

import { h, render, Fragment } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import htm from 'htm';
import { signals, toast, batch, saveMessages } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';
import { renderAttachments } from './chat.js';
import { refreshList } from './sidebar.js';

/* ---- Conversation helpers ----
 * The home-screen tools (upload, anonymize, redact) used to dump their
 * result with insertAdjacentHTML into #messages — which Preact's
 * <MessageList> then overwrote on its next render, leaving the user with
 * the impression that "nothing happened". The fix is to treat every tool
 * invocation as a real conversation entry: create a conversation on
 * demand, push a user message describing the action and an assistant
 * message containing the formatted result into signals.messages, and let
 * Preact render everything reactively.
 */

async function ensureConversation(title) {
  if (signals.currentConversationId.value) return signals.currentConversationId.value;
  const provider = signals.provider.value;
  const model = signals.model.value;
  try {
    const { id } = await api.createConversation({ provider, model, title: title || t('newChatDefault') });
    signals.currentConversationId.value = id;
    await refreshList();
    return id;
  } catch (err) {
    console.error('Failed to create conversation:', err);
    return null;
  }
}

function switchToChatView() {
  // Activate the "Chat" sidebar nav button so the mode matches the view.
  const chatBtn = document.querySelector('.aai-sidebar-nav-btn[data-mode="chat"]');
  if (chatBtn && !chatBtn.classList.contains('active')) chatBtn.click();
  signals.currentView.value = 'chat';
}

function ellipsize(s, n) {
  const str = String(s ?? '').trim();
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function markdownForUpload(result, filename) {
  const entities = result.entity_count || 0;
  const pages = result.pages ? ` · Seiten: ${result.pages}` : '';
  const chars = result.chars ? ` · Zeichen: ${result.chars}` : '';
  const warnings = Array.isArray(result.warnings) && result.warnings.length
    ? `\n\n> ⓘ ${result.warnings.join(' · ')}`
    : '';
  const header = `**📄 ${filename}**  \nTyp: ${result.type || 'document'} · Entitäten: ${entities}${pages}${chars}${warnings}`;
  const original = ellipsize(result.extracted_text, 600);
  const anonymized = ellipsize(result.anonymized_text, 600);
  const mappings = result.mappings && Object.keys(result.mappings).length
    ? '\n\n**Anonymisierungs-Zuordnungen:**\n' +
      Object.entries(result.mappings)
        .slice(0, 20)
        .map(([code, orig]) => `- \`${orig}\` → \`${code}\``)
        .join('\n')
    : '';
  return `${header}

**Original (Auszug):**
\`\`\`
${original || '(kein Text extrahiert)'}
\`\`\`

**Anonymisiert (so sieht die KI den Inhalt):**
\`\`\`
${anonymized || '(leer)'}
\`\`\`${mappings}`;
}

// NOTE: `markdownForRedact` wurde in 3.1.10 entfernt. Früher hat es einen
// Markdown-String mit data:-URL für das geschwärzte Bild erzeugt — das
// wurde durch den markdown.js Link-Parser geschleust und produzierte
// kaputte Links im Chat (Safari öffnet große data-URLs nicht im neuen
// Tab). Der neue Flow nutzt `msg.attachment = { kind: 'redact', base64 }`
// und der MessageBubble-Renderer erzeugt daraus eine Blob-URL. Siehe
// chat.js::RedactEmbed.

async function addToolResultToChat(kind, result, filename) {
  // Conversation wird mit dem Dateinamen (gekürzt) betitelt — so ist der
  // Sidebar-Eintrag sofort aussagekräftig ("Rechnung-2026.pdf") statt "New Chat".
  const shortName = filename.length > 60 ? filename.slice(0, 57) + '…' : filename;
  const convId = await ensureConversation(shortName);
  switchToChatView();

  const userContent = kind === 'redact'
    ? `📷 ${filename} zum Schwärzen hochgeladen`
    : `📄 ${filename} zur Anonymisierung hochgeladen`;

  let assistantMsg;
  if (kind === 'redact') {
    // Redact-Ergebnisse als strukturiertes Attachment speichern — der
    // MessageBubble-Renderer erkennt `attachment.kind === 'redact'` und
    // erzeugt daraus ein <img> + Download-Button mit Blob-URL. So bleibt
    // die data-URL nicht im Markdown stecken (wo Safari sie in neuen Tabs
    // blockiert).
    assistantMsg = {
      role: 'assistant',
      content: `**📷 ${filename}** — ${result.entities_redacted || 0} Bereiche geschwärzt`,
      meta: null,
      attachment: {
        kind: 'redact',
        base64: result.redacted_base64,
        mimeType: result.mime_type || 'image/png',
        filename,
        entitiesRedacted: result.entities_redacted || 0,
      },
    };
  } else {
    assistantMsg = {
      role: 'assistant',
      content: markdownForUpload(result, filename),
      meta: null,
    };
  }

  const newMessages = [
    ...signals.messages.value,
    { role: 'user', content: userContent, meta: null },
    assistantMsg,
  ];
  signals.messages.value = newMessages;
  if (convId) saveMessages(convId, newMessages);
  await refreshList();
}

/* Redact im Chat mit Loading-Placeholder ----
 * Fügt User-Message + Loading-Assistant-Message in den Chat ein BEVOR der
 * Server-Call startet, damit der User sofort sieht dass etwas passiert.
 * Beim Erfolg wird der Placeholder durch das echte Redact-Attachment
 * ersetzt; bei Fehler wird er entfernt und die Exception propagiert. */
async function redactInChat(file) {
  const shortName = file.name.length > 60 ? file.name.slice(0, 57) + '…' : file.name;
  const convId = await ensureConversation(shortName);
  switchToChatView();

  const tempId = `tmp-redact-${Date.now()}-${Math.random()}`;
  const userMsg = { role: 'user', content: `📷 ${file.name} zum Schwärzen hochgeladen`, meta: null };
  const placeholder = {
    role: 'assistant',
    content: '',
    meta: null,
    _tempId: tempId,
    attachment: { kind: 'redact', filename: file.name, loading: true },
  };
  signals.messages.value = [...signals.messages.value, userMsg, placeholder];

  try {
    const result = await api.redactImage(file);
    const finalMsg = {
      role: 'assistant',
      content: `**📷 ${file.name}** — ${result.entities_redacted || 0} Bereiche geschwärzt`,
      meta: null,
      attachment: {
        kind: 'redact',
        base64: result.redacted_base64,
        mimeType: result.mime_type || 'image/png',
        filename: file.name,
        entitiesRedacted: result.entities_redacted || 0,
      },
    };
    // Guard: falls der User während des Redact-Uploads die Konversation
    // gewechselt hat (z.B. "Neuer Chat" geklickt), darf die Ersetzung
    // nicht in die aktuelle UI-View geschrieben werden — das würde der
    // neuen Konversation einen falschen Eintrag spendieren.
    const stillActive = convId === signals.currentConversationId.value;
    if (stillActive) {
      const updated = signals.messages.value.map((m) => m._tempId === tempId ? finalMsg : m);
      signals.messages.value = updated;
      if (convId) saveMessages(convId, updated);
    } else if (convId) {
      // Konversation wurde gewechselt: Nachricht dennoch für die alte
      // Konversation persistieren, damit der User sie findet wenn er
      // zurückwechselt. Wir können die cached messages aus dem alten
      // Closure nicht nutzen (wurden überschrieben), also laden wir
      // den aktuellen Stand und hängen die finale Message an.
      try {
        const cached = JSON.parse(localStorage.getItem(`aai_msg_${convId}`) || '[]');
        const filtered = cached.filter((m) => m._tempId !== tempId);
        filtered.push(finalMsg);
        saveMessages(convId, filtered);
      } catch { /* localStorage nicht verfügbar — DB-Record bleibt */ }
    }
    await refreshList();
    return result;
  } catch (err) {
    // Placeholder auch bei Fehler nur entfernen wenn wir noch in der
    // ursprünglichen Konversation sind — sonst lassen wir die aktuelle
    // View unberührt.
    if (convId === signals.currentConversationId.value) {
      const updated = signals.messages.value.filter((m) => m._tempId !== tempId);
      signals.messages.value = updated;
    }
    throw err;
  }
}

const html = htm.bind(h);

/* ---- Drop Overlay Component ---- */

function DropOverlay() {
  const [active, setActive] = useState(false);

  useEffect(() => {
    const app = document.getElementById('app');
    if (!app) return;

    let dragCounter = 0;

    function onDragEnter(e) {
      e.preventDefault();
      dragCounter++;
      setActive(true);
    }
    function onDragLeave(e) {
      e.preventDefault();
      dragCounter--;
      if (dragCounter <= 0) { dragCounter = 0; setActive(false); }
    }
    function onDragOver(e) { e.preventDefault(); }
    function onDrop(e) {
      e.preventDefault();
      dragCounter = 0;
      setActive(false);
      if (e.dataTransfer.files.length) {
        processFiles([...e.dataTransfer.files], 'attach');
      }
    }

    app.addEventListener('dragenter', onDragEnter);
    app.addEventListener('dragleave', onDragLeave);
    app.addEventListener('dragover', onDragOver);
    app.addEventListener('drop', onDrop);

    return () => {
      app.removeEventListener('dragenter', onDragEnter);
      app.removeEventListener('dragleave', onDragLeave);
      app.removeEventListener('dragover', onDragOver);
      app.removeEventListener('drop', onDrop);
    };
  }, []);

  return html`
    <div class=${`aai-drop-overlay${active ? ' active' : ''}`}>
      <div class="aai-drop-label">${t('uploadHint')}</div>
    </div>
  `;
}

/* ---- File processing ----
 *
 * `source` controls where the result lands:
 *   - 'chat'  (default): create/reuse a conversation and insert tool-user +
 *                        tool-assistant messages, switch to chat-view.
 *   - 'tools': render the result below the Werkzeuge tool cards via
 *              `signals.toolResult`. No conversation is created and nothing
 *              is written to the sidebar.
 */

function publishToolResult(kind, result, filename) {
  // Werkzeuge-Tab rendert das Ergebnis selbst (tools.js) — wir übergeben
  // nur die Rohdaten, damit das Panel voll interaktiv sein kann (voller
  // Text, editierbare Textarea, Copy/Download-Buttons, echtes <img>).
  signals.toolResult.value = { kind, result, filename };
}

async function processFiles(files, mode, source = 'chat') {
  for (const file of files) {
    const useToolsPanel = source === 'tools' && (mode === 'redact' || mode === 'anonymize');
    if (useToolsPanel) {
      signals.toolResult.value = null;
      signals.toolLoading.value = { kind: mode, filename: file.name };
    } else {
      toast(`${t('uploadProcessing')} ${file.name}…`, 'info', 2000);
    }
    try {
      if (mode === 'redact') {
        if (source === 'tools') {
          const result = await api.redactImage(file);
          publishToolResult('redact', result, file.name);
          toast(`${file.name} geschwärzt ✓ — ${result.entities_redacted || 0} Bereiche entfernt`, 'success', 5000);
        } else {
          // Chat-Flow: redactInChat fügt selbst einen Loading-Placeholder
          // ein und ersetzt ihn beim Erfolg — so sieht der User sofort,
          // dass etwas passiert, und muss nicht blind auf den Toast warten.
          const result = await redactInChat(file);
          toast(`${file.name} geschwärzt ✓ — ${result.entities_redacted || 0} Bereiche entfernt`, 'success', 5000);
        }
      } else if (mode === 'anonymize') {
        const result = await api.uploadFile(file);
        if (source === 'tools') publishToolResult('anonymize', result, file.name);
        else await addToolResultToChat('anonymize', result, file.name);
        const entities = result.entity_count || 0;
        toast(`${file.name} anonymisiert ✓ — ${entities} sensible Begriff(e) erkannt`, 'success', 5000);
        if (Array.isArray(result.warnings)) {
          for (const w of result.warnings) toast(w, 'info', 9000);
        }
      } else {
        // mode === 'attach' — attach the file for the next chat message.
        // We still create a conversation so the sidebar shows the chat and
        // the user doesn't feel stranded.
        //
        // Placeholder-Attachment: Der User sieht sofort eine Karte mit
        // Spinner + Dateiname während der Server PDF-Extraktion und
        // Anonymisierung laufen lässt (kann bei großen PDFs 10-30s dauern).
        // Beim Erfolg ersetzen wir den Placeholder durch das echte Result.
        const shortName = file.name.length > 60 ? file.name.slice(0, 57) + '…' : file.name;
        await ensureConversation(shortName);
        switchToChatView();

        const tempId = `tmp-attach-${Date.now()}-${Math.random()}`;
        const placeholder = { _tempId: tempId, filename: file.name, loading: true };
        signals.pendingAttachments.value = [...signals.pendingAttachments.value, placeholder];
        renderAttachments();

        let result;
        try {
          result = await api.uploadFile(file);
        } catch (err) {
          signals.pendingAttachments.value = signals.pendingAttachments.value.filter((a) => a._tempId !== tempId);
          throw err;
        }
        signals.pendingAttachments.value = signals.pendingAttachments.value.map((a) =>
          a._tempId === tempId ? result : a
        );
        renderAttachments();

        // Privacy-Shield sofort reagieren lassen: die Anonymisierung ist hier
        // bereits passiert (im Upload-Response), auch wenn noch keine Chat-
        // Nachricht gesendet wurde. Der User soll sehen "X Begriffe erkannt"
        // im Header-Badge, ohne erst eine Frage abschicken zu müssen.
        const entities = result.entity_count || 0;
        if (entities > 0) {
          const total = (signals.lastMeta.value?.anonymized_count || 0) + entities;
          const existing = signals.lastMeta.value?.mappings_preview || {};
          signals.lastMeta.value = {
            ...(signals.lastMeta.value || {}),
            anonymized_count: total,
            mappings_preview: { ...existing, ...(result.mappings || {}) },
          };
        }
        const chars = result.chars || (result.extracted_text || '').length;
        let status;
        if (chars === 0) {
          status = 'kein Text erkannt (Datei evtl. leer oder Bild-PDF)';
        } else if (entities > 0) {
          status = `${entities} sensible Begriff(e) erkannt — werden beim Absenden anonymisiert`;
        } else {
          status = 'keine sensiblen Daten erkannt, wird unverändert mitgesendet';
        }
        toast(`${file.name} hochgeladen ✓ — ${status}`, 'success', 6000);
        if (Array.isArray(result.warnings)) {
          for (const w of result.warnings) toast(w, 'info', 9000);
        }
      }
    } catch (err) {
      console.error('Upload error:', err);
      toast(`Upload fehlgeschlagen: ${err.message}`, 'error', 5000);
    } finally {
      if (useToolsPanel) signals.toolLoading.value = null;
    }
  }
}

/* ---- Show result card in chat view ----
 * Imperative DOM insertion. Will move into a reactive <MessageList>
 * (Phase 10) once chat.js is migrated.
 */
function showResultInChat(cardHtml) {
  const chatBtn = document.querySelector('.aai-sidebar-nav-btn[data-mode="chat"]');
  if (chatBtn && !chatBtn.classList.contains('active')) chatBtn.click();

  signals.currentView.value = 'chat';

  const chatView = document.getElementById('chat-view');
  const messagesEl = document.getElementById('messages');
  const welcomeView = document.getElementById('welcome-view');
  const inputArea = document.getElementById('input-area');
  if (chatView) chatView.hidden = false;
  if (welcomeView) welcomeView.hidden = true;
  if (inputArea) inputArea.hidden = false;

  if (messagesEl) {
    messagesEl.insertAdjacentHTML('beforeend', cardHtml);
    chatView.scrollTop = chatView.scrollHeight;
  }
}

/* ---- Card HTML renderers (still string templates; will become Preact in Phase 10) ---- */

function highlightAnon(text) {
  return text.replace(/\[([A-Z_]+_\d+)\]/g, '<span class="aai-anon-highlight">[$1]</span>');
}
function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function escAttr(s) { return String(s || '').replace(/"/g, '&quot;'); }

function renderUploadResult(result) {
  return `
    <div class="aai-upload-result">
      <div class="aai-upload-result-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        ${esc(result.filename)}
      </div>
      <div class="aai-upload-diff">
        <div class="aai-upload-pane">
          <div class="aai-upload-pane-label">Original</div>
          <div style="white-space:pre-wrap;word-break:break-word">${esc((result.extracted_text || '').slice(0, 800))}</div>
        </div>
        <div class="aai-upload-pane" style="border:1px solid var(--accent-border)">
          <div class="aai-upload-pane-label" style="color:var(--accent)">Anonymisiert</div>
          <div style="white-space:pre-wrap;word-break:break-word">${highlightAnon(esc((result.anonymized_text || '').slice(0, 800)))}</div>
        </div>
      </div>
      ${result.entity_count ? `
        <div style="padding:8px 0;display:flex;flex-wrap:wrap;gap:4px">
          ${Object.entries(result.mappings || {}).map(([code, orig]) =>
            `<span class="aai-tag"><span style="color:var(--danger);text-decoration:line-through;font-size:11px">${esc(orig)}</span> → <span style="color:var(--accent);font-family:var(--mono);font-size:11px">${esc(code)}</span></span>`
          ).join('')}
        </div>
      ` : ''}
      <div class="aai-upload-stats">
        Typ: <span>${result.type || '?'}</span>
        &nbsp;|&nbsp; Entitäten: <span>${result.entity_count || 0}</span>
        ${result.pages ? ` &nbsp;|&nbsp; Seiten: <span>${result.pages}</span>` : ''}
        ${result.chars ? ` &nbsp;|&nbsp; Zeichen: <span>${result.chars}</span>` : ''}
      </div>
    </div>
  `;
}

function renderRedactResult(result) {
  const mimeType = result.mime_type || 'image/png';
  const dataUrl = `data:${mimeType};base64,${result.redacted_base64}`;

  return `
    <div class="aai-upload-result">
      <div class="aai-upload-result-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
        Bild geschwärzt: ${esc(result.filename)}
      </div>
      <div style="text-align:center;margin:12px 0">
        <img src="${dataUrl}" alt="Geschwärzt" style="max-width:100%;border-radius:var(--r-md);border:1px solid var(--border)" />
      </div>
      <div class="aai-upload-stats">
        Entitäten geschwärzt: <span>${result.entities_redacted || 0}</span>
      </div>
      <div style="margin-top:8px">
        <a href="${dataUrl}" download="${escAttr(result.filename)}" class="aai-btn aai-btn--primary aai-btn--sm">Download</a>
      </div>
    </div>
  `;
}

/* ---- Init ---- */

/* ---- Upload-Popover Menü (Paperclip → Auswahl) ----
 *
 * Beim Klick auf die Büroklammer im Chat-Input öffnet sich ein kleines Menü
 * mit zwei Aktionen:
 *   1. "Datei anhängen"  → mode='attach' (PDF/DOCX/XLSX/TXT/Bild/Audio)
 *                          Datei wird anonymisiert, als Attachment
 *                          angehängt und der User stellt dann eine Frage.
 *   2. "Bild/PDF schwärzen" → mode='redact' (PNG/JPG/PDF)
 *                          Sensible Bereiche werden pixelgenau geschwärzt,
 *                          Ergebnis als Chat-Message mit Inline-Vorschau +
 *                          Download-Button.
 *
 * Schließt bei Klick außerhalb oder Escape. Positionierung absolut
 * oberhalb der Büroklammer via CSS.
 */
function UploadMenu() {
  const isDE = signals.language.value === 'de';
  const open = signals.uploadMenuOpen.value;

  useEffect(() => {
    if (!open) return undefined;
    function onDocClick(e) {
      if (e.target.closest('.aai-upload-menu') || e.target.closest('#btn-upload')) return;
      signals.uploadMenuOpen.value = false;
    }
    function onKey(e) { if (e.key === 'Escape') signals.uploadMenuOpen.value = false; }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!open) return null;

  function pick(mode, accept) {
    signals.uploadMenuOpen.value = false;
    const fileInput = document.getElementById('file-input');
    if (!fileInput) return;
    fileInput.dataset.mode = mode;
    fileInput.accept = accept;
    delete fileInput.dataset.source;
    fileInput.click();
  }

  return html`
    <div class="aai-upload-menu" role="menu">
      <button class="aai-upload-menu-item" role="menuitem"
        onClick=${() => pick('attach', '.pdf,.docx,.xlsx,.txt,.csv,.png,.jpg,.jpeg,.mp3,.wav,.m4a')}>
        <span class="aai-upload-menu-icon" dangerouslySetInnerHTML=${{ __html:
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>'
        }} />
        <div class="aai-upload-menu-body">
          <strong>${isDE ? 'Datei anhängen' : 'Attach file'}</strong>
          <span>${isDE
            ? 'PDF, DOCX, Excel, TXT, Bild, Audio — wird anonymisiert und kann danach befragt werden'
            : 'PDF, DOCX, Excel, TXT, image, audio — anonymized first, then chat about it'}</span>
        </div>
      </button>
      <button class="aai-upload-menu-item" role="menuitem"
        onClick=${() => pick('redact', '.png,.jpg,.jpeg,.tiff,.bmp,.webp,.pdf')}>
        <span class="aai-upload-menu-icon" dangerouslySetInnerHTML=${{ __html:
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
        }} />
        <div class="aai-upload-menu-body">
          <strong>${isDE ? 'Bild / PDF schwärzen' : 'Redact image / PDF'}</strong>
          <span>${isDE
            ? 'Sensible Bereiche pixelgenau entfernen — Ergebnis als Vorschau und Download'
            : 'Pixel-accurate redaction — result as preview and download'}</span>
        </div>
      </button>
    </div>
  `;
}

export function init() {
  const fileInput = document.getElementById('file-input');
  if (!fileInput) {
    console.error('[AUSTR.AI] file-input element not found!');
    return;
  }

  document.getElementById('btn-upload')?.addEventListener('click', (e) => {
    e.stopPropagation();
    signals.uploadMenuOpen.value = !signals.uploadMenuOpen.value;
  });

  fileInput.addEventListener('change', () => {
    if (!fileInput.files.length) return;
    const mode = fileInput.dataset.mode || 'attach';
    const source = fileInput.dataset.source || 'chat';
    const files = [...fileInput.files];
    fileInput.value = '';
    // Reset the source flag after consumption so a subsequent chat-side
    // upload does not accidentally inherit 'tools' routing.
    delete fileInput.dataset.source;
    processFiles(files, mode, source);
  });

  // Mount drop-overlay into document.body
  const overlayHost = document.createElement('div');
  overlayHost.id = 'aai-drop-overlay-host';
  document.body.appendChild(overlayHost);
  render(html`<${DropOverlay} />`, overlayHost);

  // Mount Upload-Popover (relative zum .aai-input-row)
  const inputRow = document.querySelector('.aai-input-row');
  if (inputRow) {
    const menuHost = document.createElement('div');
    menuHost.id = 'aai-upload-menu-host';
    menuHost.className = 'aai-upload-menu-host';
    inputRow.appendChild(menuHost);
    render(html`<${UploadMenu} />`, menuHost);
  }
}
