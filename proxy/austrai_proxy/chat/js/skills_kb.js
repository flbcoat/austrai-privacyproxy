/**
 * AUSTR.AI — Skills & Knowledge Base UI components.
 *
 * Phase 2 + 3 of the 04/2026 pivot. Both features share this module
 * because they have parallel CRUD shapes and live next to each other in
 * Settings + the chat header. Privacy invariant (enforced by backend):
 * skill bodies and KB chunks always pass through the anonymisation
 * pipeline before LLM send.
 */

import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, batch, toast } from './state.js';
import { useSignalValue } from './hooks.js';
import * as api from './api.js';

const html = htm.bind(h);

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

/* ===========================================================
 * Skills Tab — list / create / edit / delete user-defined skills
 * =========================================================== */

export function SkillsTab() {
  const lang = useSignalValue(signals.language);
  const skills = useSignalValue(signals.skills);
  const providers = useSignalValue(signals.providers);
  const [editing, setEditing] = useState(null); // null | 'new' | slug

  async function refresh() {
    const data = await api.listSkills().catch(() => ({ skills: [] }));
    signals.skills.value = data.skills || [];
  }

  return html`
    <div class="aai-tab-content active">
      <div style="background:var(--bg-subtle);border-left:3px solid var(--accent);padding:12px 16px;margin-bottom:16px;border-radius:4px">
        <div style="font-weight:500;margin-bottom:4px">
          ${lang === 'de' ? 'Skills (Profis)' : 'Skills (specialists)'}
        </div>
        <p style="font-size:12px;color:var(--text-muted);margin:0">
          ${lang === 'de'
            ? 'Lege eigene „Profis" an: ein System-Prompt + Modell-Empfehlung. Im Chat wählst du den Skill im Header oder via /<slug>. Der Skill-Inhalt wird vor jedem Send anonymisiert wie alle anderen Texte.'
            : 'Define your own specialists: a system prompt + recommended model. Pick a skill in the chat header or via /<slug>. Skill content is anonymised before every send like everything else.'}
        </p>
      </div>

      ${editing
        ? html`<${SkillEditor}
            slug=${editing === 'new' ? '' : editing}
            providers=${providers}
            lang=${lang}
            onSave=${async () => { await refresh(); setEditing(null); }}
            onCancel=${() => setEditing(null)}
          />`
        : html`
          <div style="display:flex;justify-content:flex-end;margin-bottom:12px">
            <button class="aai-btn aai-btn--primary aai-btn--sm" onClick=${() => setEditing('new')}>
              ${lang === 'de' ? '+ Neuer Skill' : '+ New skill'}
            </button>
          </div>
          ${(skills || []).length === 0
            ? html`<div style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px;border:1px dashed var(--border);border-radius:8px">
                ${lang === 'de' ? 'Noch keine Skills angelegt.' : 'No skills yet.'}
              </div>`
            : html`<div style="display:flex;flex-direction:column;gap:8px">
                ${skills.map((s) => html`
                  <div key=${s.slug} style="border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
                    <div style="flex:1;min-width:0">
                      <div style="font-weight:500">${s.name} <code style="font-size:11px;color:var(--text-muted);font-weight:normal">/${s.slug}</code></div>
                      ${s.description ? html`<div style="font-size:12px;color:var(--text-muted);margin-top:2px">${s.description}</div>` : null}
                      ${s.recommended_model ? html`
                        <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
                          ${lang === 'de' ? 'Empfohlen:' : 'Recommended:'} ${s.recommended_provider}/${s.recommended_model}
                        </div>` : null}
                    </div>
                    <div style="display:flex;gap:6px;flex-shrink:0">
                      <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${() => setEditing(s.slug)}>
                        ${lang === 'de' ? 'Bearbeiten' : 'Edit'}
                      </button>
                      <button class="aai-btn aai-btn--ghost aai-btn--sm" style="color:var(--danger,#c14)" onClick=${async () => {
                        if (!confirm(lang === 'de' ? `Skill „${s.name}" wirklich löschen?` : `Delete skill "${s.name}"?`)) return;
                        try { await api.deleteSkill(s.slug); await refresh(); toast(lang === 'de' ? 'Gelöscht' : 'Deleted', 'success'); }
                        catch (err) { toast(err.message, 'error'); }
                      }}>
                        ${lang === 'de' ? 'Löschen' : 'Delete'}
                      </button>
                    </div>
                  </div>
                `)}
              </div>`}
        `}
    </div>
  `;
}

function SkillEditor({ slug, providers, lang, onSave, onCancel }) {
  const isNew = !slug;
  const existing = !isNew ? (signals.skills.value || []).find((s) => s.slug === slug) : null;
  const [draftSlug, setDraftSlug] = useState(slug || '');
  const [name, setName] = useState(existing?.name || '');
  const [description, setDescription] = useState(existing?.description || '');
  const [provider, setProvider] = useState(existing?.recommended_provider || '');
  const [model, setModel] = useState(existing?.recommended_model || '');
  const [systemPrompt, setSystemPrompt] = useState(existing?.system_prompt || '');
  const [busy, setBusy] = useState(false);

  const providerModels = (providers && providers[provider] && providers[provider].models) || [];

  async function handleSave() {
    const cleanSlug = draftSlug.trim().toLowerCase();
    if (!SLUG_RE.test(cleanSlug)) {
      toast(lang === 'de' ? 'Slug ungültig (a-z, 0-9, -, _)' : 'Invalid slug (a-z, 0-9, -, _)', 'error');
      return;
    }
    if (!name.trim()) {
      toast(lang === 'de' ? 'Name erforderlich' : 'Name required', 'error');
      return;
    }
    if (!systemPrompt.trim()) {
      toast(lang === 'de' ? 'System-Prompt erforderlich' : 'System prompt required', 'error');
      return;
    }
    setBusy(true);
    try {
      await api.saveSkill({
        slug: cleanSlug,
        name: name.trim(),
        description: description.trim(),
        recommended_provider: provider || '',
        recommended_model: model || '',
        system_prompt: systemPrompt,
      });
      toast(lang === 'de' ? 'Gespeichert' : 'Saved', 'success');
      onSave?.();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return html`
    <div style="border:1px solid var(--border);border-radius:8px;padding:16px;display:flex;flex-direction:column;gap:12px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="aai-field">
          <label>${lang === 'de' ? 'Slug (URL-tauglich)' : 'Slug (url-safe)'}</label>
          <input class="aai-input" disabled=${!isNew} value=${draftSlug} onInput=${(e) => setDraftSlug(e.target.value)} placeholder="rechts-skill" />
        </div>
        <div class="aai-field">
          <label>${lang === 'de' ? 'Anzeigename' : 'Display name'}</label>
          <input class="aai-input" value=${name} onInput=${(e) => setName(e.target.value)} placeholder="${lang === 'de' ? 'Rechts-Skill' : 'Legal skill'}" />
        </div>
      </div>
      <div class="aai-field">
        <label>${lang === 'de' ? 'Kurzbeschreibung (optional)' : 'Short description (optional)'}</label>
        <input class="aai-input" value=${description} onInput=${(e) => setDescription(e.target.value)} placeholder="${lang === 'de' ? 'Anwalt für Mietrecht in Wien' : 'Tenancy lawyer in Vienna'}" />
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="aai-field">
          <label>${lang === 'de' ? 'Empfohlener Provider' : 'Recommended provider'}</label>
          <select class="aai-select" value=${provider} onChange=${(e) => { setProvider(e.target.value); setModel(''); }}>
            <option value="">${lang === 'de' ? '(keiner)' : '(none)'}</option>
            ${Object.entries(providers || {}).filter(([k, v]) => k !== '_meta' && v?.configured).map(([k, v]) => html`<option value=${k}>${v.name || k}</option>`)}
          </select>
        </div>
        <div class="aai-field">
          <label>${lang === 'de' ? 'Empfohlenes Modell' : 'Recommended model'}</label>
          <select class="aai-select" value=${model} onChange=${(e) => setModel(e.target.value)} disabled=${!provider}>
            <option value="">${lang === 'de' ? '(keines)' : '(none)'}</option>
            ${providerModels.map((m) => html`<option value=${m.id}>${m.name || m.id}</option>`)}
          </select>
        </div>
      </div>
      <div class="aai-field">
        <label>${lang === 'de' ? 'System-Prompt' : 'System prompt'}</label>
        <textarea class="aai-input" rows="8" style="font-family:ui-monospace,monospace;font-size:13px" value=${systemPrompt} onInput=${(e) => setSystemPrompt(e.target.value)} placeholder="${lang === 'de' ? 'Du bist ein erfahrener ... Antworte präzise auf Deutsch.' : 'You are an experienced ... Answer precisely in English.'}"></textarea>
        <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
          ${lang === 'de'
            ? 'Wird vor jedem Send anonymisiert (PII-Codenames, Brackets) wie der User-Text.'
            : 'Anonymised before every send (PII codenames, brackets) like the user message.'}
        </div>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px">
        <button class="aai-btn aai-btn--ghost" onClick=${onCancel} disabled=${busy}>${lang === 'de' ? 'Abbrechen' : 'Cancel'}</button>
        <button class="aai-btn aai-btn--primary" onClick=${handleSave} disabled=${busy}>${lang === 'de' ? 'Speichern' : 'Save'}</button>
      </div>
    </div>
  `;
}


/* ===========================================================
 * Knowledge Base Tab — projects / documents / upload
 * =========================================================== */

export function KnowledgeTab() {
  const lang = useSignalValue(signals.language);
  const projects = useSignalValue(signals.projects);
  const [creating, setCreating] = useState(false);
  const [openSlug, setOpenSlug] = useState(null);

  async function refresh() {
    const data = await api.listProjects().catch(() => ({ projects: [] }));
    signals.projects.value = data.projects || [];
  }

  return html`
    <div class="aai-tab-content active">
      <div style="background:var(--bg-subtle);border-left:3px solid var(--accent);padding:12px 16px;margin-bottom:16px;border-radius:4px">
        <div style="font-weight:500;margin-bottom:4px">
          ${lang === 'de' ? 'Wissensbasis' : 'Knowledge base'}
        </div>
        <p style="font-size:12px;color:var(--text-muted);margin:0">
          ${lang === 'de'
            ? 'Lege Projekte an und lade Dokumente (PDF, Docx, Txt). Sie werden lokal gespeichert und VOR der Indexierung anonymisiert. Im Chat wählst du ein Projekt im Header — vor jedem Send siehst du die gefundenen Snippets und entscheidest, welche du an die KI mitschickst.'
            : 'Create projects and upload documents (PDF, Docx, Txt). They are stored locally and anonymised BEFORE indexing. Pick a project in the chat header — before each send you see candidate snippets and decide which to attach.'}
        </p>
      </div>

      ${creating
        ? html`<${ProjectCreator} lang=${lang} onSaved=${async (newSlug) => { await refresh(); setCreating(false); setOpenSlug(newSlug); }} onCancel=${() => setCreating(false)} />`
        : html`
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px">
            <div style="font-size:12px;color:var(--text-muted)">
              ${lang === 'de'
                ? '1. Projekt anlegen  →  2. Dokumente hochladen  →  3. Im Chat-Header auswählen'
                : '1. Create project  →  2. Upload documents  →  3. Select in chat header'}
            </div>
            <button class="aai-btn aai-btn--primary aai-btn--sm" onClick=${() => setCreating(true)}>
              ${lang === 'de' ? '+ Neues Projekt' : '+ New project'}
            </button>
          </div>
          ${(projects || []).length === 0
            ? html`<div style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px;border:1px dashed var(--border);border-radius:8px">
                ${lang === 'de' ? 'Noch keine Projekte angelegt. Klicke oben rechts auf „Neues Projekt", danach kannst du Dokumente hochladen.' : 'No projects yet. Click "New project" top right, then upload documents.'}
              </div>`
            : html`<div style="display:flex;flex-direction:column;gap:8px">
                ${projects.map((p) => html`
                  <${ProjectCard}
                    key=${p.slug}
                    project=${p}
                    open=${openSlug === p.slug}
                    onToggle=${() => setOpenSlug(openSlug === p.slug ? null : p.slug)}
                    lang=${lang}
                    onChanged=${refresh}
                  />
                `)}
              </div>`}
        `}
    </div>
  `;
}

function ProjectCreator({ lang, onSaved, onCancel }) {
  const [slug, setSlug] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSave() {
    const cleanSlug = slug.trim().toLowerCase();
    if (!SLUG_RE.test(cleanSlug)) {
      toast(lang === 'de' ? 'Slug ungültig (a-z, 0-9, -, _)' : 'Invalid slug (a-z, 0-9, -, _)', 'error');
      return;
    }
    if (!name.trim()) {
      toast(lang === 'de' ? 'Name erforderlich' : 'Name required', 'error');
      return;
    }
    setBusy(true);
    try {
      await api.createProject({ slug: cleanSlug, name: name.trim(), description: description.trim() });
      toast(lang === 'de' ? 'Projekt angelegt — jetzt kannst du Dokumente hochladen.' : 'Project created — you can now upload documents.', 'success', 4000);
      onSaved?.(cleanSlug);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return html`
    <div style="border:1px solid var(--border);border-radius:8px;padding:16px;display:flex;flex-direction:column;gap:12px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="aai-field">
          <label>${lang === 'de' ? 'Slug (URL-tauglich)' : 'Slug (url-safe)'}</label>
          <input class="aai-input" value=${slug} onInput=${(e) => setSlug(e.target.value)} placeholder="mietrecht" />
        </div>
        <div class="aai-field">
          <label>${lang === 'de' ? 'Anzeigename' : 'Display name'}</label>
          <input class="aai-input" value=${name} onInput=${(e) => setName(e.target.value)} placeholder="Mietrecht-Korpus" />
        </div>
      </div>
      <div class="aai-field">
        <label>${lang === 'de' ? 'Beschreibung (optional)' : 'Description (optional)'}</label>
        <input class="aai-input" value=${description} onInput=${(e) => setDescription(e.target.value)} />
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px">
        <button class="aai-btn aai-btn--ghost" onClick=${onCancel} disabled=${busy}>${lang === 'de' ? 'Abbrechen' : 'Cancel'}</button>
        <button class="aai-btn aai-btn--primary" onClick=${handleSave} disabled=${busy}>${lang === 'de' ? 'Anlegen' : 'Create'}</button>
      </div>
    </div>
  `;
}

function ProjectCard({ project, open, onToggle, lang, onChanged }) {
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(null); // { phase, percent }

  useEffect(() => {
    if (open) refreshDocs();
  }, [open, project.slug]);

  async function refreshDocs() {
    try {
      const d = await api.listProjectDocs(project.slug);
      setDocs(d.documents || []);
    } catch (err) { /* ignore */ }
  }

  async function handleUpload(file) {
    setUploading(true);
    setProgress({ phase: 'upload', percent: 0 });
    try {
      const r = await api.uploadProjectDoc(project.slug, file, (p) => setProgress(p));
      toast(`${file.name}: ${r.chunks_added} Chunks, ${r.entities_anonymized} PII-Treffer anonymisiert. Bitte unten die anonymisierten Snippets prüfen.`, 'success', 6000);
      await refreshDocs();
      onChanged?.();
      // Auto-open the inspector for the just-uploaded file so the user can
      // immediately verify what landed in the index. Privacy guarantee
      // (Florian's hard rule): every upload should be visually confirmed
      // before the doc is used in chat retrieval.
      openInspect(file.name);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setUploading(false);
      setProgress(null);
    }
  }

  // Two-click inline confirm. Replaces window.confirm() because Safari /
  // Chrome can suppress dialogs after "stop showing dialogs" — silent
  // failure mode where the button click does nothing visible. Inline
  // confirm makes the state visible and never blocks.
  const [pendingDelDoc, setPendingDelDoc] = useState(null);
  const [pendingDelProject, setPendingDelProject] = useState(false);

  function armDeleteDoc(filename) {
    if (pendingDelDoc === filename) {
      setPendingDelDoc(null);
      handleDeleteDoc(filename);
    } else {
      setPendingDelDoc(filename);
      setTimeout(() => {
        setPendingDelDoc((prev) => (prev === filename ? null : prev));
      }, 4000);
    }
  }

  function armDeleteProject() {
    if (pendingDelProject) {
      setPendingDelProject(false);
      handleDeleteProject();
    } else {
      setPendingDelProject(true);
      setTimeout(() => setPendingDelProject(false), 4000);
    }
  }

  async function handleDeleteDoc(filename) {
    try {
      await api.deleteProjectDoc(project.slug, filename);
      await refreshDocs();
      onChanged?.();
      toast(lang === 'de' ? `„${filename}" entfernt` : `"${filename}" removed`, 'success', 2500);
    } catch (err) { toast(err.message || 'Delete failed', 'error'); }
  }

  const [inspectFilename, setInspectFilename] = useState(null);
  const [inspectChunks, setInspectChunks] = useState([]);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [denyDraft, setDenyDraft] = useState('');
  const [reindexing, setReindexing] = useState(false);

  async function openInspect(filename) {
    setInspectFilename(filename);
    setInspectChunks([]);
    setDenyDraft('');
    setInspectLoading(true);
    try {
      const r = await api.inspectProjectChunks(project.slug, filename);
      setInspectChunks(r.chunks || []);
    } catch (err) { toast(err.message, 'error'); }
    finally { setInspectLoading(false); }
  }

  function closeInspect() {
    setInspectFilename(null);
    setInspectChunks([]);
    setDenyDraft('');
  }

  async function handleReindex() {
    if (!inspectFilename) return;
    // Parse deny-list draft: split by newline OR comma, trim, dedupe.
    const terms = Array.from(new Set(
      denyDraft.split(/[\n,]+/).map((s) => s.trim()).filter((s) => s.length >= 1 && s.length <= 200)
    ));
    setReindexing(true);
    try {
      const r = await api.reindexProjectDoc(project.slug, inspectFilename, terms, true);
      toast(`Re-indexiert: ${r.chunks_added} Chunks, ${r.entities_anonymized} Treffer (Deny-Liste: ${r.deny_list_size})`, 'success', 5500);
      // Reload chunks so user sees the new anonymised state.
      const refreshed = await api.inspectProjectChunks(project.slug, inspectFilename);
      setInspectChunks(refreshed.chunks || []);
      setDenyDraft('');
      await refreshDocs();
      onChanged?.();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setReindexing(false);
    }
  }

  async function handleDeleteProject() {
    try {
      await api.deleteProject(project.slug);
      toast(lang === 'de' ? `Projekt „${project.name}" gelöscht` : `Project "${project.name}" deleted`, 'success', 2500);
      onChanged?.();
    } catch (err) { toast(err.message || 'Delete failed', 'error'); }
  }

  return html`
    <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <div style="padding:12px 14px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;background:${open ? 'var(--bg-subtle)' : 'transparent'}" onClick=${onToggle}>
        <div>
          <div style="font-weight:500">${project.name}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:2px">
            <code>/${project.slug}</code> · ${project.doc_count} ${lang === 'de' ? 'Dokumente' : 'docs'} · ${project.chunk_count} ${lang === 'de' ? 'Chunks' : 'chunks'}
          </div>
        </div>
        <div style="font-size:14px;color:var(--text-muted)">${open ? '▾' : '▸'}</div>
      </div>
      ${open ? html`
        <div style="padding:12px 14px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:10px">
          <label style="display:inline-block;padding:8px 12px;border:1px dashed var(--border);border-radius:6px;text-align:center;cursor:pointer;font-size:13px">
            ${uploading ? (lang === 'de' ? 'Wird hochgeladen…' : 'Uploading…') : (lang === 'de' ? '📎 Dokument hochladen (PDF, Docx, Txt)' : '📎 Upload document (PDF, Docx, Txt)')}
            <input type="file" style="display:none" accept=".pdf,.docx,.txt,.md" disabled=${uploading} onChange=${(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = ''; }} />
          </label>
          ${uploading && progress ? html`
            <div style="display:flex;flex-direction:column;gap:4px">
              <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted)">
                <span>
                  ${progress.phase === 'upload'
                    ? (lang === 'de' ? '1/3 Hochladen' : '1/3 Uploading')
                    : progress.phase === 'processing'
                    ? (lang === 'de' ? '2/3 Anonymisieren + Chunks erzeugen…' : '2/3 Anonymising + chunking…')
                    : (lang === 'de' ? '3/3 Fertig' : '3/3 Done')}
                </span>
                <span>${typeof progress.percent === 'number' ? progress.percent + '%' : ''}</span>
              </div>
              <div style="height:6px;background:var(--bg-subtle);border-radius:3px;overflow:hidden">
                <div style="height:100%;background:var(--accent);width:${typeof progress.percent === 'number' ? progress.percent : (progress.phase === 'processing' ? 100 : 0)}%;transition:width 200ms ease;${progress.phase === 'processing' ? 'animation:aai-pulse 1.4s ease-in-out infinite;' : ''}"></div>
              </div>
              ${progress.phase === 'processing' ? html`
                <div style="font-size:11px;color:var(--text-muted);font-style:italic">
                  ${lang === 'de'
                    ? 'Server prüft den Text auf personenbezogene Daten und legt anonymisierte Snippets an. Das kann bei großen Dokumenten 10-30 Sekunden dauern.'
                    : 'Server is scanning the text for personal data and indexing anonymised snippets. May take 10-30 seconds for large documents.'}
                </div>
              ` : null}
            </div>
          ` : null}
          ${docs.length === 0
            ? html`<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:8px">
                ${lang === 'de' ? 'Noch keine Dokumente in diesem Projekt.' : 'No documents in this project yet.'}
              </div>`
            : html`<div style="display:flex;flex-direction:column;gap:4px">
                ${docs.map((d) => html`
                  <div key=${d.filename} style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;background:var(--bg-subtle);border-radius:4px;font-size:12px;gap:6px">
                    <div style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📄 ${d.filename} <span style="color:var(--text-muted)">· ${d.chunk_count} ${lang === 'de' ? 'Chunks' : 'chunks'} · ${(d.size_bytes / 1024).toFixed(0)} KB</span></div>
                    <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${() => openInspect(d.filename)} title=${lang === 'de' ? 'Anonymisierte Chunks anzeigen' : 'Show anonymised chunks'}>
                      🔍 ${lang === 'de' ? 'Prüfen' : 'Inspect'}
                    </button>
                    <button
                      class="aai-btn aai-btn--ghost aai-btn--sm"
                      style="color:var(--danger,#c14);${pendingDelDoc === d.filename ? 'background:rgba(220,38,38,0.1);font-weight:600' : ''}"
                      onClick=${(e) => { e.stopPropagation(); armDeleteDoc(d.filename); }}
                    >
                      ${pendingDelDoc === d.filename
                        ? (lang === 'de' ? 'Wirklich? Klick' : 'Confirm?')
                        : (lang === 'de' ? 'Entfernen' : 'Remove')}
                    </button>
                  </div>
                `)}
              </div>`}
          ${inspectFilename ? html`
            <div style="margin-top:6px;border:1px solid var(--border);border-radius:6px;padding:10px 12px;background:var(--bg)">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <div style="font-weight:500;font-size:12px">
                  ${lang === 'de' ? 'Anonymisierte Chunks für' : 'Anonymised chunks for'}: <code>${inspectFilename}</code>
                </div>
                <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${closeInspect}>×</button>
              </div>
              <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;padding:6px 8px;background:var(--bg-subtle);border-radius:4px">
                ${lang === 'de'
                  ? 'Das ist exakt der Text, der in der Wissensbasis liegt und an die KI geschickt wird. Wenn hier noch Klartext-PII zu sehen ist, wurde sie vom Detector beim Upload nicht erkannt — trag den fehlenden Begriff unten in die Deny-Liste ein und klick „Erneut anonymisieren".'
                  : 'This is the exact text stored in the knowledge base and sent to the AI. Plain-text PII visible here means the detector missed it at upload time — add the missed term to the deny list below and click "Re-anonymise".'}
              </div>

              <!-- Inline deny-list editor for this document -->
              <div style="border:1px dashed var(--border);border-radius:4px;padding:8px 10px;margin-bottom:10px">
                <div style="font-size:11px;font-weight:500;margin-bottom:4px">
                  ${lang === 'de' ? 'Zusätzliche Begriffe zur Deny-Liste hinzufügen' : 'Add extra terms to the deny list'}
                </div>
                <textarea
                  rows="3"
                  class="aai-input"
                  style="font-family:ui-monospace,monospace;font-size:12px;width:100%;resize:vertical"
                  placeholder=${lang === 'de' ? 'Ein Begriff pro Zeile (oder durch Komma getrennt). Beispiel: Ferdinand Porsche-Ring 3' : 'One term per line (or comma-separated). E.g. Ferdinand Porsche-Ring 3'}
                  value=${denyDraft}
                  onInput=${(e) => setDenyDraft(e.target.value)}
                  disabled=${reindexing}
                ></textarea>
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px">
                  <div style="font-size:11px;color:var(--text-muted)">
                    ${lang === 'de'
                      ? 'Diese Begriffe landen in der globalen Deny-Liste (Settings → Privacy) und schützen auch zukünftige Uploads.'
                      : 'Terms are added to the global deny list (Settings → Privacy) and protect future uploads too.'}
                  </div>
                  <button
                    class="aai-btn aai-btn--primary aai-btn--sm"
                    onClick=${handleReindex}
                    disabled=${reindexing}
                  >
                    ${reindexing
                      ? (lang === 'de' ? 'Re-indexiere…' : 'Re-indexing…')
                      : (lang === 'de' ? '🔄 Erneut anonymisieren' : '🔄 Re-anonymise')}
                  </button>
                </div>
              </div>
              ${inspectLoading
                ? html`<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">${lang === 'de' ? 'Lade…' : 'Loading…'}</div>`
                : inspectChunks.length === 0
                  ? html`<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">${lang === 'de' ? 'Keine Chunks gefunden.' : 'No chunks found.'}</div>`
                  : html`<div style="display:flex;flex-direction:column;gap:6px;max-height:360px;overflow-y:auto">
                      ${inspectChunks.map((c) => html`
                        <div key=${c.chunk_id} style="border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:11px">
                          <div style="color:var(--text-muted);margin-bottom:4px">#chunk${c.chunk_index} · id=${c.chunk_id} · ${c.anonymized_text.length} ${lang === 'de' ? 'Zeichen' : 'chars'}</div>
                          <div style="font-family:ui-monospace,monospace;white-space:pre-wrap;word-break:break-word;line-height:1.45">${c.anonymized_text}</div>
                        </div>
                      `)}
                    </div>`}
            </div>
          ` : null}
          <div style="display:flex;justify-content:flex-end;margin-top:6px">
            <button
              class="aai-btn aai-btn--ghost aai-btn--sm"
              style="color:var(--danger,#c14);${pendingDelProject ? 'background:rgba(220,38,38,0.1);font-weight:600' : ''}"
              onClick=${(e) => { e.stopPropagation(); armDeleteProject(); }}
            >
              ${pendingDelProject
                ? (lang === 'de' ? 'Wirklich? Klick zum Bestätigen' : 'Confirm? Click again')
                : (lang === 'de' ? 'Projekt löschen' : 'Delete project')}
            </button>
          </div>
        </div>
      ` : null}
    </div>
  `;
}


/* ===========================================================
 * Slash-Aliases Editor — used inside the Advanced settings tab
 * =========================================================== */

export function SlashAliasesEditor({ value, onChange, providers, lang }) {
  const [draft, setDraft] = useState(() => Object.entries(value || {}).map(([slug, v]) => ({ slug, provider: v.provider, model: v.model })));

  function commit(next) {
    setDraft(next);
    const obj = {};
    for (const row of next) {
      if (SLUG_RE.test((row.slug || '').toLowerCase()) && row.provider && row.model) {
        obj[row.slug.toLowerCase()] = { provider: row.provider, model: row.model };
      }
    }
    onChange?.(obj);
  }

  function setRow(idx, patch) {
    commit(draft.map((r, i) => i === idx ? { ...r, ...patch } : r));
  }

  function addRow() {
    setDraft([...draft, { slug: '', provider: '', model: '' }]);
  }

  function removeRow(idx) {
    commit(draft.filter((_, i) => i !== idx));
  }

  return html`
    <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">
      ${draft.map((row, idx) => {
        const provModels = (providers && providers[row.provider] && providers[row.provider].models) || [];
        return html`
          <div key=${idx} style="display:grid;grid-template-columns:140px 140px 1fr auto;gap:6px;align-items:center">
            <input class="aai-input" style="padding:4px 8px;font-size:12px" value=${row.slug} onInput=${(e) => setRow(idx, { slug: e.target.value })} placeholder="alias" />
            <select class="aai-select" style="padding:4px 8px;font-size:12px" value=${row.provider} onChange=${(e) => setRow(idx, { provider: e.target.value, model: '' })}>
              <option value="">${lang === 'de' ? '(Provider)' : '(provider)'}</option>
              ${Object.entries(providers || {}).filter(([k, v]) => k !== '_meta' && v?.configured).map(([k, v]) => html`<option value=${k}>${v.name || k}</option>`)}
            </select>
            <select class="aai-select" style="padding:4px 8px;font-size:12px" value=${row.model} onChange=${(e) => setRow(idx, { model: e.target.value })} disabled=${!row.provider}>
              <option value="">${lang === 'de' ? '(Modell)' : '(model)'}</option>
              ${row.provider === 'lmstudio' || row.provider === 'ollama'
                ? html`<option value="__local__">${lang === 'de' ? 'Erstes lokales Modell' : 'First local model'}</option>` : null}
              ${provModels.map((m) => html`<option value=${m.id}>${m.name || m.id}</option>`)}
            </select>
            <button class="aai-btn aai-btn--ghost aai-btn--sm" style="color:var(--danger,#c14)" onClick=${() => removeRow(idx)}>×</button>
          </div>
        `;
      })}
      <button class="aai-btn aai-btn--ghost aai-btn--sm" style="align-self:flex-start;margin-top:4px" onClick=${addRow}>
        ${lang === 'de' ? '+ Alias hinzufügen' : '+ Add alias'}
      </button>
    </div>
  `;
}


/* ===========================================================
 * Header controls — Skill + Project dropdowns next to model picker
 * =========================================================== */

export function HeaderSkillProject() {
  const lang = useSignalValue(signals.language);
  const skills = useSignalValue(signals.skills);
  const projects = useSignalValue(signals.projects);
  const activeSkill = useSignalValue(signals.activeSkillSlug);
  const activeProject = useSignalValue(signals.activeProjectSlug);

  function handleSkillChange(slug) {
    signals.activeSkillSlug.value = slug;
    // Skill recommendation: if skill has recommended_provider+model, set
    // header model to it. User can override afterwards.
    if (slug) {
      const sk = skills.find((s) => s.slug === slug);
      if (sk?.recommended_provider && sk?.recommended_model) {
        batch({ provider: sk.recommended_provider, model: sk.recommended_model });
        api.putSettings({ default_provider: sk.recommended_provider, default_model: sk.recommended_model }).catch(() => {});
      }
    }
  }

  function handleProjectChange(slug) {
    batch({ activeProjectSlug: slug, kbSearchResults: [], kbSelectedChunkIds: [] });
  }

  return html`
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      ${(skills && skills.length) ? html`
        <select class="aai-select" style="padding:4px 8px;font-size:12px" value=${activeSkill || ''} onChange=${(e) => handleSkillChange(e.target.value)} title=${lang === 'de' ? 'Skill (Profi)' : 'Skill'}>
          <option value="">${lang === 'de' ? 'Skill: keiner' : 'Skill: none'}</option>
          ${skills.map((s) => html`<option value=${s.slug}>${lang === 'de' ? 'Skill: ' : 'Skill: '}${s.name}</option>`)}
        </select>
      ` : null}
      ${(projects && projects.length) ? html`
        <select class="aai-select" style="padding:4px 8px;font-size:12px" value=${activeProject || ''} onChange=${(e) => handleProjectChange(e.target.value)} title=${lang === 'de' ? 'Wissensbasis' : 'Knowledge base'}>
          <option value="">${lang === 'de' ? 'Wissensbasis: keine' : 'KB: none'}</option>
          ${projects.map((p) => html`<option value=${p.slug}>${lang === 'de' ? 'KB: ' : 'KB: '}${p.name}</option>`)}
        </select>
      ` : null}
    </div>
  `;
}


/* ===========================================================
 * Anti-Magic-RAG snippet preview — shown above the chat input
 * when a project is active. User checks which snippets to attach
 * BEFORE sending. No automatic attachment.
 * =========================================================== */

export function KnowledgeSnippetPreview() {
  const lang = useSignalValue(signals.language);
  const activeProject = useSignalValue(signals.activeProjectSlug);
  const projects = useSignalValue(signals.projects);
  const results = useSignalValue(signals.kbSearchResults);
  const [expanded, setExpanded] = useState(false);

  if (!activeProject || !results || results.length === 0) return null;

  const projectName = (projects || []).find((p) => p.slug === activeProject)?.name || activeProject;

  // The preview is now a compact, friendly status indicator. All retrieved
  // snippets are auto-attached on send (Privacy unchanged — LLM only ever
  // sees anonymised text). The user can expand to see ORIGINAL text
  // (locally rehydrated for readability — never sent to the LLM in this
  // form) or remove the knowledge base for this turn.
  return html`
    <div style="border:1px solid var(--border);border-radius:8px;background:var(--bg-subtle);padding:8px 12px;margin-bottom:8px;font-size:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
        <div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0;cursor:pointer" onClick=${() => setExpanded(!expanded)}>
          <span style="font-size:14px">📚</span>
          <div style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            <strong>${results.length}</strong> ${lang === 'de' ? 'passende Stellen aus' : 'relevant snippets from'}
            <em>„${projectName}"</em>
            ${lang === 'de' ? 'werden mitgesendet' : 'will be attached'}
          </div>
          <span style="font-size:11px;color:var(--text-muted)">${expanded ? '▾' : '▸'}</span>
        </div>
        <button
          class="aai-btn aai-btn--ghost aai-btn--sm"
          style="flex-shrink:0"
          onClick=${(e) => { e.stopPropagation(); batch({ kbSearchResults: [], kbSelectedChunkIds: [] }); }}
          title=${lang === 'de' ? 'Snippets für diese Frage nicht mitsenden' : 'Skip snippets for this question'}
        >
          ${lang === 'de' ? 'Nicht mitsenden' : 'Skip'}
        </button>
      </div>
      ${expanded ? html`
        <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border);max-height:240px;overflow-y:auto">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:2px">
            ${lang === 'de'
              ? '🔒 Vorschau in Klartext (nur lokal). An die KI gehen die Snippets anonymisiert.'
              : '🔒 Preview in plain text (local only). The AI receives anonymised snippets.'}
          </div>
          ${results.map((r) => html`
            <div key=${r.chunk_id} style="padding:6px 8px;background:var(--bg);border-radius:4px;font-size:12px">
              <div style="font-size:11px;color:var(--text-muted);margin-bottom:2px">📄 ${r.doc_filename} · #${r.chunk_index}</div>
              <div style="white-space:pre-wrap;word-break:break-word;line-height:1.45">${(r.original_text || r.anonymized_text).slice(0, 400)}${(r.original_text || r.anonymized_text).length > 400 ? '…' : ''}</div>
            </div>
          `)}
        </div>
      ` : null}
    </div>
  `;
}
