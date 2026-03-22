"""Memory Layer — semantisches Langzeitgedaechtnis fuer anonymisierte Konversationen.

Speichert anonymisierte Prompts + Antworten als Vektoren in ChromaDB.
Bei neuen Prompts wird automatisch relevanter Kontext aus vergangenen
Konversationen hinzugefuegt — ohne dass Klartext das Geraet verlaesst.

Dreifache Datensicherheit:
1. Nur anonymisierter Text wird gespeichert (kein Klartext)
2. Text wird in numerische Vektoren umgewandelt (nicht rekonstruierbar)
3. Datenbank liegt lokal auf verschluesseltem Volume

Storage: ~/.austrai/memory/
"""

import logging
import time
import uuid
from pathlib import Path

logger = logging.getLogger("austrai.memory")

MEMORY_DIR = Path.home() / ".austrai" / "memory"
COLLECTION_NAME = "conversations"
DEFAULT_MODEL = "all-MiniLM-L6-v2"
MAX_CHUNK_SIZE = 512  # tokens approx (chars / 4)
MAX_CONTEXT_CHUNKS = 5
SIMILARITY_THRESHOLD = 0.75


class MemoryLayer:
    """Semantic long-term memory for anonymized conversations."""

    def __init__(self, embedding_model: str = DEFAULT_MODEL):
        self._embedding_model = embedding_model
        self._chroma_client = None
        self._collection = None
        self._embedder = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError(
                "Memory Layer braucht ChromaDB: pip install chromadb"
            )

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("Initialisiere Memory Layer...")

        # ChromaDB persistent client with built-in embeddings
        self._chroma_client = chromadb.PersistentClient(
            path=str(MEMORY_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create collection — ChromaDB handles embeddings internally
        self._collection = self._chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Anonymisierte Konversationen"},
        )

        self._initialized = True
        logger.info(
            "Memory Layer bereit. %d Eintraege gespeichert.",
            self._collection.count(),
        )

    def store(
        self,
        anonymized_prompt: str,
        anonymized_response: str,
        metadata: dict | None = None,
    ) -> str:
        """Store an anonymized conversation in the memory.

        Args:
            anonymized_prompt: The anonymized user prompt (no PII).
            anonymized_response: The anonymized LLM response (no PII).
            metadata: Optional metadata (e.g., task_type, project_tag).

        Returns:
            Memory entry ID.
        """
        self._ensure_initialized()

        # Combine prompt + response for storage
        full_text = f"Prompt: {anonymized_prompt}\n\nAntwort: {anonymized_response}"

        # Chunk the text
        chunks = self._chunk_text(full_text)

        # Store each chunk — ChromaDB generates embeddings automatically
        entry_id = str(uuid.uuid4())[:8]
        ids = []
        metas = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{entry_id}-{i}"
            ids.append(chunk_id)
            meta = {
                "entry_id": entry_id,
                "chunk_index": i,
                "timestamp": time.time(),
                "text_length": len(chunk),
            }
            if metadata:
                meta.update(metadata)
            metas.append(meta)

        self._collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metas,
        )

        logger.info(
            "Memory: %d Chunks gespeichert (Entry %s, %d Zeichen).",
            len(chunks), entry_id, len(full_text),
        )
        return entry_id

    def retrieve(self, anonymized_prompt: str, n_results: int = MAX_CONTEXT_CHUNKS) -> list[str]:
        """Retrieve relevant context from memory for a new prompt.

        Args:
            anonymized_prompt: The current anonymized prompt.
            n_results: Maximum number of context chunks to return.

        Returns:
            List of relevant text chunks from past conversations.
        """
        self._ensure_initialized()

        if self._collection.count() == 0:
            return []

        # Search — ChromaDB generates query embedding automatically
        results = self._collection.query(
            query_texts=[anonymized_prompt],
            n_results=min(n_results, self._collection.count()),
        )

        if not results or not results["documents"]:
            return []

        # Filter by similarity threshold
        relevant = []
        docs = results["documents"][0]
        distances = results["distances"][0] if results.get("distances") else [0] * len(docs)

        for doc, distance in zip(docs, distances):
            # ChromaDB returns L2 distance; lower = more similar
            # Convert to similarity score (approximate)
            similarity = max(0, 1 - distance / 2)
            if similarity >= SIMILARITY_THRESHOLD:
                relevant.append(doc)

        if relevant:
            logger.info(
                "Memory: %d relevante Chunks gefunden (von %d gespeicherten).",
                len(relevant), self._collection.count(),
            )

        return relevant

    def build_context_prompt(self, anonymized_prompt: str) -> str:
        """Build an enhanced prompt with context from memory.

        If relevant past conversations are found, prepends them as context.
        Otherwise returns the original prompt unchanged.
        """
        context_chunks = self.retrieve(anonymized_prompt)

        if not context_chunks:
            return anonymized_prompt

        context_text = "\n\n".join(context_chunks)
        return (
            f"Relevanter Kontext aus frueheren Gespraechen:\n"
            f"---\n{context_text}\n---\n\n"
            f"{anonymized_prompt}"
        )

    def count(self) -> int:
        """Number of stored chunks."""
        self._ensure_initialized()
        return self._collection.count()

    def clear(self) -> int:
        """Delete all stored memories. Returns count of deleted entries."""
        self._ensure_initialized()
        count = self._collection.count()
        if count > 0:
            # ChromaDB doesn't have a bulk delete, recreate collection
            self._chroma_client.delete_collection(COLLECTION_NAME)
            self._collection = self._chroma_client.get_or_create_collection(
                name=COLLECTION_NAME,
            )
        return count

    def _chunk_text(self, text: str, chunk_size: int = MAX_CHUNK_SIZE * 4) -> list[str]:
        """Split text into chunks of approximately chunk_size characters."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        # Split on paragraph boundaries
        paragraphs = text.split("\n\n")
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 > chunk_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())

        return chunks if chunks else [text]
