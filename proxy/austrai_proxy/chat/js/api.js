/**
 * AUSTR.AI — API Client
 * Wraps all backend endpoints at /chat/api/*
 */

const BASE = '/chat/api';

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ---- Settings & Config ---- */

export const getSettings    = ()     => request('/settings');
export const putSettings    = (data) => request('/settings', { method: 'PUT', body: JSON.stringify(data) });
export const getProviders   = ()     => request('/providers');
export const getSystemInfo  = ()     => request('/system-info');

export const validateKey = (provider, api_key, ollama_url) =>
  request('/validate-key', {
    method: 'POST',
    body: JSON.stringify({ provider, api_key, ollama_url }),
  });

/* ---- Conversations ---- */

export const listConversations   = ()           => request('/conversations');
export const createConversation  = (data = {})  => request('/conversations', { method: 'POST', body: JSON.stringify(data) });
export const getConversation     = (id)         => request(`/conversations/${id}`);
export const updateConversation  = (id, data)   => request(`/conversations/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteConversation  = (id)         => request(`/conversations/${id}`, { method: 'DELETE' });

/* ---- Privacy ---- */

export const dismissTerm   = (term, permanent = false) =>
  request('/dismiss', { method: 'POST', body: JSON.stringify({ term, permanent }) });

export const addToAllowList = (term) =>
  request('/allow-list/add', { method: 'POST', body: JSON.stringify({ term }) });

/* ---- Debug / Transparency ---- */

export const debugTest  = (text) => request('/debug/test', { method: 'POST', body: JSON.stringify({ text }) });
export const debugLog   = (limit = 20) => request(`/debug/log?limit=${limit}`);
export const debugClear = () => request('/debug/clear', { method: 'POST' });

/* ---- File Operations ---- */

export async function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'Upload failed');
  return res.json();
}

export async function redactImage(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/redact`, { method: 'POST', body: form });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'Redaction failed');
  return res.json();
}

/* ---- Chat (SSE Streaming) ---- */

export function streamMessage({ message, provider, model, history, system_prompt }, callbacks) {
  const controller = new AbortController();

  fetch(`${BASE}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, provider, model, history, system_prompt }),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      callbacks.onError?.(err.error || `HTTP ${res.status}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let currentEvent = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            switch (currentEvent) {
              case 'meta':  callbacks.onMeta?.(data);         break;
              case 'done':  callbacks.onDone?.(data);         break;
              case 'error': callbacks.onError?.(data.error);  break;
              default:      callbacks.onToken?.(data.content); break;
            }
          } catch { /* skip unparseable */ }
          currentEvent = '';
        } else if (line.trim() === '') {
          currentEvent = '';
        }
      }
    }

    callbacks.onComplete?.();
  }).catch((err) => {
    if (err.name !== 'AbortError') callbacks.onError?.(err.message);
  });

  return { abort: () => controller.abort() };
}
