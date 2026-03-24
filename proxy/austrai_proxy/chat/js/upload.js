/**
 * AUSTR.AI — File Upload & Drag-Drop
 * Handles file selection, drag-drop, processing.
 * - "attach" mode → adds file as chat attachment
 * - "anonymize" mode → shows anonymization result in chat
 * - "redact" mode → shows redacted image for download
 */

import { get, set, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';
import { renderAttachments } from './chat.js';

let fileInput, dropOverlay;

export function init() {
  fileInput = document.getElementById('file-input');
  if (!fileInput) {
    console.error('[AUSTR.AI] file-input element not found!');
    return;
  }
  console.log('[AUSTR.AI] Upload module initialized');

  document.getElementById('btn-upload')?.addEventListener('click', () => {
    fileInput.dataset.mode = 'attach';
    fileInput.accept = '.pdf,.docx,.xlsx,.txt,.csv,.png,.jpg,.jpeg,.mp3,.wav,.m4a';
    fileInput.click();
  });

  fileInput.addEventListener('change', handleFiles);

  // Drag & Drop
  const app = document.getElementById('app');
  if (!app) return;

  dropOverlay = document.createElement('div');
  dropOverlay.className = 'aai-drop-overlay';
  dropOverlay.innerHTML = `<div class="aai-drop-label">${t('uploadHint')}</div>`;
  document.body.appendChild(dropOverlay);

  let dragCounter = 0;

  app.addEventListener('dragenter', (e) => { e.preventDefault(); dragCounter++; dropOverlay.classList.add('active'); });
  app.addEventListener('dragleave', (e) => { e.preventDefault(); dragCounter--; if (dragCounter <= 0) { dragCounter = 0; dropOverlay.classList.remove('active'); } });
  app.addEventListener('dragover', (e) => e.preventDefault());
  app.addEventListener('drop', (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.classList.remove('active');
    if (e.dataTransfer.files.length) processFiles([...e.dataTransfer.files], 'attach');
  });
}

function handleFiles() {
  console.log('[AUSTR.AI] File input changed, files:', fileInput.files.length);
  if (!fileInput.files.length) return;
  const mode = fileInput.dataset.mode || 'attach';
  const files = [...fileInput.files];
  fileInput.value = '';
  console.log('[AUSTR.AI] Processing', files.length, 'file(s) in mode:', mode);
  processFiles(files, mode);
}

async function processFiles(files, mode) {
  for (const file of files) {
    toast(`${t('uploadProcessing')} ${file.name}…`, 'info', 2000);
    try {
      if (mode === 'redact') {
        const result = await api.redactImage(file);
        showResultInChat(renderRedactResult(result));
        // Also add redacted image info as attachment so user can chat about it
        const attachInfo = {
          filename: result.filename,
          extracted_text: `[Geschwärztes Bild: ${result.filename}, ${result.entities_redacted || 0} Bereiche geschwärzt]`,
          anonymized_text: null,
          entity_count: result.entities_redacted || 0,
        };
        const attachments = [...get('pendingAttachments'), attachInfo];
        set('pendingAttachments', attachments);
        renderAttachments();
      } else if (mode === 'anonymize') {
        const result = await api.uploadFile(file);
        showResultInChat(renderUploadResult(result));
      } else {
        // attach mode — add to pending attachments for next chat message
        const result = await api.uploadFile(file);
        const attachments = [...get('pendingAttachments'), result];
        set('pendingAttachments', attachments);
        renderAttachments();
        toast(`${file.name} — ${result.entity_count || 0} Entitäten anonymisiert`, 'success');
      }
    } catch (err) {
      console.error('Upload error:', err);
      toast(`Upload fehlgeschlagen: ${err.message}`, 'error', 5000);
    }
  }
}

/* ---- Show result as a card in chat view ---- */

function showResultInChat(html) {
  // Switch to chat mode + chat view
  const chatBtn = document.querySelector('.aai-sidebar-nav-btn[data-mode="chat"]');
  if (chatBtn && !chatBtn.classList.contains('active')) chatBtn.click();

  set('currentView', 'chat');

  // Make sure chat-view and messages are visible
  const chatView = document.getElementById('chat-view');
  const messagesEl = document.getElementById('messages');
  if (chatView) chatView.hidden = false;
  document.getElementById('welcome-view').hidden = true;
  document.getElementById('input-area').hidden = false;

  if (messagesEl) {
    messagesEl.insertAdjacentHTML('beforeend', html);
    chatView.scrollTop = chatView.scrollHeight;
  }
}

/* ---- Render upload result card ---- */

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

function highlightAnon(text) {
  return text.replace(/\[([A-Z_]+_\d+)\]/g, '<span class="aai-anon-highlight">[$1]</span>');
}

function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function escAttr(s) { return String(s || '').replace(/"/g, '&quot;'); }
