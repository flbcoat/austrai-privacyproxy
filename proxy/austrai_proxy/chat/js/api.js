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

export const validateKey = (provider, api_key, ollama_url, lmstudio_url) =>
  request('/validate-key', {
    method: 'POST',
    body: JSON.stringify({ provider, api_key, ollama_url, lmstudio_url }),
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

export function streamMessage(payload, callbacks) {
  // Rest-spread the entire payload — chat.js builds the full object
  // (provider, model, history, advanced params, skill_slug, project_slug,
  // attached_chunk_ids, ...). Lock-and-key allow-listing here used to
  // silently drop new fields.
  const controller = new AbortController();

  fetch(`${BASE}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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
              case 'meta':     callbacks.onMeta?.(data);             break;
              case 'done':     callbacks.onDone?.(data);             break;
              case 'error':    callbacks.onError?.(data);            break;
              case 'thinking': callbacks.onThinking?.(data.content); break;
              default:         callbacks.onToken?.(data.content);    break;
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

/* ---- Skills (Phase 2 of pivot) ---- */

export const listSkills   = ()         => request('/skills');
export const saveSkill    = (skill)    => request('/skills', { method: 'PUT', body: JSON.stringify(skill) });
export const deleteSkill  = (slug)     => request(`/skills/${encodeURIComponent(slug)}`, { method: 'DELETE' });

/* ---- Knowledge base / Projects (Phase 3) ---- */

export const listProjects   = ()                     => request('/projects');
export const createProject  = (data)                 => request('/projects', { method: 'POST', body: JSON.stringify(data) });
export const updateProject  = (slug, data)           => request(`/projects/${encodeURIComponent(slug)}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteProject  = (slug)                 => request(`/projects/${encodeURIComponent(slug)}`, { method: 'DELETE' });
export const listProjectDocs = (slug)                => request(`/projects/${encodeURIComponent(slug)}/docs`);
export const inspectProjectChunks = (slug, filename) => request(`/projects/${encodeURIComponent(slug)}/chunks?filename=${encodeURIComponent(filename)}`);
export const reindexProjectDoc     = (slug, filename, extraDenyTerms = [], persistGlobally = true) =>
  request(`/projects/${encodeURIComponent(slug)}/reindex`, {
    method: 'POST',
    body: JSON.stringify({ filename, extra_deny_terms: extraDenyTerms, persist_globally: persistGlobally }),
  });
export const deleteProjectDoc = (slug, filename)     => request(`/projects/${encodeURIComponent(slug)}/doc?filename=${encodeURIComponent(filename)}`, { method: 'DELETE' });
export const searchProject  = (slug, query, top_k=5) => request(`/projects/${encodeURIComponent(slug)}/search`, { method: 'POST', body: JSON.stringify({ query, top_k }) });

export function uploadProjectDoc(slug, file, onProgress) {
  // XHR (not fetch) because fetch's body upload progress is not yet
  // widely supported. XHR.upload.progress fires reliably across browsers.
  // Returns a Promise that resolves with the parsed JSON response, or
  // rejects with an Error whose message is the backend's error string.
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append('file', file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/projects/${encodeURIComponent(slug)}/upload`);
    xhr.upload.addEventListener('progress', (e) => {
      if (!onProgress) return;
      // Two phases the user cares about:
      //   1) Network upload (this event)
      //   2) Server-side anonymisation + chunking + embedding (no progress
      //      events from the server today; we collapse it into a fake
      //      "processing" state once upload hits 100%).
      const pct = e.lengthComputable ? Math.round((e.loaded / e.total) * 100) : null;
      onProgress({ phase: 'upload', percent: pct, loaded: e.loaded, total: e.total });
    });
    xhr.upload.addEventListener('load', () => {
      onProgress?.({ phase: 'processing', percent: 100 });
    });
    xhr.addEventListener('load', () => {
      onProgress?.({ phase: 'done', percent: 100 });
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data.error || `HTTP ${xhr.status}`));
      } catch (err) {
        reject(new Error(`Bad server response (${xhr.status})`));
      }
    });
    xhr.addEventListener('error', () => reject(new Error('Upload network error')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));
    xhr.send(fd);
  });
}
