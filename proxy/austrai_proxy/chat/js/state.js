/**
 * AUSTR.AI — Reactive State Store (Preact Signals)
 *
 * During the Preact migration this module exposes two APIs on the same store:
 *  - Signal API (`signals.*`, `useSignalValue`): for new Preact components
 *  - Legacy API (`get` / `set` / `on` / `batch`): for non-migrated Vanilla-JS modules
 *
 * Both views observe the same underlying Preact signals, so setters from either
 * side automatically notify subscribers of the other side.
 */

import { signal, batch as signalsBatch } from '@preact/signals';

function makeSignals() {
  return {
    // Auth & Config
    onboardingDone: signal(false),
    settings: signal({}),
    providers: signal({}),
    systemInfo: signal({}),

    // Navigation
    currentView: signal('welcome'),
    currentConversationId: signal(null),
    conversations: signal([]),
    messages: signal([]),

    // Chat
    provider: signal(''),
    model: signal(''),
    isStreaming: signal(false),

    // Privacy (last message stats)
    lastMeta: signal(null),
    sessionStats: signal({ anonymized: 0, restored: 0 }),

    // UI
    language: signal((navigator.language || 'de').startsWith('de') ? 'de' : 'en'),
    sidebarOpen: signal(window.innerWidth > 768),
    settingsOpen: signal(false),
    privacyPanelOpen: signal(false),

    // Uploads
    pendingAttachments: signal([]),

    // Chat input preview (anonymization check before sending)
    // null = hidden, { text, result } = shown (result null = loading)
    pendingPreview: signal(null),
  };
}

export const signals = makeSignals();

/* ---- Legacy pub/sub API (backward compatibility) ----
 * Non-migrated modules continue to use get/set/on/batch as before.
 * Internally these are proxied onto the same Preact signals so that
 * migrated Preact components and legacy modules stay in sync.
 */

export function get(key) {
  const s = signals[key];
  return s ? s.value : undefined;
}

export function set(key, value) {
  const s = signals[key];
  if (s) s.value = value;
}

export function on(key, fn) {
  const s = signals[key];
  if (!s) return () => {};
  let first = true;
  return s.subscribe((v) => {
    if (first) { first = false; return; } // skip initial replay — match legacy on() semantics
    fn(v);
  });
}

export function batch(updates) {
  signalsBatch(() => {
    for (const [k, v] of Object.entries(updates)) {
      const s = signals[k];
      if (s) s.value = v;
    }
  });
}

/* ---- Local persistence for messages ----
 * Backend v2.2.2 persists messages in encrypted SQLite. localStorage is a
 * per-browser cache that preserves rich metadata (rawResponse, meta, doneData)
 * which the backend does not store. Sidebar falls back to the backend API
 * when localStorage has no entry for a conversation.
 */

export function saveMessages(convId, messages) {
  try {
    localStorage.setItem(`aai_msg_${convId}`, JSON.stringify(messages));
  } catch { /* quota exceeded — ignore, backend is source of truth */ }
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

/* ---- Toast notifications ----
 * Imperative DOM insertion for now; will become a Preact <ToastContainer>
 * in Phase 11 when the app root is migrated.
 */

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
