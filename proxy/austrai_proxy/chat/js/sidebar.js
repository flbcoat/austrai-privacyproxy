/**
 * AUSTR.AI — Sidebar Component
 * Renders conversation list, handles new/select/delete.
 */

import { get, set, on, deleteMessages, loadMessages } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const ICONS = {
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>',
};

let listEl;

export function init() {
  listEl = document.getElementById('conversation-list');

  document.getElementById('btn-new-chat').addEventListener('click', newChat);

  on('conversations', render);
  on('currentConversationId', render);
  render();
}

function render() {
  const convs = get('conversations');
  const activeId = get('currentConversationId');

  if (!convs.length) {
    listEl.innerHTML = `<div class="aai-conv-empty">${t('noConversations')}</div>`;
    return;
  }

  listEl.innerHTML = convs.map(c => {
    const active = c.id === activeId ? ' active' : '';
    const count = c.message_count || 0;
    const date = new Date(c.updated_at * 1000).toLocaleDateString(get('language') === 'de' ? 'de-AT' : 'en-US', { day: 'numeric', month: 'short' });
    return `<div class="aai-conv-item${active}" data-id="${c.id}">
      <span class="aai-conv-icon">${ICONS.chat}</span>
      <span class="aai-conv-title">${escHtml(c.title)}</span>
      <span class="aai-conv-meta">${date}</span>
      <button class="aai-conv-delete" data-delete="${c.id}" title="${t('deleteConv')}">&times;</button>
    </div>`;
  }).join('');

  // Event delegation
  listEl.onclick = (e) => {
    const delBtn = e.target.closest('[data-delete]');
    if (delBtn) {
      e.stopPropagation();
      removeConversation(delBtn.dataset.delete);
      return;
    }
    const item = e.target.closest('.aai-conv-item');
    if (item) selectConversation(item.dataset.id);
  };
}

export async function newChat() {
  const provider = get('provider');
  const model = get('model');
  try {
    const { id } = await api.createConversation({ provider, model });
    await refreshList();
    selectConversation(id);
  } catch (err) {
    console.error('Failed to create conversation:', err);
  }
}

function selectConversation(id) {
  set('currentConversationId', id);
  set('currentView', 'chat');
  set('messages', loadMessages(id));
  if (window.innerWidth <= 768) set('sidebarOpen', false);
}

async function removeConversation(id) {
  try {
    await api.deleteConversation(id);
    deleteMessages(id);
    if (get('currentConversationId') === id) {
      set('currentConversationId', null);
      set('messages', []);
      set('currentView', 'welcome');
    }
    await refreshList();
  } catch (err) {
    console.error('Failed to delete conversation:', err);
  }
}

export async function refreshList() {
  try {
    const convs = await api.listConversations();
    set('conversations', convs);
  } catch { /* offline */ }
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
