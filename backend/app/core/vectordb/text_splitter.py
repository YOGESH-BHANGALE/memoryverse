"""
Recursive character text splitter — vendored, zero-dependency.

This is a faithful port of LangChain's ``RecursiveCharacterTextSplitter``
(``langchain_text_splitters.character`` + the ``_merge_splits`` logic from its
``base``), reduced to only what ``EmbeddingService`` uses: ``split_text``.

Why vendor it instead of importing?  ``langchain_text_splitters/__init__.py``
eagerly imports ``SentenceTransformersTokenTextSplitter``, which imports
``sentence_transformers`` → ``torch`` at module load. There is no lazy
``__getattr__``, so importing *any* symbol (even ``RecursiveCharacterTextSplitter``
or a submodule) drags PyTorch into the process. On a 512 MB free-tier container
that resident footprint leaves no headroom and OOM-kills the worker mid-upload.
Copying the ~90 lines of pure-``re`` logic here keeps chunking behaviour byte-for-byte
identical while removing torch from the runtime entirely.

Only ``re`` from the stdlib is needed.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Literal

logger = logging.getLogger(__name__)


def _split_text_with_regex(
    text: str, separator: str, *, keep_separator: bool | Literal["start", "end"]
) -> list[str]:
    """Split ``text`` on ``separator`` (a regex), optionally keeping the separator."""
    if separator:
        if keep_separator:
            # Parentheses keep the delimiters in the result.
            splits_ = re.split(f"({separator})", text)
            splits = (
                [splits_[i] + splits_[i + 1] for i in range(0, len(splits_) - 1, 2)]
                if keep_separator == "end"
                else [splits_[i] + splits_[i + 1] for i in range(1, len(splits_), 2)]
            )
            if len(splits_) % 2 == 0:
                splits += splits_[-1:]
            splits = (
                [*splits, splits_[-1]]
                if keep_separator == "end"
                else [splits_[0], *splits]
            )
        else:
            splits = re.split(separator, text)
    else:
        splits = list(text)
    return [s for s in splits if s]


class RecursiveCharacterTextSplitter:
    """
    Split text by recursively trying a list of separators, then merge the
    pieces into ``chunk_size``-bounded chunks with ``chunk_overlap`` carryover.

    Behaviour matches LangChain's class of the same name for the parameters we
    use (``keep_separator=True``, ``strip_whitespace=True``).
    """

    def __init__(
        self,
        separators: list[str] | None = None,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        length_function: Callable[[str], int] = len,
        keep_separator: bool | Literal["start", "end"] = True,
        is_separator_regex: bool = False,
        strip_whitespace: bool = True,
    ) -> None:
        if chunk_overlap > chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be <= chunk_size ({chunk_size})"
            )
        self._separators = separators or ["\n\n", "\n", " ", ""]
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._length_function = length_function
        self._keep_separator = keep_separator
        self._is_separator_regex = is_separator_regex
        self._strip_whitespace = strip_whitespace

    # ── merge helpers (from LangChain's TextSplitter base) ──────────────

    def _join_docs(self, docs: list[str], separator: str) -> str | None:
        text = separator.join(docs)
        if self._strip_whitespace:
            text = text.strip()
        return text or None

    def _merge_splits(self, splits, separator: str) -> list[str]:
        separator_len = self._length_function(separator)

        docs: list[str] = []
        current_doc: list[str] = []
        total = 0
        for d in splits:
            len_ = self._length_function(d)
            if (
                total + len_ + (separator_len if len(current_doc) > 0 else 0)
                > self._chunk_size
            ):
                if total > self._chunk_size:
                    logger.warning(
                        "Created a chunk of size %d, longer than the specified %d",
                        total,
                        self._chunk_size,
                    )
                if len(current_doc) > 0:
                    doc = self._join_docs(current_doc, separator)
                    if doc is not None:
                        docs.append(doc)
                    # Pop from the front to build the overlap for the next chunk.
                    while total > self._chunk_overlap or (
                        total + len_ + (separator_len if len(current_doc) > 0 else 0)
                        > self._chunk_size
                        and total > 0
                    ):
                        total -= self._length_function(current_doc[0]) + (
                            separator_len if len(current_doc) > 1 else 0
                        )
                        current_doc = current_doc[1:]
            current_doc.append(d)
            total += len_ + (separator_len if len(current_doc) > 1 else 0)
        doc = self._join_docs(current_doc, separator)
        if doc is not None:
            docs.append(doc)
        return docs

    # ── recursive split ─────────────────────────────────────────────────

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        final_chunks: list[str] = []
        separator = separators[-1]
        new_separators: list[str] = []
        for i, s_ in enumerate(separators):
            separator_ = s_ if self._is_separator_regex else re.escape(s_)
            if not s_:
                separator = s_
                break
            if re.search(separator_, text):
                separator = s_
                new_separators = separators[i + 1 :]
                break

        separator_ = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex(
            text, separator_, keep_separator=self._keep_separator
        )

        good_splits: list[str] = []
        merge_separator = "" if self._keep_separator else separator
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                good_splits.append(s)
            else:
                if good_splits:
                    final_chunks.extend(self._merge_splits(good_splits, merge_separator))
                    good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    final_chunks.extend(self._split_text(s, new_separators))
        if good_splits:
            final_chunks.extend(self._merge_splits(good_splits, merge_separator))
        return final_chunks

    def split_text(self, text: str) -> list[str]:
        """Split ``text`` into chunk_size-bounded chunks."""
        return self._split_text(text, self._separators)
