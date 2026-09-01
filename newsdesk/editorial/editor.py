"""Conservative editorial preparation engine."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from ..publishing.builder import BuiltArticle


class EditorialEngine:
    """
    Apply Devour Lincolnshire house-style improvements to a BuiltArticle.

    The engine is deliberately conservative:

    - it does not add facts
    - it does not alter direct quotations
    - it does not change names, dates, locations or figures
    - it removes common press-release language
    - it improves repetitive or awkward factual wording
    """

    QUOTE_PATTERN = re.compile(
        r'(["“][^"”]*["”]|[‘][^’]*[’])',
        re.DOTALL,
    )

    WHITESPACE_PATTERN = re.compile(r"[ \t]+")
    MULTIPLE_BREAKS_PATTERN = re.compile(r"\n{3,}")

    PRESS_RELEASE_REPLACEMENTS: tuple[
        tuple[re.Pattern[str], str],
        ...
    ] = (
        (
            re.compile(
                r"\bofficers from Nottinghamshire Police\b",
                re.IGNORECASE,
            ),
            "Nottinghamshire Police officers",
        ),
        (
            re.compile(
                r"\bofficers attended\b",
                re.IGNORECASE,
            ),
            "Police attended",
        ),
        (
            re.compile(
                r"\bofficers discovered\b",
                re.IGNORECASE,
            ),
            "Police discovered",
        ),
        (
            re.compile(
                r"\bofficers found\b",
                re.IGNORECASE,
            ),
            "Police found",
        ),
        (
            re.compile(
                r"\bofficers searched\b",
                re.IGNORECASE,
            ),
            "Police searched",
        ),
        (
            re.compile(
                r"\bofficers seized\b",
                re.IGNORECASE,
            ),
            "Police seized",
        ),
        (
            re.compile(
                r"\bofficers arrested\b",
                re.IGNORECASE,
            ),
            "Police arrested",
        ),
        (
            re.compile(
                r"\benquiries remain ongoing\b",
                re.IGNORECASE,
            ),
            "enquiries are continuing",
        ),
        (
            re.compile(
                r"\benquiries are ongoing\b",
                re.IGNORECASE,
            ),
            "enquiries are continuing",
        ),
        (
            re.compile(
                r"\binvestigations remain ongoing\b",
                re.IGNORECASE,
            ),
            "the investigation is continuing",
        ),
        (
            re.compile(
                r"\binvestigations are ongoing\b",
                re.IGNORECASE,
            ),
            "the investigation is continuing",
        ),
        (
            re.compile(
                r"\ba number of\b",
                re.IGNORECASE,
            ),
            "several",
        ),
        (
            re.compile(
                r"\bat this moment in time\b",
                re.IGNORECASE,
            ),
            "currently",
        ),
        (
            re.compile(
                r"\bat this stage\b",
                re.IGNORECASE,
            ),
            "currently",
        ),
        (
            re.compile(
                r"\bsubsequently\b",
                re.IGNORECASE,
            ),
            "later",
        ),
        (
            re.compile(
                r"\bhas now been jailed\b",
                re.IGNORECASE,
            ),
            "has been jailed",
        ),
        (
            re.compile(
                r"\bhave now been jailed\b",
                re.IGNORECASE,
            ),
            "have been jailed",
        ),
        (
            re.compile(
                r"\bwas subsequently arrested\b",
                re.IGNORECASE,
            ),
            "was later arrested",
        ),
        (
            re.compile(
                r"\bwere subsequently arrested\b",
                re.IGNORECASE,
            ),
            "were later arrested",
        ),
        (
            re.compile(
                r"\bmade their way to\b",
                re.IGNORECASE,
            ),
            "went to",
        ),
        (
            re.compile(
                r"\butilised\b",
                re.IGNORECASE,
            ),
            "used",
        ),
        (
            re.compile(
                r"\bcommenced\b",
                re.IGNORECASE,
            ),
            "began",
        ),
    )

    REDUNDANT_OPENINGS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"^Nottinghamshire Police has revealed that\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^Nottinghamshire Police has confirmed that\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^Police have confirmed that\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^It has been confirmed that\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^It has been revealed that\s+",
            re.IGNORECASE,
        ),
    )

    DUPLICATE_SENTENCE_PATTERN = re.compile(
        r"(?<=[.!?])\s+"
    )

    def edit(self, article: BuiltArticle) -> BuiltArticle:
        """Return an editorially prepared copy of a BuiltArticle."""

        title = self._edit_title(article.title)
        summary = self._edit_summary(
            article.summary,
            title=title,
        )

        paragraphs = self._edit_paragraphs(
            article.paragraphs,
            title=title,
            summary=summary,
        )

        return replace(
            article,
            title=title,
            summary=summary,
            paragraphs=paragraphs,
        )

    def _edit_title(self, title: Any) -> str:
        text = self._clean_spacing(title)

        if not text:
            return "Untitled story"

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip(" -–—")

    def _edit_summary(
        self,
        summary: Any,
        *,
        title: str,
    ) -> str:
        text = self._edit_text_preserving_quotes(summary)

        if not text:
            return ""

        if self._comparison_key(text) == self._comparison_key(title):
            return ""

        return self._ensure_terminal_punctuation(text)

    def _edit_paragraphs(
        self,
        paragraphs: list[str],
        *,
        title: str,
        summary: str,
    ) -> list[str]:
        edited: list[str] = []
        seen: set[str] = set()

        excluded = {
            self._comparison_key(title),
            self._comparison_key(summary),
        }

        for raw_paragraph in paragraphs:
            paragraph = self._edit_text_preserving_quotes(
                raw_paragraph
            )

            if not paragraph:
                continue

            paragraph = self._remove_repeated_sentences(
                paragraph
            )

            paragraph = self._ensure_terminal_punctuation(
                paragraph
            )

            key = self._comparison_key(paragraph)

            if not key:
                continue

            if key in excluded or key in seen:
                continue

            seen.add(key)
            edited.append(paragraph)

        return self._merge_short_paragraphs(edited)

    def _edit_text_preserving_quotes(
        self,
        value: Any,
    ) -> str:
        """
        Edit non-quoted text while leaving direct quotations unchanged.
        """

        text = self._clean_spacing(value)

        if not text:
            return ""

        parts = self.QUOTE_PATTERN.split(text)
        edited_parts: list[str] = []

        for part in parts:
            if not part:
                continue

            if self.QUOTE_PATTERN.fullmatch(part):
                edited_parts.append(part)
            else:
                edited_parts.append(
                    self._edit_unquoted_text(part)
                )

        return "".join(edited_parts).strip()

    def _edit_unquoted_text(self, text: str) -> str:
        edited = text

        for pattern in self.REDUNDANT_OPENINGS:
            edited = pattern.sub("", edited)

        for pattern, replacement in (
            self.PRESS_RELEASE_REPLACEMENTS
        ):
            edited = pattern.sub(
                lambda match: self._match_case(
                    match.group(0),
                    replacement,
                ),
                edited,
            )

        edited = re.sub(
            r"\bPolice police\b",
            "Police",
            edited,
            flags=re.IGNORECASE,
        )

        edited = re.sub(
            r"\bthe the\b",
            "the",
            edited,
            flags=re.IGNORECASE,
        )

        edited = re.sub(
            r"\bthat that\b",
            "that",
            edited,
            flags=re.IGNORECASE,
        )

        edited = re.sub(
            r"\s+([,.;:!?])",
            r"\1",
            edited,
        )

        edited = re.sub(
            r"([,.;:!?])([A-Za-z])",
            r"\1 \2",
            edited,
        )

        return self._clean_spacing(edited)

    def _remove_repeated_sentences(
        self,
        paragraph: str,
    ) -> str:
        sentences = self.DUPLICATE_SENTENCE_PATTERN.split(
            paragraph
        )

        if len(sentences) < 2:
            return paragraph

        kept: list[str] = []
        seen: set[str] = set()

        for sentence in sentences:
            sentence = sentence.strip()

            if not sentence:
                continue

            key = self._comparison_key(sentence)

            if not key or key in seen:
                continue

            seen.add(key)
            kept.append(sentence)

        return " ".join(kept)

    def _merge_short_paragraphs(
        self,
        paragraphs: list[str],
    ) -> list[str]:
        """
        Merge very short adjacent factual paragraphs.

        Quotes are kept as separate paragraphs.
        """

        if len(paragraphs) < 2:
            return paragraphs

        merged: list[str] = []
        index = 0

        while index < len(paragraphs):
            current = paragraphs[index]

            if (
                index + 1 < len(paragraphs)
                and self._can_merge(
                    current,
                    paragraphs[index + 1],
                )
            ):
                current = (
                    current.rstrip()
                    + " "
                    + paragraphs[index + 1].lstrip()
                )
                index += 1

            merged.append(current)
            index += 1

        return merged

    def _can_merge(
        self,
        first: str,
        second: str,
    ) -> bool:
        if self._contains_quote(first):
            return False

        if self._contains_quote(second):
            return False

        if len(first) > 180 or len(second) > 180:
            return False

        if len(first) + len(second) > 320:
            return False

        return True

    def _contains_quote(self, text: str) -> bool:
        return bool(
            self.QUOTE_PATTERN.search(
                str(text or "")
            )
        )

    @classmethod
    def _clean_spacing(cls, value: Any) -> str:
        text = str(value or "").strip()

        if not text:
            return ""

        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        text = cls.WHITESPACE_PATTERN.sub(" ", text)
        text = cls.MULTIPLE_BREAKS_PATTERN.sub(
            "\n\n",
            text,
        )

        return text.strip()

    @staticmethod
    def _ensure_terminal_punctuation(
        text: str,
    ) -> str:
        text = str(text or "").strip()

        if not text:
            return ""

        if text.endswith(
            (
                ".",
                "!",
                "?",
                ":",
                ";",
                "”",
                '"',
                "’",
            )
        ):
            return text

        return text + "."

    @staticmethod
    def _comparison_key(value: Any) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^\w\s]", "", text)

        return " ".join(text.split())

    @staticmethod
    def _match_case(
        original: str,
        replacement: str,
    ) -> str:
        if not original:
            return replacement

        if original.isupper():
            return replacement.upper()

        if original[0].isupper():
            return replacement[0].upper() + replacement[1:]

        return replacement