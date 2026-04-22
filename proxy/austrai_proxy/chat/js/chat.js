/**
 * AUSTR.AI — Chat View (Preact)
 *
 * Three separate Preact render trees, one shared signal store:
 *   - <MessageList />      mounted into #messages
 *   - <PreviewPanel />     mounted into #anon-preview (above the input)
 *   - <AttachmentList />   mounted into #attachments (above the preview)
 *
 * State flows through `signals.messages`, `signals.pendingAttachments`,
 * and `signals.pendingPreview`. Side-effect controllers (send, abort,
 * showPreview) live at module scope and read/write those signals directly.
 */

import { h, render, Fragment } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, batch, saveMessages, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';
import { renderMarkdown } from './markdown.js';
import { refreshList } from './sidebar.js';
import { getConfirmSend } from './settings.js';

const html = htm.bind(h);

/* ---- Icons ---- */

const SVG_USER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
const SVG_BOT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const SVG_COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>';
const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const SVG_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
const SVG_SEND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
const SVG_STOP = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';

function highlightAnon(html) {
  return html.replace(/\[([A-Z_]+_\d+)\]/g, '<span class="aai-anon-highlight">[$1]</span>');
}
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
}

/* ---- Module-scope state for side-effect controllers ---- */

let abortHandle = null;

/* ---- Message bubble ---- */

function MessageBubble({ msg, prevMsg, isLast, isStreaming }) {
  const [showRaw, setShowRaw] = useState(false);
  const isUser = msg.role === 'user';
  const showTyping = isStreaming && isLast && !isUser && !msg.content;

  async function copyText() {
    try {
      await navigator.clipboard.writeText(msg.content);
      toast(t('copied'), 'success');
    } catch { /* clipboard unavailable */ }
  }

  let badge = null;
  if (isUser && msg.meta) {
    if (msg.meta.anonymized_count > 0) {
      const n = msg.meta.anonymized_count;
      const label = n === 1 ? t('privacyBadge1') : t('privacyBadge', { n });
      const entities = msg.meta.mappings_preview || [];
      badge = html`
        <${Fragment}>
          <div class="aai-privacy-badge">
            <span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} /> ${label}
          </div>
          ${entities.length ? html`
            <div class="aai-privacy-details">
              ${entities.map((e, i) => html`
                <span key=${i} class="aai-badge-entity">
                  <span class=${`aai-plevel aai-plevel-${e.protection_level || 2}`}>${e.protection_level || 2}</span>
                  <span class="aai-entity-type">${e.type}</span>
                  ${' '}${e.codename}
                </span>
              `)}
            </div>
          ` : null}
        <//>
      `;
    } else {
      badge = html`
        <div class="aai-privacy-badge aai-privacy-badge--none">
          <span dangerouslySetInnerHTML=${{ __html: SVG_CHECK }} /> ${t('privacyNone')}
        </div>
      `;
    }
  }

  let rehydrate = null;
  if (!isUser && msg.doneData && msg.doneData.restored_count > 0) {
    const rc = msg.doneData.restored_count;
    const ac = prevMsg?.meta?.anonymized_count || 0;
    if (ac > 0 && rc < ac) {
      rehydrate = html`
        <${Fragment}>
          <div class="aai-rehydrate-badge">
            <span dangerouslySetInnerHTML=${{ __html: SVG_CHECK }} /> ${rc} von ${ac} Begriff(en) in der Antwort wiederhergestellt
          </div>
          <div class="aai-rehydrate-hint">${ac - rc} Begriff(e) wurden anonymisiert, aber von der KI nicht in der Antwort verwendet.</div>
        <//>
      `;
    } else {
      rehydrate = html`
        <div class="aai-rehydrate-badge">
          <span dangerouslySetInnerHTML=${{ __html: SVG_CHECK }} /> ${rc} Begriff(e) wiederhergestellt
        </div>
      `;
    }
  }

  const avatarClass = isUser ? 'aai-avatar--user' : 'aai-avatar--assistant';
  const avatarSvg = isUser ? SVG_USER : SVG_BOT;
  const contentHtml = showTyping
    ? '<div class="aai-typing"><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div></div>'
    : (isUser ? esc(msg.content) : renderMarkdown(msg.content));

  return html`
    <div class=${`aai-message aai-message--${msg.role}`}>
      <div class="aai-msg-inner">
        <div class=${`aai-avatar ${avatarClass}`} dangerouslySetInnerHTML=${{ __html: avatarSvg }} />
        <div class="aai-msg-body">
          <div class="aai-msg-text" dangerouslySetInnerHTML=${{ __html: contentHtml }} />
          ${badge}
          ${rehydrate}
          ${!isUser && msg.content && !showTyping ? html`
            <div class="aai-msg-actions">
              ${msg.rawResponse ? html`
                <button class=${`aai-msg-action${showRaw ? ' active' : ''}`} onClick=${() => setShowRaw(!showRaw)}>
                  <span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} /> Was die KI sah
                </button>
              ` : null}
              <button class="aai-msg-action" onClick=${copyText}>
                <span dangerouslySetInnerHTML=${{ __html: SVG_COPY }} /> ${t('copy')}
              </button>
            </div>
          ` : null}
          ${showRaw && msg.rawResponse ? html`
            <div class="aai-raw-response">
              <div class="aai-raw-header">
                <span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} /> Roh-Antwort der KI (vor Wiederherstellung)
              </div>
              <div class="aai-raw-text" dangerouslySetInnerHTML=${{ __html: esc(msg.rawResponse) }} />
            </div>
          ` : null}
        </div>
      </div>
    </div>
  `;
}

/* ---- Message list ---- */

function MessageList() {
  const messages = signals.messages.value;
  const isStreaming = signals.isStreaming.value;

  useEffect(() => {
    const chatView = document.getElementById('chat-view');
    if (chatView) chatView.scrollTop = chatView.scrollHeight;
  }, [messages.length, messages[messages.length - 1]?.content]);

  return html`
    <${Fragment}>
      ${messages.map((m, i) => html`
        <${MessageBubble}
          key=${i}
          msg=${m}
          prevMsg=${i > 0 ? messages[i - 1] : null}
          isLast=${i === messages.length - 1}
          isStreaming=${isStreaming}
        />
      `)}
    <//>
  `;
}

/* ---- Anonymization preview panel ---- */

function PreviewPanel() {
  const pending = signals.pendingPreview.value;
  const [editMode, setEditMode] = useState(false);
  const [slowLoad, setSlowLoad] = useState(false);

  useEffect(() => { if (!pending) setEditMode(false); }, [pending]);

  // Show an extended hint after 3 s: the first anonymization call can take
  // ~60 s while GLiNER + spaCy load. Without this the user sees a silent
  // spinner and assumes the UI is broken.
  useEffect(() => {
    if (!pending || pending.result) { setSlowLoad(false); return; }
    const id = setTimeout(() => setSlowLoad(true), 3000);
    return () => clearTimeout(id);
  }, [pending, pending?.result]);

  if (!pending) return null;
  const { text, result } = pending;

  if (!result) {
    return html`
      <div class="aai-preview-loading">
        <span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} />
        ${slowLoad
          ? 'Anonymisierung wird geprüft… (KI-Modelle werden beim ersten Mal geladen, bis zu 1 Minute)'
          : 'Anonymisierung wird geprüft…'}
      </div>
    `;
  }

  const hasChanges = result.is_changed;
  const statusColor = hasChanges ? 'var(--accent)' : 'var(--success)';

  async function handleAllowTerm(term) {
    try {
      await api.addToAllowList(term);
      toast(`"${term}" → Allow-List`, 'success');
    } catch (err) { toast(err.message, 'error'); }
  }

  async function handleSelectionDeny() {
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
    } catch (err) { toast(err.message, 'error'); }
  }

  return html`
    <${Fragment}>
      <div class="aai-preview-header">
        <span class="aai-preview-status" style=${`color:${statusColor}`}>
          <span dangerouslySetInnerHTML=${{ __html: hasChanges ? SVG_SHIELD : SVG_CHECK }} />
          ${hasChanges
            ? `${result.entity_count} Begriff(e) werden anonymisiert`
            : 'Keine personenbezogenen Daten erkannt'}
        </span>
        <button class="aai-btn aai-btn--ghost aai-btn--icon aai-btn--sm" onClick=${closePreview}>×</button>
      </div>

      ${hasChanges ? html`
        <div class="aai-preview-diff">
          <div class="aai-preview-pane">
            <div class="aai-preview-pane-label">Dein Text</div>
            <div class="aai-preview-text">${result.original}</div>
          </div>
          <div class="aai-preview-arrow">→</div>
          <div class="aai-preview-pane aai-preview-pane--anon">
            <div class="aai-preview-pane-label" style="color:var(--accent)">Was die KI sieht</div>
            <div
              class="aai-preview-text"
              dangerouslySetInnerHTML=${{ __html: highlightAnon(esc(result.anonymized)) }}
            />
          </div>
        </div>
        <div class="aai-preview-entities">
          ${result.entities.map((e, i) => html`
            <span key=${i} class="aai-preview-entity">
              <span class=${`aai-plevel aai-plevel-${e.protection_level || 2}`}>${e.protection_level || 2}</span>
              <span class="aai-entity-type">${e.type}</span>
              <span style="color:var(--danger);text-decoration:line-through">${e.original}</span>
              ${' → '}
              <span style="color:var(--accent);font-family:var(--mono);font-size:12px">${e.codename}</span>
              <button class="aai-entity-action" onClick=${() => handleAllowTerm(e.original)}>Allow</button>
            </span>
          `)}
        </div>
      ` : null}

      <div class="aai-preview-actions">
        <button class=${`aai-btn aai-btn--ghost aai-btn--sm${editMode ? ' active' : ''}`} onClick=${() => setEditMode(!editMode)}>Bearbeiten</button>
        <button class="aai-btn aai-btn--primary aai-btn--sm" onClick=${() => sendConfirmed(text)}>
          Absenden <span class="aai-key-hint">Enter</span>
        </button>
      </div>

      ${editMode ? html`
        <div class="aai-preview-edit-hint">
          <div class="aai-preview-edit-text aai-tool-selectable" onMouseUp=${handleSelectionDeny}>${result.original}</div>
          <div class="aai-preview-edit-info">Text markieren → Begriff wird anonymisiert</div>
        </div>
      ` : null}
    <//>
  `;
}

/* ---- Attachment chips ---- */

function AttachmentList() {
  const items = signals.pendingAttachments.value;
  if (!items.length) return null;

  function removeAt(idx) {
    const next = [...items];
    next.splice(idx, 1);
    signals.pendingAttachments.value = next;
  }

  return html`
    <${Fragment}>
      ${items.map((a, i) => html`
        <div key=${i} class="aai-attachment">
          <span>${a.filename}</span>
          <span class="aai-attachment-info">${a.entity_count || 0} entities</span>
          <button class="aai-attachment-remove" onClick=${() => removeAt(i)}>×</button>
        </div>
      `)}
    <//>
  `;
}

/* ---- Side-effect controllers (module scope) ---- */

async function showPreview(text) {
  // If a preview for the same text is already loading, do not fire a second
  // request — the first call on a fresh server warms GLiNER + spaCy and can
  // take ~60 s; letting Enter re-trigger it creates a thundering herd.
  const current = signals.pendingPreview.value;
  if (current && current.text === text && current.result === null) return;

  signals.pendingPreview.value = { text, result: null };
  try {
    const result = await api.debugTest(text);
    // Only overwrite if the user has not already cancelled/sent in the meantime.
    if (signals.pendingPreview.value && signals.pendingPreview.value.text === text) {
      signals.pendingPreview.value = { text, result };
    }
  } catch (err) {
    signals.pendingPreview.value = null;
    toast(err.message || 'Vorschau nicht verfügbar', 'error');
  }
}

function closePreview() {
  signals.pendingPreview.value = null;
}

async function sendConfirmed(text) {
  let provider = signals.provider.value;
  let model = signals.model.value;

  if (!provider) {
    provider = document.getElementById('sel-provider')?.value || '';
    if (provider) signals.provider.value = provider;
  }
  if (!model) {
    model = document.getElementById('sel-model')?.value || '';
    if (model) signals.model.value = model;
  }

  if (!provider || !model) {
    const providers = signals.providers.value;
    for (const pid of ['ollama', 'anthropic', 'openai', 'mistral', 'google']) {
      const p = providers[pid];
      if (p?.configured && p.models?.length) {
        provider = pid;
        model = p.models[0].id;
        batch({ provider, model });
        break;
      }
    }
  }

  if (!provider || !model) {
    toast('Bitte zuerst einen KI-Anbieter und ein Modell konfigurieren (Einstellungen)', 'error', 5000);
    return;
  }

  const inputEl = document.getElementById('msg-input');
  if (inputEl) { inputEl.value = ''; inputEl.style.height = 'auto'; }
  closePreview();

  let convId = signals.currentConversationId.value;
  if (!convId) {
    try {
      const { id } = await api.createConversation({ provider, model, title: text.slice(0, 60) });
      convId = id;
      batch({ currentConversationId: id, currentView: 'chat' });
      refreshList();
    } catch (err) { toast(err.message, 'error'); return; }
  }

  const userMsg = { role: 'user', content: text, meta: null };
  const newMessages = [...signals.messages.value, userMsg];
  signals.messages.value = newMessages;
  const history = newMessages.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));

  const attachments = signals.pendingAttachments.value;
  let fullMessage = text;
  if (attachments.length) {
    const attachTexts = attachments.map((a) => `[Datei: ${a.filename}]\n${a.extracted_text || a.anonymized_text || ''}`).join('\n\n');
    fullMessage = `${attachTexts}\n\n${text}`;
    signals.pendingAttachments.value = [];
  }

  signals.isStreaming.value = true;
  let streamedText = '';
  let meta = null;
  const msgIdx = newMessages.length;
  signals.messages.value = [...newMessages, { role: 'assistant', content: '', meta: null }];

  abortHandle = api.streamMessage(
    { message: fullMessage, provider, model, history, system_prompt: '', conversation_id: convId },
    {
      onMeta(data) {
        meta = data;
        signals.lastMeta.value = data;
        const stats = signals.sessionStats.value;
        signals.sessionStats.value = { ...stats, anonymized: stats.anonymized + (data.anonymized_count || 0) };
      },
      onToken(content) {
        if (!content) return;
        streamedText += content;
        const msgs = [...signals.messages.value];
        if (msgs[msgIdx]) {
          msgs[msgIdx] = { ...msgs[msgIdx], content: streamedText };
          signals.messages.value = msgs;
        }
      },
      onDone(data) {
        if (data.full_response) streamedText = data.full_response;
        const msgs = [...signals.messages.value];
        if (msgs[msgIdx]) {
          msgs[msgIdx] = {
            role: 'assistant',
            content: streamedText,
            meta,
            doneData: data,
            rawResponse: data.raw_response || null,
          };
        }
        if (meta && msgs[msgIdx - 1]) {
          msgs[msgIdx - 1] = { ...msgs[msgIdx - 1], meta };
        }
        signals.messages.value = msgs;
        saveMessages(convId, msgs);
        signals.isStreaming.value = false;
        refreshList();
        const stats = signals.sessionStats.value;
        signals.sessionStats.value = { ...stats, restored: stats.restored + (data.restored_count || 0) };
      },
      onError(error) {
        toast(error, 'error', 8000);
        const msgs = [...signals.messages.value];
        if (msgs[msgIdx]?.content === '') msgs.pop();
        signals.messages.value = msgs;
        signals.isStreaming.value = false;
      },
      onComplete() {
        if (signals.isStreaming.value) signals.isStreaming.value = false;
      },
    },
  );
}

function handleSend(chipText) {
  if (signals.isStreaming.value) {
    abortHandle?.abort();
    signals.isStreaming.value = false;
    return;
  }

  const inputEl = document.getElementById('msg-input');
  const text = typeof chipText === 'string' ? chipText : inputEl?.value.trim();
  if (!text) return;

  if (typeof chipText !== 'string' && getConfirmSend()) {
    showPreview(text);
    return;
  }

  sendConfirmed(text);
}

/* ---- Wire the static input/send buttons (outside Preact trees) ---- */

function wireInputControls() {
  const inputEl = document.getElementById('msg-input');
  const sendBtn = document.getElementById('btn-send');
  const previewBtn = document.getElementById('btn-preview');
  if (!inputEl || !sendBtn) return;

  sendBtn.addEventListener('click', () => handleSend());

  if (previewBtn) {
    previewBtn.addEventListener('click', () => {
      const text = inputEl.value.trim();
      if (text) showPreview(text);
    });
  }

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const pending = signals.pendingPreview.value;
      if (pending && pending.result) {
        // Preview already confirmed → send
        sendConfirmed(pending.text);
      } else {
        handleSend();
      }
    }
  });

  inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + 'px';
    // Closing the preview on typing feels right — if the user keeps editing,
    // the old preview is stale anyway.
    if (signals.pendingPreview.value) signals.pendingPreview.value = null;
  });

  inputEl.addEventListener('chip-submit', (e) => handleSend(e.detail));

  // Reflect streaming state in the send button icon + disabled input
  signals.isStreaming.subscribe((streaming) => {
    sendBtn.classList.toggle('streaming', streaming);
    sendBtn.innerHTML = streaming
      ? SVG_STOP
      : (getConfirmSend() ? SVG_SHIELD : SVG_SEND);
    inputEl.disabled = streaming;
  });

  // Mirror preview state onto the #anon-preview container's `hidden` attribute
  // so CSS/layout that uses the attribute keep working.
  const previewEl = document.getElementById('anon-preview');
  if (previewEl) {
    const updateHidden = () => {
      previewEl.hidden = signals.pendingPreview.value === null;
    };
    updateHidden();
    signals.pendingPreview.subscribe(updateHidden);
  }
}

/* ---- Init ---- */

export function init() {
  const messagesEl = document.getElementById('messages');
  if (messagesEl) {
    try { render(html`<${MessageList} />`, messagesEl); }
    catch (err) { console.error('[AUSTR.AI] MessageList render failed:', err); }
  }

  const previewEl = document.getElementById('anon-preview');
  if (previewEl) {
    try { render(html`<${PreviewPanel} />`, previewEl); }
    catch (err) { console.error('[AUSTR.AI] PreviewPanel render failed:', err); }
  }

  const attachmentsEl = document.getElementById('attachments');
  if (attachmentsEl) {
    try { render(html`<${AttachmentList} />`, attachmentsEl); }
    catch (err) { console.error('[AUSTR.AI] AttachmentList render failed:', err); }
    const updateHidden = () => {
      attachmentsEl.hidden = signals.pendingAttachments.value.length === 0;
    };
    updateHidden();
    signals.pendingAttachments.subscribe(updateHidden);
  }

  wireInputControls();
}

/* Backward-compat export for upload.js.
 * The <AttachmentList /> Preact component subscribes to `signals.pendingAttachments`
 * and re-renders on its own — this function is intentionally a no-op. Kept so the
 * existing import in upload.js continues to resolve until upload.js stops calling it.
 */
export function renderAttachments() {
  /* no-op: reactive AttachmentList handles updates via signal subscription */
}
