/**
 * AUSTR.AI — Sidebar (Preact)
 * Renders conversation list, handles new/select/delete.
 *
 * Backend persistence (v2.2.2): messages are encrypted in SQLite on the server.
 * On conversation-select, we first show any cached messages from localStorage
 * (instant), then fall back to the backend API when the cache is empty.
 */

import { h, render, Fragment } from 'preact';
import { useState, useRef, useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, batch, deleteMessages, loadMessages, saveMessages, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const html = htm.bind(h);

const ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>';
const ICON_EDIT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';

function ConvIcon() {
  return html`<span class="aai-conv-icon" dangerouslySetInnerHTML=${{ __html: ICON_CHAT }} />`;
}

function EditIcon() {
  return html`<span dangerouslySetInnerHTML=${{ __html: ICON_EDIT }} />`;
}

function ConversationItem({ conv, active, onSelect, onDelete, onRename }) {
  const lang = signals.language.value === 'de' ? 'de-AT' : 'en-US';
  const isDE = signals.language.value === 'de';
  const date = new Date(conv.updated_at * 1000).toLocaleDateString(lang, { day: 'numeric', month: 'short' });

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conv.title);
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  function startEdit(e) {
    e.stopPropagation();
    setDraft(conv.title);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setDraft(conv.title);
  }

  async function commit() {
    const next = draft.trim();
    if (!next || next === conv.title) { cancelEdit(); return; }
    setEditing(false);
    try {
      await onRename(conv.id, next);
    } catch (err) {
      toast(isDE ? 'Umbenennen fehlgeschlagen' : 'Rename failed', 'error', 3000);
      setDraft(conv.title);
    }
  }

  return html`
    <div class=${`aai-conv-item${active ? ' active' : ''}`}
         onClick=${editing ? null : () => onSelect(conv.id)}>
      <${ConvIcon} />
      ${editing ? html`
        <input
          ref=${inputRef}
          class="aai-conv-title-edit"
          aria-label=${isDE ? 'Chat-Titel bearbeiten' : 'Edit chat title'}
          value=${draft}
          onInput=${(e) => setDraft(e.target.value)}
          onKeyDown=${(e) => {
            if (e.key === 'Enter') { e.preventDefault(); commit(); }
            else if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); }
          }}
          onBlur=${commit}
          onClick=${(e) => e.stopPropagation()}
          maxlength="120"
        />
      ` : html`
        <span class="aai-conv-title" onDblClick=${startEdit}>${conv.title}</span>
      `}
      ${!editing ? html`
        <span class="aai-conv-meta">${date}</span>
        <button
          class="aai-conv-rename"
          title=${isDE ? 'Umbenennen' : 'Rename'}
          onClick=${startEdit}
        ><${EditIcon} /></button>
        <button
          class="aai-conv-delete"
          title=${t('deleteConv')}
          onClick=${(e) => { e.stopPropagation(); onDelete(conv.id); }}
        >×</button>
      ` : null}
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
          onRename=${renameConversation}
        />
      `)}
    <//>
  `;
}

export async function renameConversation(id, title) {
  const next = (title || '').trim().slice(0, 120);
  if (!next) return;
  // Optimistic update: Sidebar reflektiert den neuen Titel sofort; wenn das
  // Backend-Update fehlschlägt, rollen wir zurück.
  const prev = signals.conversations.value;
  signals.conversations.value = prev.map((c) => c.id === id ? { ...c, title: next } : c);
  try {
    await api.updateConversation(id, { title: next });
  } catch (err) {
    signals.conversations.value = prev;
    throw err;
  }
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
