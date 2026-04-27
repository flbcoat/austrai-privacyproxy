"""AUSTR.AI Wissensbasis (Knowledge Base / Projects).

Projects are user-defined document collections for retrieval-augmented chat.
Each project lives at ~/.austrai/projects/<slug>/ with this layout:

    meta.yaml           — name, description, created_at
    docs/               — original document files (read-only after upload)
    chunks.sqlite       — anonymised chunks + embeddings (no plain-text PII)

Privacy invariants enforced by this module:

    1. Documents are anonymised BEFORE storage. The anonymised chunks
       become the chromadb / sqlite content. The original files stay
       in docs/ on the user's device but are NEVER sent to an LLM.
    2. The chat send-path uses an explicit per-message snippet selection
       (Florian's "Anti-Magic-RAG" rule). Retrieval surfaces candidate
       snippets to the user; only those the user confirms are attached
       to the prompt. There is no automatic context injection.
    3. Mappings (codename -> original) are persisted in the existing
       global MappingStore (Fernet-encrypted SQLite). Project upload
       reuses that store — no parallel vault.

The retrieval index uses sqlite + cosine similarity over float32
embeddings packed as bytes. We avoid chromadb to keep dependency surface
small and to make the schema readable.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .config import CONFIG_DIR

logger = logging.getLogger("austrai.projects")

PROJECTS_DIR = CONFIG_DIR / "projects"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# Chunking: ~500 token windows with 50 token overlap, character-approximated.
# Token-accurate chunking would need tiktoken/transformers — overkill here.
_CHUNK_CHARS = 1800  # ~500 tokens at 3.6 chars/token (German average)
_CHUNK_OVERLAP = 180


@dataclass
class Project:
    slug: str
    name: str
    description: str = ""
    created_at: float = 0.0
    doc_count: int = 0
    chunk_count: int = 0

    def to_public_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name or self.slug,
            "description": self.description,
            "created_at": self.created_at,
            "doc_count": self.doc_count,
            "chunk_count": self.chunk_count,
        }


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug or ""))


def _project_dir(slug: str) -> Path:
    return PROJECTS_DIR / slug


def _meta_path(slug: str) -> Path:
    return _project_dir(slug) / "meta.yaml"


def _db_path(slug: str) -> Path:
    return _project_dir(slug) / "chunks.sqlite"


def _docs_dir(slug: str) -> Path:
    return _project_dir(slug) / "docs"


def _ensure_db(slug: str) -> sqlite3.Connection:
    """Open (or initialise) the per-project chunk store. Performs an
    additive schema upgrade for the mappings_json column added in the
    de-anonymisation fix (26.04.2026)."""
    db_path = _db_path(slug)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_filename TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            anonymized_text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_filename)")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    if "mappings_json" not in cols:
        # Existing chunks (if any) get an empty mapping dict, which means
        # codenames they introduced will not be rehydrated until re-upload.
        conn.execute("ALTER TABLE chunks ADD COLUMN mappings_json TEXT DEFAULT '{}'")
    conn.commit()
    return conn


def _load_meta(slug: str) -> Optional[dict]:
    path = _meta_path(slug)
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load meta for %s: %s", slug, e)
        return None


def _save_meta(slug: str, data: dict) -> None:
    _project_dir(slug).mkdir(parents=True, exist_ok=True)
    _meta_path(slug).write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def list_projects() -> list[Project]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    out: list[Project] = []
    for path in PROJECTS_DIR.iterdir():
        if not path.is_dir() or not is_valid_slug(path.name):
            continue
        meta = _load_meta(path.name) or {}
        out.append(Project(
            slug=path.name,
            name=str(meta.get("name", path.name)),
            description=str(meta.get("description", "")),
            created_at=float(meta.get("created_at", 0.0)),
            doc_count=_count_docs(path.name),
            chunk_count=_count_chunks(path.name),
        ))
    out.sort(key=lambda p: p.name.lower())
    return out


def _count_docs(slug: str) -> int:
    d = _docs_dir(slug)
    return len([p for p in d.iterdir() if p.is_file()]) if d.exists() else 0


def _count_chunks(slug: str) -> int:
    db_path = _db_path(slug)
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(db_path)
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        conn.close()
        return int(n)
    except sqlite3.Error:
        return 0


def get_project(slug: str) -> Optional[Project]:
    if not is_valid_slug(slug):
        return None
    meta = _load_meta(slug)
    if meta is None:
        return None
    return Project(
        slug=slug,
        name=str(meta.get("name", slug)),
        description=str(meta.get("description", "")),
        created_at=float(meta.get("created_at", 0.0)),
        doc_count=_count_docs(slug),
        chunk_count=_count_chunks(slug),
    )


def create_project(slug: str, name: str, description: str = "") -> Project:
    if not is_valid_slug(slug):
        raise ValueError(f"Invalid project slug: {slug!r}")
    if _project_dir(slug).exists():
        raise ValueError(f"Project already exists: {slug}")
    _save_meta(slug, {
        "name": name or slug,
        "description": description,
        "created_at": time.time(),
    })
    _docs_dir(slug).mkdir(parents=True, exist_ok=True)
    return Project(slug=slug, name=name or slug, description=description, created_at=time.time())


def update_project(slug: str, name: Optional[str] = None, description: Optional[str] = None) -> Optional[Project]:
    meta = _load_meta(slug)
    if meta is None:
        return None
    if name is not None:
        meta["name"] = name
    if description is not None:
        meta["description"] = description
    _save_meta(slug, meta)
    return get_project(slug)


def delete_project(slug: str) -> bool:
    if not is_valid_slug(slug):
        return False
    d = _project_dir(slug)
    if not d.exists():
        return False
    import shutil
    try:
        shutil.rmtree(d)
        return True
    except OSError as e:
        logger.warning("Failed to delete project %s: %s", slug, e)
        return False


# ---------------------------------------------------------------------------
# Chunking + Embedding
# ---------------------------------------------------------------------------


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks. Naive char-based, sufficient for
    retrieval precision in the sub-50-doc range.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= _CHUNK_CHARS:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_CHARS, len(text))
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - _CHUNK_OVERLAP
    return [c for c in chunks if c]


_embedding_model = None


def _get_embedder():
    """Lazy-load sentence-transformers. Reused across calls."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers not installed. Install austrai[memory] "
                "or austrai[routing] to enable knowledge base retrieval."
            ) from e
        # Same model the auto-router uses, so we share the on-disk cache.
        _embedding_model = SentenceTransformer(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
    return _embedding_model


def _pack_embedding(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def add_document(
    slug: str,
    filename: str,
    anonymized_text: str,
    mappings: Optional[dict] = None,
) -> int:
    """Chunk + embed an already-anonymised document. Returns # of chunks added.

    Caller (chat_api endpoint) is responsible for running the document
    through engine.anonymize() before calling this — we do NOT accept
    plain text into the index (defensive privacy invariant: the index
    must never hold un-anonymised content).

    `mappings` is the codename->original lookup produced by the
    anonymiser. We persist it per-chunk so the rehydrator can resolve
    placeholders that the LLM reproduces from retrieved context.
    """
    if not is_valid_slug(slug):
        raise ValueError(f"Invalid project slug: {slug!r}")
    chunks = chunk_text(anonymized_text)
    if not chunks:
        return 0
    embedder = _get_embedder()
    vectors = embedder.encode(chunks, show_progress_bar=False)
    conn = _ensure_db(slug)
    now = time.time()
    # We attach the FULL mapping dict to every chunk for simplicity.
    # Per-chunk filtering (only mappings whose codename appears in the
    # chunk text) would save bytes but add fragility; the dicts are
    # small relative to the embeddings.
    mappings_blob = json.dumps(mappings or {}, ensure_ascii=False)
    with conn:
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            conn.execute(
                "INSERT INTO chunks (doc_filename, chunk_index, anonymized_text, embedding, created_at, mappings_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (filename, i, chunk, _pack_embedding(vec), now, mappings_blob),
            )
    conn.close()
    return len(chunks)


def remove_document(slug: str, filename: str) -> int:
    """Delete chunks for a given doc. Returns # of chunks removed."""
    db_path = _db_path(slug)
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    with conn:
        cur = conn.execute("DELETE FROM chunks WHERE doc_filename = ?", (filename,))
        deleted = cur.rowcount or 0
    conn.close()
    return int(deleted)


def list_chunks_for_doc(slug: str, filename: str) -> list[dict]:
    """Inspector view — returns the anonymised text of every chunk that
    belongs to a given document. Used by the UI's "Snippets prüfen"
    button so the user can verify what is actually stored (and therefore
    what would be sent to an LLM as context). No mappings, no plain text,
    just the anonymised payload as it sits in the index."""
    db_path = _db_path(slug)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, chunk_index, anonymized_text FROM chunks WHERE doc_filename = ? ORDER BY chunk_index",
        (filename,),
    ).fetchall()
    conn.close()
    return [
        {"chunk_id": cid, "chunk_index": idx, "anonymized_text": txt}
        for cid, idx, txt in rows
    ]


def list_documents(slug: str) -> list[dict]:
    """Return per-doc summaries: filename + chunk count + bytes."""
    docs_dir = _docs_dir(slug)
    if not docs_dir.exists():
        return []
    db_path = _db_path(slug)
    counts: dict[str, int] = {}
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        for fn, n in conn.execute("SELECT doc_filename, COUNT(*) FROM chunks GROUP BY doc_filename"):
            counts[fn] = n
        conn.close()
    out = []
    for path in sorted(docs_dir.iterdir()):
        if not path.is_file():
            continue
        out.append({
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "chunk_count": counts.get(path.name, 0),
        })
    return out


def _rehydrate_text(anonymized_text: str, mappings: dict) -> str:
    """Local-only de-anonymisation for UI preview. The mapping dict comes
    from the chunk's own mappings_json column (built at upload time).
    Codenames are simple substring replacements ordered by length descending
    so longer codenames replace before shorter ones (avoids "Arion" leaking
    into "Arion Schmidt" if the latter were also a codename).

    NEVER call this on text destined for an LLM — it deliberately undoes
    the privacy boundary. UI-only.
    """
    if not mappings or not anonymized_text:
        return anonymized_text
    out = anonymized_text
    for codename in sorted(mappings.keys(), key=len, reverse=True):
        original = mappings[codename]
        if codename and original:
            out = out.replace(codename, original)
    return out


def search(slug: str, anonymized_query: str, top_k: int = 5) -> list[dict]:
    """Return top-k matching chunks for an anonymised query.

    The query MUST be already anonymised by the caller. We do not anonymise
    here because retrieval happens BEFORE the user clicks Send — the same
    query the LLM will eventually see.

    Each result also carries `original_text` (rehydrated via the chunk's
    own mappings) — UI-only field for friendly snippet display. The chat
    send-path uses `anonymized_text` exclusively; original_text never
    leaves the UI.
    """
    db_path = _db_path(slug)
    if not db_path.exists():
        return []
    if not anonymized_query.strip():
        return []
    embedder = _get_embedder()
    qvec = list(embedder.encode([anonymized_query], show_progress_bar=False)[0])
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    has_mappings = "mappings_json" in cols
    if has_mappings:
        rows = conn.execute(
            "SELECT id, doc_filename, chunk_index, anonymized_text, embedding, mappings_json FROM chunks"
        ).fetchall()
    else:
        rows = [
            (cid, fn, idx, txt, blob, "{}")
            for cid, fn, idx, txt, blob in conn.execute(
                "SELECT id, doc_filename, chunk_index, anonymized_text, embedding FROM chunks"
            ).fetchall()
        ]
    conn.close()
    scored = []
    for cid, fn, idx, txt, blob, mj in rows:
        score = _cosine(qvec, _unpack_embedding(blob))
        try:
            mp = json.loads(mj) if mj else {}
            if not isinstance(mp, dict):
                mp = {}
        except (json.JSONDecodeError, TypeError):
            mp = {}
        scored.append((score, cid, fn, idx, txt, mp))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "chunk_id": cid,
            "doc_filename": fn,
            "chunk_index": idx,
            "anonymized_text": txt,
            "original_text": _rehydrate_text(txt, mp),
            "score": float(score),
        }
        for score, cid, fn, idx, txt, mp in scored[:top_k]
    ]


def get_chunks_by_id(slug: str, chunk_ids: list[int]) -> list[dict]:
    """Fetch specific chunks by id, including their mappings_json blob.
    Used by chat send-path when the user confirms which retrieved
    snippets to attach. The mappings are merged into the global
    rehydrator dict so codenames the LLM reproduces from chunk context
    get translated back to originals."""
    db_path = _db_path(slug)
    if not db_path.exists() or not chunk_ids:
        return []
    placeholders = ",".join("?" * len(chunk_ids))
    conn = sqlite3.connect(db_path)
    # Defensive: older rows may not have mappings_json yet.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    has_mappings = "mappings_json" in cols
    if has_mappings:
        rows = conn.execute(
            f"SELECT id, doc_filename, chunk_index, anonymized_text, mappings_json FROM chunks WHERE id IN ({placeholders})",
            list(chunk_ids),
        ).fetchall()
        conn.close()
        out = []
        for cid, fn, idx, txt, mj in rows:
            try:
                mp = json.loads(mj) if mj else {}
                if not isinstance(mp, dict):
                    mp = {}
            except (json.JSONDecodeError, TypeError):
                mp = {}
            out.append({"chunk_id": cid, "doc_filename": fn, "chunk_index": idx,
                        "anonymized_text": txt, "mappings": mp})
        return out
    rows = conn.execute(
        f"SELECT id, doc_filename, chunk_index, anonymized_text FROM chunks WHERE id IN ({placeholders})",
        list(chunk_ids),
    ).fetchall()
    conn.close()
    return [
        {"chunk_id": cid, "doc_filename": fn, "chunk_index": idx, "anonymized_text": txt, "mappings": {}}
        for cid, fn, idx, txt in rows
    ]


def get_document_path(slug: str, filename: str) -> Optional[Path]:
    """Return the on-disk path of an uploaded original, if it still exists.
    Used by the re-index endpoint to anonymise the document again with an
    extended deny-list."""
    if not is_valid_slug(slug):
        return None
    safe = re.sub(r"[^\w.\-]", "_", filename)[:200]
    if not safe:
        return None
    p = _docs_dir(slug) / safe
    return p if p.exists() else None


def save_document_file(slug: str, filename: str, data: bytes) -> Path:
    """Persist the raw upload to docs/. Returns the saved path. Filename is
    sanitised to prevent path traversal."""
    safe = re.sub(r"[^\w.\-]", "_", filename)[:200] or "untitled"
    docs = _docs_dir(slug)
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / safe
    path.write_bytes(data)
    return path
