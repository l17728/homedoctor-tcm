"""BGE-M3 embedding wrapper with lazy load + graceful degradation.

The model is **never** loaded at import time. The first call to
:meth:`EmbeddingModel.embed` attempts to load ``BAAI/bge-m3`` via
``sentence-transformers``. If the library is missing or the model cannot be
downloaded, ``embed`` returns ``None`` and a warning is logged — callers must
fall back to BM25-only search.

Design (AGENTS.md §M5 本机先行, §F4 graceful degradation):
- Lazy singleton — one model instance per process, created on first use.
- All failures are caught and logged; no exception ever escapes to the caller.
- :func:`is_available` lets the pipeline report degradation status without
  triggering a load.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-m3"
DEFAULT_DIM = 1024


class EmbeddingModel:
    """Lazy-loading BGE-M3 embedding model with graceful degradation."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model_name = model_name
        self._model: Any = None
        self._loaded = False
        self._available: bool | None = None
        self._lock = threading.Lock()
        self._dim = DEFAULT_DIM

    def _try_load(self) -> bool:
        """Attempt to load the model. Returns True on success. Thread-safe."""
        with self._lock:
            if self._loaded:
                return self._available is True
            self._loaded = True
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            except ImportError:
                logger.warning(
                    "embedding: sentence-transformers not installed — "
                    "semantic search disabled, BM25-only mode."
                )
                self._available = False
                return False
            try:
                self._model = SentenceTransformer(self._model_name)
                test_vec = self._model.encode(["test"], normalize_embeddings=True)
                self._dim = len(test_vec[0])
                self._available = True
                logger.info(
                    "embedding: model %s loaded (dim=%d)", self._model_name, self._dim
                )
                return True
            except Exception as exc:
                logger.warning(
                    "embedding: failed to load %s — %s. "
                    "Semantic search disabled, BM25-only mode.",
                    self._model_name, exc,
                )
                self._model = None
                self._available = False
                return False

    @property
    def available(self) -> bool:
        """True if the model can produce embeddings (triggers a load check)."""
        if self._available is None:
            self._try_load()
        return self._available is True

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed a batch of texts. Returns ``None`` if the model is unavailable."""
        if not texts:
            return []
        if not self._try_load():
            return None
        if self._model is None:
            return None
        try:
            vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return [list(map(float, v)) for v in vecs]
        except Exception as exc:
            logger.warning("embedding: encode failed — %s", exc)
            return None

    def embed_one(self, text: str) -> list[float] | None:
        """Embed a single text. Returns ``None`` if unavailable."""
        result = self.embed([text])
        if result is None:
            return None
        return result[0] if result else None

    def reset(self) -> None:
        """Release the model (used by tests to force reload)."""
        with self._lock:
            self._model = None
            self._loaded = False
            self._available = None


_singleton: EmbeddingModel | None = None


def get_embedding_model() -> EmbeddingModel:
    """Return the process-wide :class:`EmbeddingModel` singleton."""
    global _singleton
    if _singleton is None:
        _singleton = EmbeddingModel()
    return _singleton


def is_available() -> bool:
    """Check (without forcing load side-effects beyond the check) availability."""
    return get_embedding_model().available
