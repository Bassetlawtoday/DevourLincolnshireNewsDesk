"""Facebook publication formatter."""

from __future__ import annotations

import re
from typing import Any

from .builder import ArticleBuilder


try:
    from ..constants import FACEBOOK_MAX_EMOJIS
except ImportError:
    FACEBOOK_MAX_EMOJIS = 8


class FacebookFormatter:
    """Create polished, publication-ready Facebook copy."""

    DEFAULT_MAX_EMOJIS = 8
    MAX_POST_LENGTH = 6_500

    SENSITIVE_TERMS = (
        "death",
        "died",
        "fatal",
        "killed",
        "murder",
        "manslaughter",
        "rape",
        "sexual assault",
        "domestic abuse",
        "missing child",
        "serious injury",
        "life-threatening",
        "terrorism",
        "bereaved",
        "funeral",
    )

    COMMUNITY_TERMS = (
        "community",
        "event",
        "engagement",
        "patrol",
        "prevention",
        "advice",
        "volunteer",
        "school",
        "reassurance",
        "neighbourhood",
    )

    COURT_TERMS = (
        "charged",
        "court",
        "magistrates",
        "crown court",
        "jailed",
        "sentenced",
        "convicted",
        "remanded",
        "pleaded guilty",
    )

    ROAD_TERMS = (
        "collision",
        "road",
        "vehicle",
        "driver",
        "motorist",
        "car",
        "van",
        "motorcycle",
        "motorbike",
    )

    APPEAL_TERMS = (
        "appeal",
        "witness",
        "information",
        "recognise",
        "recognize",
        "come forward",
        "contact police",
    )

    ARREST_TERMS = (
        "arrested",
        "arrest",
        "detained",
        "custody",
    )

    DRUG_TERMS = (
        "cannabis",
        "cocaine",
        "heroin",
        "drug",
        "drugs",
        "county lines",
    )

    QUOTE_PATTERN = re.compile(
        r"""["“‘][^"”’]+["”’]""",
        re.DOTALL,
    )

    SENTENCE_END_PATTERN = re.compile(
        r"(?<=[.!?])\s+"
    )

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
    ) -> None:
        self.builder = builder or ArticleBuilder()

    def format(
        self,
        story: Any,
        emoji_limit: int = FACEBOOK_MAX_EMOJIS,
    ) -> str:
        article = self.builder.build(story)

        combined_text = " ".join(
            [
                article.title,
                article.summary,
                *article.paragraphs,
            ]
        )

        emoji_limit = self._normalise_emoji_limit(
            emoji_limit
        )

        sensitive = self._contains_any(
            combined_text,
            self.SENSITIVE_TERMS,
        )

        emoji_plan = self._build_emoji_plan(
            combined_text,
            sensitive=sensitive,
            limit=emoji_limit,
        )

        sections: list[str] = []

        headline = self._build_headline(
            article.title,
            emoji_plan,
        )

        if headline:
            sections.append(headline)

        introduction = self._build_introduction(
            article.summary,
            article.paragraphs,
        )

        if introduction:
            sections.append(introduction)

        body_paragraphs = self._select_body_paragraphs(
            article.paragraphs,
            introduction=introduction,
        )

        sections.extend(
            self._decorate_body_paragraphs(
                body_paragraphs,
                emoji_plan=emoji_plan,
                sensitive=sensitive,
            )
        )

        if not article.has_content:
            sections.append(
                "Further details were not available in the "
                "supplied source material."
            )

        footer = self._build_footer(
            article,
            emoji_plan=emoji_plan,
        )

        if footer:
            sections.append(footer)

        output = "\n\n".join(
            section.strip()
            for section in sections
            if section and section.strip()
        )

        return self._limit_post_length(output)

    @staticmethod
    def _contains_any(
        text: str,
        terms: tuple[str, ...],
    ) -> bool:
        lowered = str(text or "").casefold()

        return any(
            term.casefold() in lowered
            for term in terms
        )

    def _normalise_emoji_limit(
        self,
        value: Any,
    ) -> int:
        try:
            limit = int(value)
        except (TypeError, ValueError):
            limit = self.DEFAULT_MAX_EMOJIS

        return max(
            0,
            min(limit, self.DEFAULT_MAX_EMOJIS),
        )

    def _build_emoji_plan(
        self,
        text: str,
        *,
        sensitive: bool,
        limit: int,
    ) -> dict[str, str]:
        if limit <= 0:
            return {}

        if sensitive:
            candidates = [
                ("headline", "🚨"),
                ("location", "📍"),
                ("investigation", "🔎"),
                ("court", "⚖️"),
                ("appeal", "📢"),
                ("police", "🚔"),
                ("information", "ℹ️"),
                ("news", "📰"),
            ]

        elif self._contains_any(
            text,
            self.COMMUNITY_TERMS,
        ):
            candidates = [
                ("headline", "📣"),
                ("location", "📍"),
                ("community", "🤝"),
                ("police", "👮"),
                ("area", "🏘️"),
                ("information", "ℹ️"),
                ("news", "📰"),
                ("positive", "✅"),
            ]

        else:
            candidates = [
                ("headline", "🚔"),
                ("location", "📍"),
                ("investigation", "🔎"),
                ("court", "⚖️"),
                ("appeal", "📢"),
                ("information", "ℹ️"),
                ("news", "📰"),
                ("positive", "✅"),
            ]

        plan = dict(candidates[:limit])

        if self._contains_any(text, self.ROAD_TERMS):
            self._replace_emoji(
                plan,
                preferred_key="investigation",
                fallback_key="headline",
                emoji="🚗",
            )

        if self._contains_any(text, self.COURT_TERMS):
            self._replace_emoji(
                plan,
                preferred_key="court",
                fallback_key="information",
                emoji="⚖️",
            )

        if self._contains_any(text, self.APPEAL_TERMS):
            self._replace_emoji(
                plan,
                preferred_key="appeal",
                fallback_key="information",
                emoji="📢",
            )

        if self._contains_any(text, self.ARREST_TERMS):
            self._replace_emoji(
                plan,
                preferred_key="police",
                fallback_key="investigation",
                emoji="🚔",
            )

        if self._contains_any(text, self.DRUG_TERMS):
            self._replace_emoji(
                plan,
                preferred_key="investigation",
                fallback_key="information",
                emoji="🔎",
            )

        return plan

    @staticmethod
    def _replace_emoji(
        plan: dict[str, str],
        *,
        preferred_key: str,
        fallback_key: str,
        emoji: str,
    ) -> None:
        if preferred_key in plan:
            plan[preferred_key] = emoji
        elif fallback_key in plan:
            plan[fallback_key] = emoji

    @staticmethod
    def _build_headline(
        title: str,
        emoji_plan: dict[str, str],
    ) -> str:
        title = str(title or "").strip()

        if not title:
            title = "Police update"

        prefix = emoji_plan.get("headline", "")

        if prefix:
            return f"{prefix} {title}"

        return title

    def _build_introduction(
        self,
        summary: str,
        paragraphs: list[str],
    ) -> str:
        summary = str(summary or "").strip()

        if summary:
            return summary

        for paragraph in paragraphs:
            paragraph = str(paragraph or "").strip()

            if paragraph:
                return paragraph

        return ""

    def _select_body_paragraphs(
        self,
        paragraphs: list[str],
        *,
        introduction: str,
    ) -> list[str]:
        selected: list[str] = []
        introduction_key = self._comparison_key(
            introduction
        )

        for paragraph in paragraphs:
            paragraph = str(paragraph or "").strip()

            if not paragraph:
                continue

            if (
                introduction_key
                and self._comparison_key(paragraph)
                == introduction_key
            ):
                continue

            selected.append(paragraph)

        return selected

    def _decorate_body_paragraphs(
        self,
        paragraphs: list[str],
        *,
        emoji_plan: dict[str, str],
        sensitive: bool,
    ) -> list[str]:
        if not paragraphs:
            return []

        decorated: list[str] = []
        used_keys: set[str] = set()

        for paragraph in paragraphs:
            prefix = self._paragraph_prefix(
                paragraph,
                emoji_plan=emoji_plan,
                used_keys=used_keys,
                sensitive=sensitive,
            )

            if prefix:
                decorated.append(
                    f"{prefix} {paragraph}"
                )
            else:
                decorated.append(paragraph)

        return decorated

    def _paragraph_prefix(
        self,
        paragraph: str,
        *,
        emoji_plan: dict[str, str],
        used_keys: set[str],
        sensitive: bool,
    ) -> str:
        if not emoji_plan:
            return ""

        checks = (
            (
                "court",
                self.COURT_TERMS,
            ),
            (
                "appeal",
                self.APPEAL_TERMS,
            ),
            (
                "investigation",
                self.DRUG_TERMS + self.ARREST_TERMS,
            ),
            (
                "community",
                self.COMMUNITY_TERMS,
            ),
            (
                "police",
                self.ARREST_TERMS,
            ),
        )

        for key, terms in checks:
            if (
                key in emoji_plan
                and key not in used_keys
                and self._contains_any(paragraph, terms)
            ):
                used_keys.add(key)
                return emoji_plan[key]

        if sensitive:
            return ""

        return ""

    def _build_footer(
        self,
        article: Any,
        *,
        emoji_plan: dict[str, str],
    ) -> str:
        lines: list[str] = []

        if article.location:
            prefix = emoji_plan.get("location", "")

            location_line = article.location

            if prefix:
                location_line = (
                    f"{prefix} {location_line}"
                )

            lines.append(location_line)

        if article.source:
            source_prefix = emoji_plan.get(
                "information",
                "",
            )

            source_line = f"Source: {article.source}"

            if source_prefix:
                source_line = (
                    f"{source_prefix} {source_line}"
                )

            lines.append(source_line)

        return "\n".join(lines)

    def _limit_post_length(
        self,
        text: str,
    ) -> str:
        text = str(text or "").strip()

        if len(text) <= self.MAX_POST_LENGTH:
            return text

        shortened = text[: self.MAX_POST_LENGTH - 1]
        shortened = shortened.rsplit(
            "\n\n",
            maxsplit=1,
        )[0].rstrip()

        if not shortened:
            shortened = text[
                : self.MAX_POST_LENGTH - 1
            ].rstrip()

        return shortened + "…"

    @staticmethod
    def _comparison_key(
        value: Any,
    ) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^\w\s]", "", text)

        return " ".join(text.split())