/**
 * AUSTR.AI — Sidebar (Preact)
 * Renders conversation list, handles new/select/delete.
 *
 * Backend persistence (v2.2.2): messages are encrypted in SQLite on the server.
 * On conversation-select, we first show any cached messages from localStorage
 * (instant), then fall back to the backend API when the cache is empty.
 */

import { h, render, Fragment } from 'preact';
import htm from 'htm';
import { signals, batch, deleteMessages, loadMessages, saveMessages } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const html = htm.bind(h);

const ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>';

function ConvIcon() {
  return html`<span class="aai-conv-icon" dangerouslySetInnerHTML=${{ __html: ICON_CHAT }} />`;
}

function ConversationItem({ conv, active, onSelect, onDelete }) {
  const lang = signals.language.value === 'de' ? 'de-AT' : 'en-US';
  const date = new Date(conv.updated_at * 1000).toLocaleDateString(lang, { day: 'numeric', month: 'short' });

  return html`
    <div class=${`aai-conv-item${active ? ' active' : ''}`} onClick=${() => onSelect(conv.id)}>
      <${ConvIcon} />
      <span class="aai-conv-title">${conv.title}</span>
      <span class="aai-conv-meta">${date}</span>
      <button
        class="aai-conv-delete"
        title=${t('deleteConv')}
        onClick=${(e) => { e.stopPropagation(); onDelete(conv.id); }}
      >×</button>
    </div>
  `;
}

function ConversationList() {
  const convs = signals.conversations.value;
  const activeId = signals.currentConversationId.value;

  if (!convs.length) {
    return html`<div class="aai-conv-empty">${t('noConversations')}</div>`;
  }

  return html`
    <${Fragment}>
      ${convs.map((c) => html`
        <${ConversationItem}
          key=${c.id}
          conv=${c}
          active=${c.id === activeId}
          onSelect=${selectConversation}
          onDelete=${removeConversation}
        />
      `)}
    <//>
  `;
}

/* ---- Actions ---- */

export async function newChat() {
  // "Neuer Chat" takes the user back to the home screen (Welcome view) with
  // the tool cards and the chat input. A conversation is created lazily the
  // moment the user actually types a message or triggers a tool — that way
  // we don't accumulate empty conversations and the mental model stays
  // consistent: Home = nothing started yet, every real action produces a
  // new conversation entry in the sidebar.
  batch({
    currentConversationId: null,
    currentView: 'welcome',
    messages: [],
  });
  signals.pendingAttachments.value = [];
  signals.pendingPreview.value = null;
  if (window.innerWidth <= 768) signals.sidebarOpen.value = false;

  // Also un-highlight any currently selected conversation item in the
  // sidebar. The <ConversationList> reads currentConversationId reactively,
  // so clearing it above already handles the visual state.
}

async function selectConversation(id) {
  batch({
    currentConversationId: id,
    currentView: 'chat',
    messages: loadMessages(id),
  });
  if (window.innerWidth <= 768) signals.sidebarOpen.value = false;

  // Backend fallback: when localStorage is empty, fetch from SQLite store.
  // This handles first-time load on a new browser, quota-exceeded writes,
  // and users returning after cache clears.
  if (!signals.messages.value.length) {
    try {
      const { messages } = await api.getConversation(id);
      if (messages?.length && signals.currentConversationId.value === id) {
        const mapped = messages.map((m) => ({ role: m.role, content: m.content, meta: null }));
        signals.messages.value = mapped;
        saveMessages(id, mapped);
      }
    } catch { /* offline fallback: keep whatever localStorage had */ }
  }
}

async function removeConversation(id) {
  try {
    await api.deleteConversation(id);
    deleteMessages(id);
    if (signals.currentConversationId.value === id) {
      batch({
        currentConversationId: null,
        messages: [],
        currentView: 'welcome',
      });
    }
    await refreshList();
  } catch (err) {
    console.error('Failed to delete conversation:', err);
  }
}

export async function refreshList() {
  try {
    const convs = await api.listConversations();
    signals.conversations.value = convs;
  } catch { /* offline */ }
}

/* ---- Init ---- */

export function init() {
  const listEl = document.getElementById('conversation-list');
  if (!listEl) return;

  render(html`<${ConversationList} />`, listEl);

  const newBtn = document.getElementById('btn-new-chat');
  if (newBtn) newBtn.addEventListener('click', newChat);
}
