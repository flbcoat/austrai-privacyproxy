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

import { h, render } from 'preact';
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

async function ensureConversation() {
  if (signals.currentConversationId.value) return signals.currentConversationId.value;
  const provider = signals.provider.value;
  const model = signals.model.value;
  try {
    const { id } = await api.createConversation({ provider, model });
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

function markdownForRedact(result, filename) {
  const mimeType = result.mime_type || 'image/png';
  const dataUrl = `data:${mimeType};base64,${result.redacted_base64}`;
  return `**📷 ${filename} — geschwärzt**  \n${result.entities_redacted || 0} Bereiche entfernt.

![${filename} geschwärzt](${dataUrl})

[Geschwärzte Datei herunterladen](${dataUrl})`;
}

async function addToolResultToChat(kind, result, filename) {
  const convId = await ensureConversation();
  switchToChatView();

  const userContent = kind === 'redact'
    ? `📷 ${filename} zum Schwärzen hochgeladen`
    : `📄 ${filename} zur Anonymisierung hochgeladen`;

  const assistantContent = kind === 'redact'
    ? markdownForRedact(result, filename)
    : markdownForUpload(result, filename);

  const newMessages = [
    ...signals.messages.value,
    { role: 'user', content: userContent, meta: null },
    { role: 'assistant', content: assistantContent, meta: null },
  ];
  signals.messages.value = newMessages;
  if (convId) saveMessages(convId, newMessages);
  await refreshList();
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

/* ---- File processing ---- */

async function processFiles(files, mode) {
  for (const file of files) {
    toast(`${t('uploadProcessing')} ${file.name}…`, 'info', 2000);
    try {
      if (mode === 'redact') {
        const result = await api.redactImage(file);
        await addToolResultToChat('redact', result, file.name);
        toast(`${file.name} geschwärzt ✓ — ${result.entities_redacted || 0} Bereiche entfernt`, 'success', 5000);
      } else if (mode === 'anonymize') {
        const result = await api.uploadFile(file);
        await addToolResultToChat('anonymize', result, file.name);
        const entities = result.entity_count || 0;
        toast(`${file.name} anonymisiert ✓ — ${entities} sensible Begriff(e) erkannt`, 'success', 5000);
        if (Array.isArray(result.warnings)) {
          for (const w of result.warnings) toast(w, 'info', 9000);
        }
      } else {
        // mode === 'attach' — attach the file for the next chat message.
        // We still create a conversation so the sidebar shows the chat and
        // the user doesn't feel stranded. The attachment appears as a rich
        // card above the input; the user can then type a question and send.
        const result = await api.uploadFile(file);
        await ensureConversation();
        switchToChatView();
        signals.pendingAttachments.value = [...signals.pendingAttachments.value, result];
        renderAttachments();

        const entities = result.entity_count || 0;
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

export function init() {
  const fileInput = document.getElementById('file-input');
  if (!fileInput) {
    console.error('[AUSTR.AI] file-input element not found!');
    return;
  }

  document.getElementById('btn-upload')?.addEventListener('click', () => {
    fileInput.dataset.mode = 'attach';
    fileInput.accept = '.pdf,.docx,.xlsx,.txt,.csv,.png,.jpg,.jpeg,.mp3,.wav,.m4a';
    fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    if (!fileInput.files.length) return;
    const mode = fileInput.dataset.mode || 'attach';
    const files = [...fileInput.files];
    fileInput.value = '';
    processFiles(files, mode);
  });

  // Mount drop-overlay into document.body
  const overlayHost = document.createElement('div');
  overlayHost.id = 'aai-drop-overlay-host';
  document.body.appendChild(overlayHost);
  render(html`<${DropOverlay} />`, overlayHost);
}
