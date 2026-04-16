/**
 * AUSTR.AI — Chat Component
 * Message rendering, SSE streaming, inline anonymization preview,
 * confirmation step before sending to LLM.
 */

import { get, set, on, saveMessages, loadMessages, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';
import { renderMarkdown } from './markdown.js';
import { refreshList } from './sidebar.js';
import { getConfirmSend } from './settings.js';

const SVG = {
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
  bot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
};

let messagesEl, inputEl, sendBtn, previewBtn, previewPanel, abortHandle;
let pendingConfirmation = null; // holds text waiting for user confirmation

export function init() {
  messagesEl = document.getElementById('messages');
  inputEl = document.getElementById('msg-input');
  sendBtn = document.getElementById('btn-send');
  previewBtn = document.getElementById('btn-preview');
  previewPanel = document.getElementById('anon-preview');

  sendBtn.addEventListener('click', () => handleSend());

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      // If preview is showing, Enter confirms and sends
      if (pendingConfirmation && previewPanel && !previewPanel.hidden) {
        const text = pendingConfirmation.text;
        closePreview();
        sendConfirmed(text);
      } else {
        handleSend();
      }
    }
  });

  // Auto-resize
  inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + 'px';
    if (previewPanel && !previewPanel.hidden) {
      previewPanel.hidden = true;
      pendingConfirmation = null;
    }
  });

  if (previewBtn) previewBtn.addEventListener('click', showPreview);

  // Chip submit
  inputEl.addEventListener('chip-submit', (e) => handleSend(e.detail));

  on('messages', renderMessages);
  on('currentView', (view) => {
    if (window.__aai_showView) {
      window.__aai_showView(view === 'chat' ? 'chat-view' : 'welcome-view');
    } else {
      document.getElementById('welcome-view').hidden = view !== 'welcome';
      document.getElementById('chat-view').hidden = view !== 'chat';
    }
  });
  on('currentConversationId', (id) => {
    if (id) {
      set('messages', loadMessages(id));
      set('currentView', 'chat');
    }
  });
  on('isStreaming', (streaming) => {
    sendBtn.classList.toggle('streaming', streaming);
    sendBtn.innerHTML = streaming ? stopIcon() : sendIcon();
    inputEl.disabled = streaming;
  });

  sendBtn.innerHTML = sendIcon();
}

function sendIcon() {
  // Show shield icon when confirm-send is enabled (= "Prüfen" mode)
  if (getConfirmSend()) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
  }
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
}

function stopIcon() {
  return '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
}

/* ---- Anonymization Preview + Confirmation ---- */

async function showPreview(textOverride) {
  const text = typeof textOverride === 'string' ? textOverride : inputEl.value.trim();
  if (!text) return;

  if (!previewPanel) return;
  previewPanel.hidden = false;
  previewPanel.innerHTML = `<div class="aai-preview-loading">${SVG.shield} Anonymisierung wird geprüft…</div>`;

  try {
    const result = await api.debugTest(text);
    pendingConfirmation = { text, result };
    renderPreview(result);
  } catch (err) {
    previewPanel.innerHTML = `<div class="aai-preview-error">
      <strong>Vorschau nicht verfügbar</strong><br>
      <span style="font-size:12px;color:var(--text-muted)">${escHtml(err.message)}<br>
      Tipp: Server neu starten damit die Debug-Endpoints geladen werden.</span>
    </div>`;
  }
}

function renderPreview(r) {
  const hasChanges = r.is_changed;
  const statusColor = hasChanges ? 'var(--accent)' : 'var(--success)';
  const statusIcon = hasChanges ? SVG.shield : SVG.check;

  previewPanel.innerHTML = `
    <div class="aai-preview-header">
      <span class="aai-preview-status" style="color:${statusColor}">
        ${statusIcon}
        ${hasChanges
          ? `${r.entity_count} Begriff(e) werden anonymisiert`
          : 'Keine personenbezogenen Daten erkannt'}
      </span>
      <button class="aai-btn aai-btn--ghost aai-btn--icon aai-btn--sm" id="preview-close">&times;</button>
    </div>
    ${hasChanges ? `
      <div class="aai-preview-diff">
        <div class="aai-preview-pane">
          <div class="aai-preview-pane-label">Dein Text</div>
          <div class="aai-preview-text">${escHtml(r.original)}</div>
        </div>
        <div class="aai-preview-arrow">→</div>
        <div class="aai-preview-pane aai-preview-pane--anon">
          <div class="aai-preview-pane-label" style="color:var(--accent)">Was die KI sieht</div>
          <div class="aai-preview-text">${highlightAnon(escHtml(r.anonymized))}</div>
        </div>
      </div>
      <div class="aai-preview-entities">
        ${r.entities.map(e => `
          <span class="aai-preview-entity">
            <span class="aai-plevel aai-plevel-${e.protection_level || 2}">${e.protection_level || 2}</span>
            <span class="aai-entity-type">${escHtml(e.type)}</span>
            <span style="color:var(--danger);text-decoration:line-through">${escHtml(e.original)}</span>
            → <span style="color:var(--accent);font-family:var(--mono);font-size:12px">${escHtml(e.codename)}</span>
            <button class="aai-entity-action" data-allow-term="${escAttr(e.original)}">Allow</button>
          </span>
        `).join('')}
      </div>
    ` : ''}
    <div class="aai-preview-actions">
      <button class="aai-btn aai-btn--ghost aai-btn--sm" id="preview-edit">Bearbeiten</button>
      <button class="aai-btn aai-btn--primary aai-btn--sm" id="preview-confirm">
        ${hasChanges ? 'Absenden' : 'Absenden'} <span class="aai-key-hint">Enter</span>
      </button>
    </div>
    <div class="aai-preview-edit-hint" id="preview-edit-panel" hidden>
      <div class="aai-preview-edit-text aai-tool-selectable" id="preview-edit-text">${escHtml(r.original)}</div>
      <div class="aai-preview-edit-info">Text markieren → Begriff wird anonymisiert</div>
    </div>
  `;

  // Wire
  previewPanel.querySelector('#preview-close')?.addEventListener('click', closePreview);
  previewPanel.querySelector('#preview-edit')?.addEventListener('click', () => {
    const editPanel = previewPanel.querySelector('#preview-edit-panel');
    if (editPanel) {
      editPanel.hidden = !editPanel.hidden;
      previewPanel.querySelector('#preview-edit')?.classList.toggle('active', !editPanel.hidden);
    }
  });

  // Text selection in edit mode → add to deny-list
  const editText = previewPanel.querySelector('#preview-edit-text');
  if (editText) {
    editText.addEventListener('mouseup', async () => {
      const selection = window.getSelection();
      const selectedText = selection.toString().trim();
      if (selectedText.length < 2 || selectedText.length > 200) return;
      try {
        const config = await api.getSettings();
        const denyList = [...(config.deny_list || [])];
        if (!denyList.includes(selectedText)) {
          denyList.push(selectedText);
          await api.putSettings({ deny_list: denyList });
        }
        toast(`"${selectedText}" → Deny-List`, 'success');
        selection.removeAllRanges();
        if (pendingConfirmation) setTimeout(() => showPreview(pendingConfirmation.text), 400);
      } catch (err) { toast(err.message, 'error'); }
    });
  }
  previewPanel.querySelector('#preview-confirm')?.addEventListener('click', () => {
    const text = pendingConfirmation?.text;
    closePreview();
    if (text) sendConfirmed(text);
  });

  // Allow-list
  previewPanel.querySelectorAll('[data-allow-term]').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api.addToAllowList(btn.dataset.allowTerm);
        toast(`"${btn.dataset.allowTerm}" → Allow-List`, 'success');
        btn.textContent = '✓';
        btn.disabled = true;
        // Re-run preview after short delay
        setTimeout(() => {
          if (pendingConfirmation) showPreview(pendingConfirmation.text);
        }, 600);
      } catch (err) { toast(err.message, 'error'); }
    });
  });
}

function closePreview() {
  if (previewPanel) previewPanel.hidden = true;
  pendingConfirmation = null;
}

function highlightAnon(text) {
  return text.replace(/\[([A-Z_]+_\d+)\]/g, '<span class="aai-anon-highlight">[$1]</span>');
}

/* ---- Send Message ---- */

async function handleSend(chipText) {
  if (get('isStreaming')) {
    if (abortHandle) abortHandle.abort();
    set('isStreaming', false);
    return;
  }

  const text = typeof chipText === 'string' ? chipText : inputEl.value.trim();
  if (!text) return;

  // Two-step flow: first Enter = "Prüfen" (show preview), second Enter = "Absenden"
  // Skip for chip-submitted text since it's pre-defined
  if (typeof chipText !== 'string' && getConfirmSend()) {
    showPreview(text);
    return;
  }

  // Direct send (confirmation disabled or chip text)
  sendConfirmed(text);
}

async function sendConfirmed(text) {
  let provider = get('provider');
  let model = get('model');

  // Try to resolve from dropdowns if state is empty
  if (!provider) {
    provider = document.getElementById('sel-provider')?.value || '';
    if (provider) set('provider', provider);
  }
  if (!model) {
    model = document.getElementById('sel-model')?.value || '';
    if (model) set('model', model);
  }

  // Auto-select first configured
  if (!provider || !model) {
    const providers = get('providers');
    for (const pid of ['ollama', 'anthropic', 'openai', 'mistral', 'google']) {
      const p = providers[pid];
      if (p?.configured && p.models?.length) {
        provider = pid;
        model = p.models[0].id;
        set('provider', provider);
        set('model', model);
        break;
      }
    }
  }

  if (!provider || !model) {
    toast('Bitte zuerst einen KI-Anbieter und ein Modell konfigurieren (Einstellungen)', 'error', 5000);
    return;
  }

  inputEl.value = '';
  inputEl.style.height = 'auto';
  closePreview();

  // Ensure conversation
  let convId = get('currentConversationId');
  if (!convId) {
    try {
      const { id } = await api.createConversation({ provider, model, title: text.slice(0, 60) });
      convId = id;
      set('currentConversationId', id);
      set('currentView', 'chat');
      refreshList();
    } catch (err) { toast(err.message, 'error'); return; }
  }

  // Add user message
  const messages = [...get('messages'), { role: 'user', content: text, meta: null }];
  set('messages', messages);

  const history = messages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

  // Attachments
  const attachments = get('pendingAttachments');
  let fullMessage = text;
  if (attachments.length) {
    // Send ORIGINAL text — backend handles anonymization + rehydration in one pass
    const attachTexts = attachments.map(a => `[Datei: ${a.filename}]\n${a.extracted_text || a.anonymized_text || ''}`).join('\n\n');
    fullMessage = `${attachTexts}\n\n${text}`;
    set('pendingAttachments', []);
    renderAttachments();
  }

  // Stream
  set('isStreaming', true);
  let streamedText = '';
  let meta = null;
  const msgIdx = messages.length;
  set('messages', [...messages, { role: 'assistant', content: '', meta: null }]);

  abortHandle = api.streamMessage(
    { message: fullMessage, provider, model, history, system_prompt: '' },
    {
      onMeta(data) {
        meta = data;
        set('lastMeta', data);
        const stats = get('sessionStats');
        set('sessionStats', { ...stats, anonymized: stats.anonymized + (data.anonymized_count || 0) });
      },
      onToken(content) {
        if (content) {
          streamedText += content;
          const msgs = [...get('messages')];
          if (msgs[msgIdx]) { msgs[msgIdx] = { ...msgs[msgIdx], content: streamedText }; set('messages', msgs); }
        }
      },
      onDone(data) {
        if (data.full_response) streamedText = data.full_response;
        const msgs = [...get('messages')];
        if (msgs[msgIdx]) msgs[msgIdx] = { role: 'assistant', content: streamedText, meta, doneData: data, rawResponse: data.raw_response || null };
        if (meta && msgs[msgIdx - 1]) msgs[msgIdx - 1] = { ...msgs[msgIdx - 1], meta };
        set('messages', msgs);
        saveMessages(convId, msgs);
        set('isStreaming', false);
        refreshList();
        const stats = get('sessionStats');
        set('sessionStats', { ...stats, restored: stats.restored + (data.restored_count || 0) });
      },
      onError(error) {
        toast(error, 'error', 8000);
        const msgs = [...get('messages')];
        if (msgs[msgIdx]?.content === '') msgs.pop();
        set('messages', msgs);
        set('isStreaming', false);
      },
      onComplete() { if (get('isStreaming')) set('isStreaming', false); },
    }
  );
}

/* ---- Render Messages ---- */

function renderMessages() {
  const messages = get('messages');
  if (!messages.length) { messagesEl.innerHTML = ''; return; }

  messagesEl.innerHTML = messages.map((m, i) => {
    const isUser = m.role === 'user';
    const isLast = i === messages.length - 1;
    const isStreaming = get('isStreaming') && isLast && !isUser;

    const avatarClass = isUser ? 'aai-avatar--user' : 'aai-avatar--assistant';
    const avatarContent = isUser ? SVG.user : SVG.bot;

    let contentHtml = isUser ? escHtml(m.content) : renderMarkdown(m.content);
    if (isStreaming && !m.content) {
      contentHtml = `<div class="aai-typing"><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div></div>`;
    }

    // Privacy badge with ACTUAL entities shown
    let badgeHtml = '';
    if (isUser && m.meta) {
      if (m.meta.anonymized_count > 0) {
        const n = m.meta.anonymized_count;
        const label = n === 1 ? t('privacyBadge1') : t('privacyBadge', { n });
        const entities = (m.meta.mappings_preview || []).map(e =>
          `<span class="aai-badge-entity"><span class="aai-plevel aai-plevel-${e.protection_level || 2}">${e.protection_level || 2}</span><span class="aai-entity-type">${escHtml(e.type)}</span> ${escHtml(e.codename)}</span>`
        ).join('');
        badgeHtml = `<div class="aai-privacy-badge">${SVG.shield} ${label}</div>`;
        if (entities) {
          badgeHtml += `<div class="aai-privacy-details">${entities}</div>`;
        }
      } else {
        badgeHtml = `<div class="aai-privacy-badge aai-privacy-badge--none">${SVG.check} ${t('privacyNone')}</div>`;
      }
    }

    // Rehydration indicator on assistant messages
    let rehydrateHtml = '';
    if (!isUser && m.doneData && m.doneData.restored_count > 0) {
      const rc = m.doneData.restored_count;
      // Get anonymized count from the preceding user message's meta
      const prevMsg = i > 0 ? messages[i - 1] : null;
      const ac = prevMsg?.meta?.anonymized_count || 0;
      if (ac > 0 && rc < ac) {
        rehydrateHtml = `<div class="aai-rehydrate-badge">${SVG.check} ${rc} von ${ac} Begriff(en) in der Antwort wiederhergestellt</div>
          <div class="aai-rehydrate-hint">${ac - rc} Begriff(e) wurden anonymisiert, aber von der KI nicht in der Antwort verwendet.</div>`;
      } else {
        rehydrateHtml = `<div class="aai-rehydrate-badge">${SVG.check} ${rc} Begriff(e) wiederhergestellt</div>`;
      }
    }

    // Actions
    let actionsHtml = '';
    if (!isUser && m.content && !isStreaming) {
      const rawBtn = m.rawResponse
        ? `<button class="aai-msg-action" data-action="show-raw" data-idx="${i}">${SVG.shield} Was die KI sah</button>`
        : '';
      actionsHtml = `<div class="aai-msg-actions">
        ${rawBtn}
        <button class="aai-msg-action" data-action="copy" data-idx="${i}">${SVG.copy} ${t('copy')}</button>
      </div>`;
    }

    return `<div class="aai-message aai-message--${m.role}">
      <div class="aai-msg-inner">
        <div class="aai-avatar ${avatarClass}">${avatarContent}</div>
        <div class="aai-msg-body">
          <div class="aai-msg-text">${contentHtml}</div>
          ${badgeHtml}
          ${rehydrateHtml}
          ${actionsHtml}
        </div>
      </div>
    </div>`;
  }).join('');

  // Scroll
  const chatView = document.getElementById('chat-view');
  chatView.scrollTop = chatView.scrollHeight;

  // Wire copy code
  messagesEl.querySelectorAll('.aai-copy-code').forEach(btn => {
    btn.onclick = () => {
      const code = btn.closest('pre').querySelector('code').textContent;
      navigator.clipboard.writeText(code).then(() => { btn.textContent = '✓'; setTimeout(() => btn.textContent = 'Copy', 1500); });
    };
  });

  // Wire message actions
  messagesEl.querySelectorAll('.aai-msg-action').forEach(btn => {
    btn.onclick = () => {
      const idx = parseInt(btn.dataset.idx);
      const msg = get('messages')[idx];
      if (btn.dataset.action === 'copy' && msg) {
        navigator.clipboard.writeText(msg.content).then(() => toast(t('copied'), 'success'));
      }
      if (btn.dataset.action === 'show-raw' && msg?.rawResponse) {
        const msgEl = btn.closest('.aai-message');
        const existing = msgEl.querySelector('.aai-raw-response');
        if (existing) {
          existing.remove();
          btn.classList.remove('active');
        } else {
          const rawDiv = document.createElement('div');
          rawDiv.className = 'aai-raw-response';
          rawDiv.innerHTML = `<div class="aai-raw-header">${SVG.shield} Roh-Antwort der KI (vor Wiederherstellung)</div><div class="aai-raw-text">${escHtml(msg.rawResponse)}</div>`;
          msgEl.querySelector('.aai-msg-body').appendChild(rawDiv);
          btn.classList.add('active');
        }
      }
    };
  });
}

/* ---- Attachments ---- */

function renderAttachments() {
  const container = document.getElementById('attachments');
  const items = get('pendingAttachments');
  if (!items.length) { container.hidden = true; container.innerHTML = ''; return; }
  container.hidden = false;
  container.innerHTML = items.map((a, i) =>
    `<div class="aai-attachment"><span>${escHtml(a.filename)}</span><span class="aai-attachment-info">${a.entity_count || 0} entities</span><button class="aai-attachment-remove" data-idx="${i}">&times;</button></div>`
  ).join('');

  container.onclick = (e) => {
    const btn = e.target.closest('.aai-attachment-remove');
    if (!btn) return;
    const idx = parseInt(btn.dataset.idx);
    const items = [...get('pendingAttachments')];
    items.splice(idx, 1);
    set('pendingAttachments', items);
    renderAttachments();
  };
}

export { renderAttachments };

function escHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>'); }
function escAttr(s) { return String(s).replace(/"/g, '&quot;'); }
