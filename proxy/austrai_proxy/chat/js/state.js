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

    // Streaming-isolation: separate signal for the in-flight assistant message.
    // While a stream is active, onToken writes ONLY here. MessageList renders
    // historical messages from `messages[]` (static during stream) and the
    // streaming message via a dedicated <StreamingMessage /> component that
    // subscribes only to this signal. Preact's fine-grained reactivity then
    // re-renders only that one bubble per token, not the whole list.
    streamingContent: signal(''),
    streamingMsgIdx: signal(-1),
    // Extended-Thinking content for the in-flight assistant message.
    // Rendered in a separate (collapsible) block above the answer so
    // the user can SEE the model's reasoning when it uses thinking-mode.
    streamingThinking: signal(''),

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

    // Stand-alone tool result (Werkzeuge-Tab).
    // null = nothing to show, { kind, result, filename } = display
    // the latest tool output below the tool cards. Does not create a chat.
    toolResult: signal(null),

    // Stand-alone tool loading state. null = idle,
    // { kind, filename, status } = show spinner + status text while upload/
    // anonymization is running. Lets the user see that something is happening
    // even on large PDFs that take several seconds to extract + detect.
    toolLoading: signal(null),

    // Chat-Input Büroklammer Popover-Menü: beim Klick auf btn-upload öffnet
    // sich ein kleines Menü mit "Datei anhängen" vs. "Bild/PDF schwärzen",
    // damit der User vor dem Dateipicker entscheidet, was passieren soll.
    uploadMenuOpen: signal(false),

    // Phase 2/3 of the 04/2026 pivot: Skills and Knowledge Base
    skills: signal([]),                 // [{slug, name, description, recommended_provider, recommended_model, ...}]
    activeSkillSlug: signal(''),        // selected via header dropdown or /<skill-slug>
    projects: signal([]),               // [{slug, name, description, doc_count, chunk_count}]
    activeProjectSlug: signal(''),      // selected via header dropdown
    // Anti-Magic-RAG: candidate snippets shown under the chat input
    // before send. User toggles which to attach via checkbox.
    kbSearchResults: signal([]),        // [{chunk_id, doc_filename, anonymized_text, score}]
    kbSelectedChunkIds: signal([]),     // user-confirmed chunk_ids for next send
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

/* Strip large/sensitive payloads from messages before localStorage save.
 *
 * Rationale: geschwärzte Bilder (`attachment.base64`) können MBs groß sein
 * und landen ungeschützt im Browser-Storage, wo Extensions + Profile-
 * Backups sie lesen können. Während der aktiven Session halten wir das
 * base64 im Memory (signals.messages), aber wir schreiben es nicht in
 * den persistenten Cache. Beim Reload zeigt RedactEmbed dann einen
 * "Bild abgelaufen — bitte neu schwärzen"-Placeholder. DB-Content auf
 * dem Server bleibt davon unberührt (Redact-Outputs werden serverseitig
 * ohnehin nicht persistiert).
 */
function stripSensitivePayloads(messages) {
  return messages.map((m) => {
    if (m?.attachment?.base64) {
      const { base64, ...attachmentWithoutBase64 } = m.attachment;
      return { ...m, attachment: { ...attachmentWithoutBase64, expired: true } };
    }
    return m;
  });
}

export function saveMessages(convId, messages) {
  try {
    const sanitized = stripSensitivePayloads(messages);
    localStorage.setItem(`aai_msg_${convId}`, JSON.stringify(sanitized));
  } catch (err) {
    // Quota exceeded → Toast damit der User weiß, dass der Chat nicht
    // lokal gecacht ist (Backend-SQLite bleibt aber Source of Truth).
    try { toast('Browser-Speicher voll — Chat wird nur serverseitig gesichert', 'info', 5000); } catch {}
  }
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
