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
import { useState, useEffect, useRef } from 'preact/hooks';
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

/* ---- Blob-URL Helper für Redact-Attachments ----
 *
 * Geschwärzte Bilder/PDFs können sehr groß sein (>10 MB Base64). Eine
 * `data:`-URL im <img>-Tag funktioniert zwar, aber Safari lehnt solche
 * URLs im neuen Tab (target="_blank") ab → weißer Screen. Wir konvertieren
 * das base64-Payload stattdessen zu einem Blob und erzeugen eine
 * `blob:` URL, die in neuen Tabs zuverlässig funktioniert.
 */
function base64ToBlobUrl(base64, mimeType) {
  try {
    const bin = atob(base64 || '');
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([bytes], { type: mimeType || 'application/octet-stream' }));
  } catch (err) {
    console.error('base64ToBlobUrl failed:', err);
    return null;
  }
}

function RedactEmbed({ attachment }) {
  const isDE = signals.language.value === 'de';
  const mimeType = attachment.mimeType || 'image/png';
  const isPdf = mimeType === 'application/pdf';
  // Drei States:
  //   loading=true    → Upload läuft, Spinner
  //   expired=true    → base64 wurde aus localStorage gestrippt beim Reload
  //   base64 vorhanden → Bild anzeigen
  const isLoading = attachment.loading === true;
  const isExpired = attachment.expired === true && !attachment.base64;
  const [blobUrl, setBlobUrl] = useState(null);

  useEffect(() => {
    if (!attachment.base64) { setBlobUrl(null); return undefined; }
    const url = base64ToBlobUrl(attachment.base64, mimeType);
    setBlobUrl(url);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [attachment.base64, mimeType]);

  // Loading-State: während der Server das Bild schwärzt zeigen wir einen
  // dezenten Spinner mit Dateiname + Status — kein Download-Button, weil es
  // noch nichts zum Herunterladen gibt.
  if (isLoading) {
    return html`
      <div class="aai-redact-embed aai-redact-embed--loading">
        <div class="aai-redact-embed-head">
          <strong>${attachment.filename || 'redacted'}</strong>
          <span class="aai-redact-embed-meta">${isDE ? 'wird verarbeitet …' : 'processing …'}</span>
        </div>
        <div class="aai-redact-embed-preview aai-redact-embed-preview--loading">
          <div class="aai-spinner aai-spinner--lg" aria-hidden="true"></div>
        </div>
      </div>
    `;
  }

  // Expired: das Bild wurde aus Privacy-Gründen nicht im localStorage
  // persistiert (H-1 in 3.1.10). Nach Reload ist es nicht mehr verfügbar —
  // wir zeigen einen dezenten Placeholder statt eines defekten Bildes.
  if (isExpired) {
    const count = attachment.entitiesRedacted || 0;
    return html`
      <div class="aai-redact-embed aai-redact-embed--expired">
        <div class="aai-redact-embed-head">
          <strong>${attachment.filename || 'redacted'}</strong>
          <span class="aai-redact-embed-meta">${isDE
            ? `${count} Bereich${count === 1 ? '' : 'e'} geschwärzt`
            : `${count} area${count === 1 ? '' : 's'} redacted`}</span>
        </div>
        <div class="aai-redact-embed-preview aai-redact-embed-preview--expired">
          <p style="text-align:center;color:var(--text-muted);font-size:12px;margin:0">
            ${isDE
              ? 'Bild wurde aus Datenschutz­gründen nicht lokal gespeichert.'
              : 'Image was not cached locally for privacy reasons.'}
            <br/>${isDE ? 'Bitte neu schwärzen, falls benötigt.' : 'Please redact again if needed.'}
          </p>
        </div>
      </div>
    `;
  }

  function openInNewTab() {
    if (!blobUrl) return;
    const a = document.createElement('a');
    a.href = blobUrl; a.target = '_blank'; a.rel = 'noopener';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }

  function downloadFile() {
    if (!blobUrl) return;
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = (attachment.filename || 'redacted').replace(/(\.[^.]+)?$/, (ext) => `_redacted${ext || '.png'}`);
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }

  const count = attachment.entitiesRedacted || 0;
  const countLabel = isDE
    ? `${count} Bereich${count === 1 ? '' : 'e'} geschwärzt`
    : `${count} area${count === 1 ? '' : 's'} redacted`;

  return html`
    <div class="aai-redact-embed">
      <div class="aai-redact-embed-head">
        <strong>${attachment.filename || 'redacted'}</strong>
        <span class="aai-redact-embed-meta">${countLabel}</span>
      </div>
      ${isPdf ? html`
        <div class="aai-redact-placeholder">
          <p>${isDE ? 'Geschwärztes PDF vorbereitet.' : 'Redacted PDF ready.'}</p>
        </div>
      ` : html`
        <div class="aai-redact-embed-preview">
          ${blobUrl ? html`<img src=${blobUrl} alt=${attachment.filename} onClick=${openInNewTab} style="cursor: zoom-in" />` : html`<div class="aai-spinner aai-spinner--lg"></div>`}
        </div>
      `}
      <div class="aai-redact-embed-actions">
        <button class="aai-btn aai-btn--primary aai-btn--sm" onClick=${openInNewTab} disabled=${!blobUrl}>
          ${isDE ? 'Im neuen Tab öffnen' : 'Open in new tab'}
        </button>
        <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${downloadFile} disabled=${!blobUrl}>
          ${isDE ? 'Herunterladen' : 'Download'}
        </button>
      </div>
    </div>
  `;
}

/* ---- Message bubble ---- */

// Render LaTeX inside an element using vendored KaTeX. No-op when KaTeX
// isn't loaded yet (defer-loaded scripts). Called after each non-streaming
// markdown render so $$...$$ and $...$ become real math, not raw text.
function renderMathIn(element) {
  if (!element || typeof window === 'undefined' || !window.renderMathInElement) return;
  try {
    window.renderMathInElement(element, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '\\[', right: '\\]', display: true },
        { left: '\\(', right: '\\)', display: false },
        { left: '$', right: '$', display: false },
      ],
      // Default ignoredTags includes 'pre' and 'code' which means inline-code
      // math like `$x^2$` would silently NOT render. We trim that to just the
      // tags where math truly cannot appear (script/style). 'code' inside
      // inline-code blocks may still occasionally false-positive but the
      // visible win is bigger than the rare collision.
      ignoredTags: ['script', 'style'],
      ignoredClasses: ['aai-routing-badge', 'aai-model-badge', 'aai-auto-badge'],
      throwOnError: false,
      errorColor: '#cc6666',  // soft red so failed-to-render formulas are visible
      strict: 'ignore',       // don't reject unsupported macros
      trust: false,
    });
  } catch (e) {
    // Silent: KaTeX errors must never break the chat UI.
  }
}

function MessageBubble({ msg, prevMsg, isLast, isStreaming }) {
  const [showRaw, setShowRaw] = useState(false);
  const contentRef = useRef(null);
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

  // Routing-Badge on user message: shows when Auto-Routing picked a model.
  let routingBadge = null;
  if (isUser && msg.meta && msg.meta.routing) {
    const r = msg.meta.routing;
    routingBadge = html`
      <div class="aai-routing-badge" style="margin-top:4px;font-size:11px;color:var(--text-muted)">
        → ${r.model} · ${r.task} · via ${r.stage}
      </div>
    `;
  }

  // Model-Badge on assistant message: always shown (if we know which
  // model answered), so the user can see per-turn which model was active.
  // Especially useful when switching models between turns, since the header
  // dropdown reflects the CURRENT selection, not the one at send-time.
  let modelBadge = null;
  if (!isUser && !msg.error && (msg.provider || msg.model || msg.meta?.model)) {
    const mProvider = msg.provider || msg.meta?.provider || '';
    const mModel = msg.model || msg.meta?.model || '';
    if (mModel) {
      modelBadge = html`
        <div class="aai-model-badge" style="margin-top:6px;font-size:11px;color:var(--text-muted);opacity:0.75">
          ${signals.language.value === 'de' ? 'Antwort von' : 'Answer by'}: ${mProvider ? `${mProvider} · ` : ''}${mModel}
        </div>
      `;
    }
  }

  // Error-Bubble for assistant message: replaces a failed stream with a
  // persistent, contextual error entry in the chat history. Shows the
  // model that was attempted so the user can see which model triggered
  // the problem and try a different one.
  let errorBubble = null;
  if (!isUser && msg.error) {
    const e = msg.error;
    errorBubble = html`
      <div style="border:1px solid var(--danger);background:rgba(239,68,68,0.06);border-radius:8px;padding:10px 14px;margin:4px 0">
        <div style="font-weight:500;color:var(--danger);margin-bottom:4px">
          ${signals.language.value === 'de' ? 'Anfrage fehlgeschlagen' : 'Request failed'}
          ${e.status ? html` · HTTP ${e.status}` : null}
        </div>
        <div style="font-size:12px;color:var(--text-secondary);margin-bottom:6px">
          ${signals.language.value === 'de' ? 'Modell' : 'Model'}: <code>${e.provider || '?'} / ${e.model || '?'}</code>
        </div>
        <div style="font-size:13px;white-space:pre-wrap;color:var(--text-primary)">${e.message}</div>
        ${e.hint ? html`
          <div style="font-size:12px;color:var(--text-muted);margin-top:6px;border-top:1px dashed var(--border);padding-top:6px">
            💡 ${e.hint}
          </div>
        ` : null}
      </div>
    `;
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
  // After content renders (and is NOT in streaming mode), let KaTeX scan
  // the DOM and replace $$..$$ / $..$ tokens with real math. We only run
  // this on assistant messages because users typically don't write LaTeX.
  // During streaming we skip — running KaTeX on a partial token would error.
  useEffect(() => {
    if (!isUser && contentRef.current && !isStreaming) {
      renderMathIn(contentRef.current);
    }
  }, [msg.content, isStreaming, isUser]);

  // Streaming-mode rendering: while a stream is in flight, render the partial
  // content as plain (escaped) text inside <pre>, NOT as markdown. Reason:
  // renderMarkdown() is O(N) per call on the growing content, so per-token
  // rendering is O(N²) overall and blows up the heap on long answers (the
  // observed "Out of memory" crash). When the stream finishes (msg.doneData
  // is set), we re-render once as full markdown — single O(N) cost, smooth UX.
  const isStreamingMsg = isStreaming && isLast && !isUser && msg.content && !msg.doneData;
  const contentHtml = showTyping
    ? '<div class="aai-typing"><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div></div>'
    : isStreamingMsg
      ? `<pre style="white-space:pre-wrap;font-family:inherit;font-size:inherit;margin:0;background:none;border:none;padding:0">${esc(msg.content)}</pre>`
      : (isUser ? esc(msg.content) : renderMarkdown(msg.content));

  // Spezialisierter Renderer für Tool-Results: geschwärzte Bilder/PDFs
  // landen NICHT als Markdown (data-URL im Link → weißer Tab in Safari),
  // sondern als `msg.attachment` Objekt, aus dem wir on-the-fly eine
  // Blob-URL erzeugen und ein echtes <img> + Download-Button rendern.
  const isRedact = msg.attachment?.kind === 'redact';

  // Persistent thinking block on the static (post-stream) bubble.
  // Collapsed by default for past messages so the chat history stays
  // compact, but the user can expand to see what the model thought.
  const persistentThinkingBlock = (!isUser && msg.thinking) ? html`
    <details class="aai-thinking-block" style="margin-bottom:8px;border-left:2px solid var(--accent,#4f46e5);padding:6px 10px;background:var(--bg-subtle);border-radius:0 4px 4px 0">
      <summary style="cursor:pointer;font-size:11px;font-weight:500;color:var(--text-muted);user-select:none">
        💭 ${signals.language.value === 'de' ? 'Reasoning' : 'Reasoning'} (${msg.thinking.length.toLocaleString()} ${signals.language.value === 'de' ? 'Zeichen' : 'chars'})
      </summary>
      <div style="font-family:ui-monospace,monospace;font-size:12px;color:var(--text-muted);white-space:pre-wrap;word-break:break-word;margin-top:6px;line-height:1.5;max-height:280px;overflow-y:auto">${msg.thinking}</div>
    </details>
  ` : null;

  return html`
    <div class=${`aai-message aai-message--${msg.role}`}>
      <div class="aai-msg-inner">
        <div class=${`aai-avatar ${avatarClass}`} dangerouslySetInnerHTML=${{ __html: avatarSvg }} />
        <div class="aai-msg-body">
          ${persistentThinkingBlock}
          ${isRedact ? html`
            <${RedactEmbed} attachment=${msg.attachment} />
          ` : html`
            <div ref=${contentRef} class="aai-msg-text" dangerouslySetInnerHTML=${{ __html: contentHtml }} />
          `}
          ${badge}
          ${routingBadge}
          ${errorBubble}
          ${modelBadge}
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

/* ---- Streaming message (isolated re-render) ----
 * While a stream is in flight, this component owns the rendering of the
 * one growing assistant bubble. It subscribes ONLY to signals.streamingContent
 * — Preact's fine-grained reactivity ensures that no other MessageBubble
 * re-renders when a token arrives. Renders plain (escaped) text inside <pre>;
 * full markdown + KaTeX kick in once onDone copies the content into messages[]
 * and the regular MessageBubble takes over.
 */
function StreamingMessage() {
  const content = signals.streamingContent.value;  // single signal subscription
  const thinking = signals.streamingThinking?.value || '';
  const containerRef = useRef(null);
  const lastRenderAt = useRef(0);

  // Throttled rich render: every ~400ms (and on initial mount), parse the
  // current streaming text as full markdown and run KaTeX on it. Between
  // renders, the user sees the previously-rendered state (no plain $$..$$
  // raw text). Renders cap at ~2.5/sec which keeps the main thread responsive
  // even on long answers — this is the controlled re-introduction of
  // markdown rendering during streaming, traded against a moderate CPU cost.
  useEffect(() => {
    if (!containerRef.current || !content) return;
    const now = Date.now();
    // First render after mount → run immediately so user sees something fast.
    // Subsequent renders gated by the throttle.
    if (lastRenderAt.current !== 0 && now - lastRenderAt.current < 400) return;
    lastRenderAt.current = now;
    try {
      containerRef.current.innerHTML = renderMarkdown(content);
      renderMathIn(containerRef.current);
    } catch {
      // On any render failure fall back to escaped plain text — never show
      // a broken state mid-stream.
      containerRef.current.textContent = content;
    }
  }, [content]);

  // Thinking block — shown above the answer when the model uses
  // Extended Thinking (Anthropic) or reasoning (o-series). User can
  // collapse it; default is expanded so it is visible during streaming
  // (Florian's "make reasoning visible" requirement, 26.04.2026).
  const thinkingBlock = thinking ? html`
    <details open class="aai-thinking-block" style="margin-bottom:8px;border-left:2px solid var(--accent,#4f46e5);padding:6px 10px;background:var(--bg-subtle);border-radius:0 4px 4px 0">
      <summary style="cursor:pointer;font-size:11px;font-weight:500;color:var(--text-muted);user-select:none">
        💭 Reasoning (${thinking.length.toLocaleString()} ${thinking.length === 1 ? 'Zeichen' : 'Zeichen'})
      </summary>
      <div style="font-family:ui-monospace,monospace;font-size:12px;color:var(--text-muted);white-space:pre-wrap;word-break:break-word;margin-top:6px;line-height:1.5;max-height:280px;overflow-y:auto">${thinking}</div>
    </details>
  ` : null;

  if (!content) {
    return html`
      <div class="aai-message aai-message--assistant">
        <div class="aai-msg-inner">
          <div class="aai-avatar aai-avatar--assistant" dangerouslySetInnerHTML=${{ __html: SVG_BOT }} />
          <div class="aai-msg-body">
            ${thinkingBlock}
            <div class="aai-msg-text">
              <div class="aai-typing"><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div></div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  return html`
    <div class="aai-message aai-message--assistant">
      <div class="aai-msg-inner">
        <div class="aai-avatar aai-avatar--assistant" dangerouslySetInnerHTML=${{ __html: SVG_BOT }} />
        <div class="aai-msg-body">
          ${thinkingBlock}
          <div ref=${containerRef} class="aai-msg-text" />
        </div>
      </div>
    </div>
  `;
}

/* ---- Message list ---- */

function MessageList() {
  const messages = signals.messages.value;
  const isStreaming = signals.isStreaming.value;
  const streamIdx = signals.streamingMsgIdx.value;

  useEffect(() => {
    const chatView = document.getElementById('chat-view');
    if (chatView) chatView.scrollTop = chatView.scrollHeight;
  }, [messages.length, messages[messages.length - 1]?.content]);

  return html`
    <${Fragment}>
      ${messages.map((m, i) => {
        // The currently-streaming message uses the isolated StreamingMessage
        // component. Everything else uses the full MessageBubble (with markdown,
        // KaTeX, badges). Static messages do not re-render per token anymore.
        if (i === streamIdx && isStreaming) {
          return html`<${StreamingMessage} key=${'stream-' + i} />`;
        }
        return html`
          <${MessageBubble}
            key=${i}
            msg=${m}
            prevMsg=${i > 0 ? messages[i - 1] : null}
            isLast=${i === messages.length - 1}
            isStreaming=${isStreaming}
          />
        `;
      })}
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
        <span class="aai-preview-loading-text">
          ${slowLoad
            ? 'Anonymisierung wird geprüft… (KI-Modelle werden beim ersten Mal geladen, bis zu 1 Minute)'
            : 'Anonymisierung wird geprüft…'}
        </span>
        <button
          class="aai-btn aai-btn--ghost aai-btn--icon aai-btn--sm"
          onClick=${closePreview}
          title="Abbrechen"
        >×</button>
      </div>
    `;
  }

  // A user can reach this panel with an empty original text (e.g. by pressing
  // "Prüfen" without having typed anything yet). The old code still rendered a
  // "Bearbeiten" button that led nowhere. We now disable it in that case so
  // people don't click into a dead end.
  const hasEditableText = Boolean((result.original || '').trim());

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
        <button
          class=${`aai-btn aai-btn--ghost aai-btn--sm${editMode ? ' active' : ''}`}
          onClick=${() => hasEditableText && setEditMode(!editMode)}
          disabled=${!hasEditableText}
          title=${hasEditableText ? 'Text markieren um Begriffe zur Deny-Liste hinzuzufügen' : 'Kein Text zum Bearbeiten'}
        >Bearbeiten</button>
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

function AttachmentItem({ idx, a, onRemove, onUpdateAnonymized }) {
  const isDE = signals.language.value === 'de';

  // Loading-State: während der Server hochgeladene Datei extrahiert und
  // anonymisiert zeigen wir eine Placeholder-Karte mit Spinner. Das ersetzt
  // den stillen "nichts passiert"-Moment auf großen PDFs.
  if (a.loading) {
    return html`
      <div class="aai-attachment-detail aai-attachment-detail--loading">
        <div class="aai-attachment-header">
          <span class="aai-spinner" aria-hidden="true"></span>
          <span class="aai-attachment-name">${a.filename}</span>
          <span class="aai-attachment-badge aai-attachment-badge--accent">
            ${isDE ? 'wird verarbeitet …' : 'processing …'}
          </span>
        </div>
      </div>
    `;
  }

  const warns = Array.isArray(a.warnings) ? a.warnings : [];
  const extracted = ((a.extracted_text || '') + '').trim();
  const anonymized = ((a.anonymized_text || '') + '').trim();
  const hasContent = extracted.length > 0;
  const entities = a.entity_count || 0;
  const mappings = a.mappings || {};
  const mapCount = Object.keys(mappings).length;

  const [expanded, setExpanded] = useState(hasContent);

  let statusLabel;
  let statusClass;
  if (!hasContent) {
    statusLabel = isDE ? 'Kein Text lesbar' : 'No readable text';
    statusClass = 'warning';
  } else if (entities > 0) {
    statusLabel = isDE
      ? `${entities} sensible${entities === 1 ? 'r Begriff' : ' Begriffe'} erkannt`
      : `${entities} sensitive term${entities === 1 ? '' : 's'} detected`;
    statusClass = 'accent';
  } else {
    statusLabel = isDE ? 'Keine sensiblen Daten' : 'No sensitive data';
    statusClass = 'success';
  }

  return html`
    <div class="aai-attachment-detail">
      <div class="aai-attachment-header">
        <span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} class="aai-attachment-icon" />
        <span class="aai-attachment-name">${a.filename}</span>
        <span class=${`aai-attachment-badge aai-attachment-badge--${statusClass}`}>
          ${statusLabel}
        </span>
        ${hasContent ? html`
          <button class="aai-attachment-toggle"
            onClick=${() => setExpanded((v) => !v)}
            title=${expanded
              ? (isDE ? 'Vorschau einklappen' : 'Collapse preview')
              : (isDE ? 'Vorschau öffnen' : 'Open preview')}
          >${expanded ? '▾' : '▸'}</button>
        ` : null}
        <button class="aai-attachment-remove"
          onClick=${() => onRemove(idx)}
          title=${isDE ? 'Entfernen' : 'Remove'}>×</button>
      </div>

      ${warns.length ? html`
        <div class="aai-attachment-warning">ⓘ ${warns.join(' · ')}</div>
      ` : null}

      ${expanded && hasContent ? html`
        <div class="aai-attachment-split">
          <div class="aai-anon-pane">
            <div class="aai-anon-pane-label">${isDE ? 'Original' : 'Original'}</div>
            <pre class="aai-anon-pane-content aai-attachment-pane">${extracted}</pre>
          </div>
          <div class="aai-anon-pane">
            <div class="aai-anon-pane-label">
              <span>${isDE ? 'Anonymisiert (wird gesendet)' : 'Anonymized (what gets sent)'}</span>
              <span class="aai-anon-pane-hint">${isDE
                ? 'editierbar — deine Änderungen werden an die KI geschickt'
                : 'editable — your edits are sent to the AI'}</span>
            </div>
            <textarea
              class="aai-anon-pane-content aai-anon-pane-edit aai-attachment-pane"
              value=${anonymized}
              onInput=${(e) => onUpdateAnonymized(idx, e.target.value)}
              spellcheck="false"
            ></textarea>
          </div>
        </div>
        ${mapCount > 0 ? html`
          <details class="aai-attachment-mappings">
            <summary>${isDE ? 'Zuordnungen' : 'Mappings'} (${mapCount})</summary>
            <ul>
              ${Object.entries(mappings).map(([code, orig]) => html`
                <li><code class="aai-code-orig">${orig}</code> → <code class="aai-code-anon">${code}</code></li>
              `)}
            </ul>
          </details>
        ` : null}
      ` : null}
    </div>
  `;
}

function AttachmentList() {
  const items = signals.pendingAttachments.value;
  if (!items.length) return null;

  function removeAt(idx) {
    const next = [...items];
    next.splice(idx, 1);
    signals.pendingAttachments.value = next;
  }

  function updateAnonymizedAt(idx, value) {
    const next = items.map((a, i) => i === idx ? { ...a, anonymized_text: value } : a);
    signals.pendingAttachments.value = next;
  }

  return html`
    <${Fragment}>
      ${items.map((a, i) => html`
        <${AttachmentItem}
          key=${i}
          idx=${i}
          a=${a}
          onRemove=${removeAt}
          onUpdateAnonymized=${updateAnonymizedAt}
        />
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
  // Phase 1: Slash-Command-Parser (opt-in, off-by-default).
  // Position-locked: only the FIRST token of an otherwise-leading "/cmd" is
  // parsed. "/haiku" mid-text stays content. Skill activation via
  // "/<skill-slug>" follows in Phase 2 once the skill loader exists.
  let slashOverride = null;
  let skillSlugFromSlash = null;
  const _settings = signals.settings.value || {};
  if (_settings.slash_commands && typeof text === 'string') {
    const m = text.match(/^\s*\/(\S+)(?:\s+([\s\S]*))?$/);
    if (m) {
      const cmd = m[1].toLowerCase();
      const rest = (m[2] || '').trim();
      const providersSnap = signals.providers.value || {};
      const aliases = _settings.slash_aliases || {};
      const skills = signals.skills?.value || [];
      let hit = aliases[cmd];
      // Resolve special "__local__" model to first configured local model
      // at send time (so the alias keeps working when LMStudio swaps models).
      if (hit && hit.model === '__local__') {
        const ls = providersSnap.lmstudio;
        const ol = providersSnap.ollama;
        if (ls?.configured && ls.models?.length) hit = { provider: 'lmstudio', model: ls.models[0].id };
        else if (ol?.configured && ol.models?.length) hit = { provider: 'ollama', model: ol.models[0].id };
        else hit = null;
      }
      // Skill activation by slug: /<slug> matches a saved skill
      if (!hit) {
        const skill = skills.find((s) => s.slug === cmd);
        if (skill) {
          skillSlugFromSlash = skill.slug;
          if (skill.recommended_provider && skill.recommended_model) {
            hit = { provider: skill.recommended_provider, model: skill.recommended_model };
          }
        }
      }
      if (hit || skillSlugFromSlash) {
        if (!rest) {
          toast('Slash-Befehl ohne Frage. Bitte Frage hinzufügen.', 'info', 3000);
          return;
        }
        if (hit) slashOverride = hit;
        text = rest;
        const label = hit ? `${hit.provider} · ${hit.model}` : `Skill: ${cmd}`;
        toast(`/${cmd} → ${label}`, 'info', 2000);
      }
      // Unknown command -> let it pass through as normal text.
    }
  }

  let provider = slashOverride?.provider || signals.provider.value;
  let model = slashOverride?.model || signals.model.value;

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

  // Knowledge base auto-attach (revised 27.04.2026): if a project is
  // active and the live-search has populated `kbSearchResults`, the
  // chunks are sent automatically. If results are empty (user typed
  // very fast or query is too short), we run a synchronous search
  // here as a final retrieval pass, attach everything found, and
  // continue. The previous "two-click confirm" UX was reibungsvoll
  // ohne Privacy-Mehrwert — der User sieht jetzt einen kompakten
  // Status-Indikator, das LLM bekommt nur anonymisierten Text.
  const _activeProject = signals.activeProjectSlug?.value || '';
  if (_activeProject && (signals.kbSearchResults?.value || []).length === 0 && text && text.trim().length > 0) {
    try {
      const r = await api.searchProject(_activeProject, text, 10);
      const results = r.results || [];
      if (results.length > 0) {
        signals.kbSearchResults.value = results;
        signals.kbSelectedChunkIds.value = results.map((x) => x.chunk_id);
      }
    } catch (err) {
      // Soft-fail: send without context rather than blocking the user.
      console.warn('KB search failed, sending without context:', err.message);
    }
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
  // History: für Assistant-Messages bevorzugen wir `rawResponse` — das ist
  // der LLM-Output vor der Rehydrierung und enthält bereits die Codenames.
  // Ein Flag `already_anonymized` sagt dem Server dass er diese Message
  // NICHT erneut durch engine.anonymize() schicken soll (verhindert
  // Codename-Drift zwischen Turns und unzuverlässige Re-Detection auf
  // schon anonymisiertem Text). User-Messages enthalten Originaltext und
  // brauchen die normale Anonymisierung.
  const history = newMessages.slice(0, -1).map((m) => {
    if (m.role === 'assistant' && m.rawResponse) {
      return { role: 'assistant', content: m.rawResponse, already_anonymized: true };
    }
    return { role: m.role, content: m.content };
  });

  const attachments = signals.pendingAttachments.value;
  let fullMessage = text;
  if (attachments.length) {
    // CRITICAL: only the anonymized version may be forwarded to the AI.
    // The previous fallback chain `extracted_text || anonymized_text` leaked
    // the ORIGINAL text (which the server sends as a 500-char preview for
    // the UI only). That defeats the whole purpose of the tool. The server
    // guarantees `anonymized_text` contains the full anonymised content,
    // so we use it exclusively.
    const attachTexts = attachments
      .map((a) => {
        const body = (a.anonymized_text || '').trim();
        if (!body) {
          // Image-redact / empty-document uploads: tell the AI a file is
          // attached but no textual content was extracted.
          return `[Datei angehängt: ${a.filename} — kein Textinhalt]`;
        }
        return `[Datei: ${a.filename}]\n${body}`;
      })
      .join('\n\n');
    // Put the user's question AFTER the file content so the AI reads the
    // material first and then the instruction ("was siehst du?" -> answer
    // about the anonymised document instead of guessing it was an image).
    fullMessage = text
      ? `${attachTexts}\n\nFrage zur angehängten Datei: ${text}`
      : attachTexts;
    signals.pendingAttachments.value = [];
  }

  signals.isStreaming.value = true;
  let streamedText = '';
  let meta = null;
  const msgIdx = newMessages.length;
  // Push the placeholder into messages so MessageList knows there is a
  // streaming bubble at this index. Content lives in signals.streamingContent
  // (StreamingMessage subscribes to that signal). signals.messages stays
  // STABLE during the stream so MessageList does not re-render per token.
  signals.messages.value = [...newMessages, { role: 'assistant', content: '', meta: null }];
  signals.streamingMsgIdx.value = msgIdx;
  signals.streamingContent.value = '';
  if (signals.streamingThinking) signals.streamingThinking.value = '';
  let thinkingText = '';

  // Payload assembly. Auto-Routing wurde am 25.04.2026 aus dem Default-UX
  // entfernt (siehe project_austrai_pivot_skills_kb_plan.md). Modellwahl
  // läuft jetzt über Header-Dropdown plus opt-in Slash-Befehle. Advanced-
  // Parameter (reasoning/temperature/top_p/max_tokens) werden nur gesendet
  // wenn advanced_mode an ist; das Backend droppt stillschweigend Werte,
  // die das gewählte Modell nicht unterstützt.
  const settings = signals.settings.value || {};
  const payload = { message: fullMessage, provider, model, history, system_prompt: '', conversation_id: convId };
  const advancedActive = !!settings.advanced_mode;
  if (advancedActive) {
    payload.reasoning_effort = settings.reasoning_effort || 'medium';
    if (settings.temperature !== undefined) payload.temperature = settings.temperature;
    if (settings.top_p !== undefined) payload.top_p = settings.top_p;
    if (settings.max_tokens) payload.max_tokens = settings.max_tokens;
  }

  // Phase 2: skill activation. Either explicit (header dropdown) or
  // implicit via /<skill-slug> slash command. Slash beats header so the
  // user can override per-message without changing the dropdown.
  const activeSkill = skillSlugFromSlash || signals.activeSkillSlug?.value || '';
  if (activeSkill) {
    payload.skill_slug = activeSkill;
  }

  // Phase 3: knowledge base attached chunks (Anti-Magic-RAG). The user
  // has explicitly confirmed which retrieved snippets to attach via the
  // chunk-preview checkboxes. Only those reach the LLM.
  const activeProject = signals.activeProjectSlug?.value || '';
  const selectedChunks = signals.kbSelectedChunkIds?.value || [];
  if (activeProject && selectedChunks.length) {
    payload.project_slug = activeProject;
    payload.attached_chunk_ids = [...selectedChunks];
  }
  // Clear selected chunks after building the payload — they apply to
  // exactly one send. Next message gets a fresh retrieval.
  if (signals.kbSelectedChunkIds) signals.kbSelectedChunkIds.value = [];
  if (signals.kbSearchResults) signals.kbSearchResults.value = [];

  abortHandle = api.streamMessage(
    payload,
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
        // Write ONLY to the isolated streaming signal. The MessageList does
        // NOT re-render — only the dedicated <StreamingMessage /> bubble
        // does, because Preact-Signals tracks its single subscription.
        signals.streamingContent.value = streamedText;
      },
      onThinking(content) {
        // Extended-Thinking deltas (Anthropic) — accumulate and surface
        // in the streaming bubble's reasoning block.
        if (!content) return;
        thinkingText += content;
        if (signals.streamingThinking) signals.streamingThinking.value = thinkingText;
      },
      onDone(data) {
        // Reset the streaming-isolation signals: from now on the message
        // belongs in signals.messages and MessageList will swap StreamingMessage
        // for the regular MessageBubble (which does markdown + KaTeX + badges).
        signals.streamingMsgIdx.value = -1;
        signals.streamingContent.value = '';
        if (signals.streamingThinking) signals.streamingThinking.value = '';
        if (data.full_response) streamedText = data.full_response;
        const msgs = [...signals.messages.value];
        if (msgs[msgIdx]) {
          msgs[msgIdx] = {
            role: 'assistant',
            content: streamedText,
            meta,
            // Explicit provider/model for the model-badge on assistant bubbles.
            // Prefer meta (authoritative — reflects auto-routed picks) over
            // the outer request values (what the user selected in the header).
            provider: meta?.provider || provider,
            model: meta?.model || model,
            // Persist the thinking text on the message so the regular
            // MessageBubble can render the same collapsible block after
            // the stream finishes. Stays in localStorage; not sent back
            // to the LLM in subsequent turns.
            thinking: thinkingText || null,
            doneData: data,
            rawResponse: data.raw_response || null,
          };
        }
        if (meta && msgs[msgIdx - 1]) {
          msgs[msgIdx - 1] = { ...msgs[msgIdx - 1], meta };
        }
        // Guard: User hat ggf. während des Streams "Neuer Chat" oder eine
        // andere Konversation angeklickt. In dem Fall darf der Stream-Done
        // nicht in die aktive View schreiben — sonst würden fremde Messages
        // in der neuen Konversation erscheinen. Der DB-Write landet
        // trotzdem in der ursprünglichen Konversation (convId im Closure).
        const stillActive = convId === signals.currentConversationId.value;
        if (stillActive) {
          signals.messages.value = msgs;
        }
        saveMessages(convId, msgs);
        signals.isStreaming.value = false;
        refreshList();
        const stats = signals.sessionStats.value;
        signals.sessionStats.value = { ...stats, restored: stats.restored + (data.restored_count || 0) };
      },
      onError(error) {
        // Reset streaming-isolation signals so the placeholder bubble
        // becomes a regular MessageBubble that can render the error UI.
        signals.streamingMsgIdx.value = -1;
        signals.streamingContent.value = '';
        if (signals.streamingThinking) signals.streamingThinking.value = '';
        // Server now sends a structured object:
        //   { error: "...", status: 401, provider: "anthropic", model: "claude-…" }
        // We also handle legacy string errors and transport-level Error objects.
        let errObj = { message: 'Unbekannter Fehler' };
        if (error && typeof error === 'object') {
          errObj.message = error.error || error.message || error.detail || JSON.stringify(error);
          if (error.status) errObj.status = error.status;
          if (error.provider) errObj.provider = error.provider;
          if (error.model) errObj.model = error.model;
        } else if (error) {
          errObj.message = String(error);
        }
        // If the message itself is a serialized Anthropic/OpenAI error JSON,
        // unwrap the human-readable part.
        try {
          if (errObj.message && errObj.message.startsWith('{')) {
            const parsed = JSON.parse(errObj.message);
            if (parsed?.error?.message) errObj.message = parsed.error.message;
            else if (parsed?.message) errObj.message = parsed.message;
          }
        } catch { /* best effort */ }
        // Fill in context if server didn't: what WE attempted to send.
        errObj.provider = errObj.provider || meta?.provider || provider;
        errObj.model = errObj.model || meta?.model || model;
        // UX-Hint ableiten: häufige Fehlercodes zu handlungsorientierten Hinweisen.
        const low = (errObj.message || '').toLowerCase();
        if (errObj.status === 401 || /authenti(cation|zieru)|invalid.*api.?key/i.test(low)) {
          errObj.hint = 'API-Key prüfen: Einstellungen → Providers → Prüfen. Ggf. rotieren und neu eintragen.';
        } else if (errObj.status === 404 || /not.?found|does not exist/i.test(low)) {
          errObj.hint = 'Dieses Modell existiert beim Provider nicht (oder der Key hat keinen Zugriff). Ein anderes Modell aus dem Dropdown probieren.';
        } else if (errObj.status === 429 || /rate.?limit/i.test(low)) {
          errObj.hint = 'Rate-Limit erreicht. Kurz warten, dann neu senden.';
        } else if (errObj.status === 400 && /(budget.?tokens|max.?tokens)/i.test(low)) {
          errObj.hint = 'Max-Tokens in Erweiterten Einstellungen erhöhen, oder Reasoning-Tiefe reduzieren.';
        } else if (/overloaded|service.*unavailable/i.test(low)) {
          errObj.hint = 'Provider gerade überlastet. Kurz warten oder anderes Modell wählen.';
        }

        const msgs = [...signals.messages.value];
        if (msgs[msgIdx]) {
          msgs[msgIdx] = {
            role: 'assistant',
            content: '',
            error: errObj,
            provider: errObj.provider,
            model: errObj.model,
          };
        }
        signals.messages.value = msgs;
        signals.isStreaming.value = false;
        // Kurzer Toast-Ping als akustischer Cue; die eigentliche Info steht
        // jetzt in der Chat-History.
        toast(errObj.message.slice(0, 120), 'error', 5000);
      },
      onComplete() {
        // Defensive: ensure streaming signals are reset even if onDone/onError
        // didn't fire (transport-level abort, etc.).
        if (signals.streamingMsgIdx.value !== -1) {
          signals.streamingMsgIdx.value = -1;
          signals.streamingContent.value = '';
        }
        if (signals.streamingThinking?.value) signals.streamingThinking.value = '';
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

  // Knowledge-base live search: while a project is active, retrieve
  // candidate snippets in the background as the user types. This makes
  // Send a single click (snippets are visible and pre-selected before
  // Send fires), instead of the old two-click confirm flow.
  let _kbSearchTimer = null;
  let _kbLastQuery = '';

  function triggerKbSearch(text) {
    const project = signals.activeProjectSlug?.value || '';
    if (!project) return;
    const trimmed = (text || '').trim();
    if (trimmed.length < 8) {
      // Too short to be a meaningful query — clear the preview.
      signals.kbSearchResults.value = [];
      signals.kbSelectedChunkIds.value = [];
      return;
    }
    if (trimmed === _kbLastQuery) return;
    _kbLastQuery = trimmed;
    api.searchProject(project, trimmed, 10).then((r) => {
      // Only apply if the project is still active and the user has not
      // already started a stream (avoid race when send fires concurrently).
      if (signals.activeProjectSlug.value !== project) return;
      if (signals.isStreaming.value) return;
      const results = r?.results || [];
      signals.kbSearchResults.value = results;
      // Default selection: all results pre-checked. User can untick what
      // they don't want before clicking Send.
      signals.kbSelectedChunkIds.value = results.map((x) => x.chunk_id);
    }).catch(() => { /* silent — preview just stays empty */ });
  }

  inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + 'px';
    // Closing the preview on typing feels right — if the user keeps editing,
    // the old preview is stale anyway.
    if (signals.pendingPreview.value) signals.pendingPreview.value = null;
    // Debounced KB search.
    if (_kbSearchTimer) clearTimeout(_kbSearchTimer);
    _kbSearchTimer = setTimeout(() => triggerKbSearch(inputEl.value), 400);
  });

  // Switching project clears the preview state.
  signals.activeProjectSlug?.subscribe(() => {
    _kbLastQuery = '';
    signals.kbSearchResults.value = [];
    signals.kbSelectedChunkIds.value = [];
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
