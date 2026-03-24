/**
 * AUSTR.AI — Reactive State Store
 * Central state management with pub/sub notifications.
 * All modules import from here to share state.
 */

const _state = {
  // Auth & Config
  onboardingDone: false,
  settings: {},
  providers: {},
  systemInfo: {},

  // Navigation
  currentView: 'welcome',        // 'welcome' | 'chat'
  currentConversationId: null,
  conversations: [],
  messages: [],

  // Chat
  provider: '',
  model: '',
  isStreaming: false,

  // Privacy (last message stats)
  lastMeta: null,
  sessionStats: { anonymized: 0, restored: 0 },

  // UI
  language: (navigator.language || 'de').startsWith('de') ? 'de' : 'en',
  sidebarOpen: window.innerWidth > 768,
  settingsOpen: false,
  privacyPanelOpen: false,

  // Uploads
  pendingAttachments: [],
};

const _listeners = new Map();

export function get(key) {
  return _state[key];
}

export function set(key, value) {
  _state[key] = value;
  if (_listeners.has(key)) {
    for (const fn of _listeners.get(key)) fn(value);
  }
}

export function on(key, fn) {
  if (!_listeners.has(key)) _listeners.set(key, new Set());
  _listeners.get(key).add(fn);
  return () => _listeners.get(key).delete(fn);
}

export function batch(updates) {
  for (const [k, v] of Object.entries(updates)) _state[k] = v;
  for (const k of Object.keys(updates)) {
    if (_listeners.has(k)) {
      for (const fn of _listeners.get(k)) fn(_state[k]);
    }
  }
}

/* ---- Local persistence for messages (backend has no save-message endpoint yet) ---- */

export function saveMessages(convId, messages) {
  try {
    localStorage.setItem(`aai_msg_${convId}`, JSON.stringify(messages));
  } catch { /* quota exceeded — ignore */ }
}

export function loadMessages(convId) {
  try {
    const raw = localStorage.getItem(`aai_msg_${convId}`);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

export function deleteMessages(convId) {
  localStorage.removeItem(`aai_msg_${convId}`);
}

/* ---- Toast notifications ---- */

export function toast(text, type = 'info', duration = 3000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `aai-toast aai-toast--${type}`;
  el.textContent = text;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add('aai-toast--visible'));
  setTimeout(() => {
    el.classList.remove('aai-toast--visible');
    setTimeout(() => el.remove(), 300);
  }, duration);
}
