"""
Weighted editorial story classifier for Devour Lincolnshire NewsDesk.

The classifier uses the data held in rules.py to determine:

- primary category
- secondary categories
- confidence
- matched keywords
- category scores
- editorial priority
- breaking-news status
- broad location type
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .result import ClassificationResult
from .rules import (
    BREAKING_KEYWORDS,
    CATEGORY_RULES,
    DEFAULT_CATEGORY,
    DEFAULT_PRIORITY,
    MINIMUM_SCORE,
)


class StoryClassifier:
    """Classify stories using weighted editorial keyword rules."""

    BASSETLAW_LOCATIONS = {
        "bassetlaw",
        "worksop",
        "retford",
        "harworth",
        "bircotes",
        "tuxford",
        "misterton",
        "west stockwith",
        "east retford",
        "clumber park",
        "carlton-in-lindrick",
        "carlton in lindrick",
        "langold",
        "costhorpe",
        "hodsock",
        "blyth",
        "ranskill",
        "mattersey",
        "everton",
        "gringley-on-the-hill",
        "gringley on the hill",
        "walkeringham",
        "beckingham",
        "saundby",
        "clarborough",
        "hayton",
        "babworth",
        "leverton",
        "north leverton",
        "south leverton",
        "st gamel",
        "gamston",
        "elkesley",
        "markham moor",
        "darlton",
        "dunham-on-trent",
        "dunham on trent",
        "laneham",
        "stokeham",
        "west drayton",
        "east drayton",
        "askham",
        "bothamsall",
        "welham",
        "ordsaIl",
        "ord­sall",
        "oldsall",
        "shireoaks",
        "rhodesia",
        "whitwell",
        "woodsetts",
        "gateford",
        "manton",
        "kilton",
        "the canch",
    }

    NOTTINGHAMSHIRE_LOCATIONS = {
        "nottinghamshire",
        "nottingham",
        "mansfield",
        "ashfield",
        "sutton-in-ashfield",
        "sutton in ashfield",
        "kirkby-in-ashfield",
        "kirkby in ashfield",
        "newark",
        "sherwood",
        "gedling",
        "arnold",
        "hucknall",
        "beeston",
        "broxtowe",
        "rushcliffe",
        "west bridgford",
        "ollerton",
        "edwinstowe",
        "rainworth",
        "southwell",
    }

    SECONDARY_SCORE_RATIO = 0.50
    MAX_SECONDARY_CATEGORIES = 3

    def __init__(
        self,
        category_rules: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        minimum_score: int = MINIMUM_SCORE,
        secondary_score_ratio: float = SECONDARY_SCORE_RATIO,
        max_secondary_categories: int = MAX_SECONDARY_CATEGORIES,
    ) -> None:
        self.category_rules = dict(
            category_rules or CATEGORY_RULES
        )

        self.minimum_score = max(
            1,
            int(minimum_score),
        )

        self.secondary_score_ratio = min(
            1.0,
            max(0.0, float(secondary_score_ratio)),
        )

        self.max_secondary_categories = max(
            0,
            int(max_secondary_categories),
        )

    def classify(self, story: Any) -> ClassificationResult:
        """Classify a Story or other story-like object."""

        title = self._story_value(
            story,
            "title",
            "headline",
            "name",
        )

        summary = self._story_value(
            story,
            "summary",
            "standfirst",
            "description",
            "excerpt",
        )

        body = self._story_body(story)

        location = self._story_value(
            story,
            "location",
            "area",
            "place",
        )

        return self.classify_text(
            title=title,
            summary=summary,
            body=body,
            location=location,
        )

    def classify_text(
        self,
        *,
        title: str = "",
        summary: str = "",
        body: str = "",
        location: str = "",
    ) -> ClassificationResult:
        """
        Classify supplied text without requiring a Story instance.

        Title matches receive more weight than summary or body matches.
        """

        clean_title = self._normalise_text(title)
        clean_summary = self._normalise_text(summary)
        clean_body = self._normalise_text(body)
        clean_location = self._normalise_text(location)

        scores, matched_keywords = self.score_categories(
            title=clean_title,
            summary=clean_summary,
            body=clean_body,
        )

        primary = self.determine_primary(scores)

        secondary = self.determine_secondary(
            scores,
            primary=primary,
        )

        confidence = self.calculate_confidence(
            scores,
            primary=primary,
        )

        priority = self.determine_priority(
            primary=primary,
            scores=scores,
        )

        combined_text = " ".join(
            part
            for part in (
                clean_title,
                clean_summary,
                clean_body,
            )
            if part
        )

        breaking = self.detect_breaking(
            combined_text,
        )

        location_type = self.detect_location(
            location=clean_location,
            text=combined_text,
        )

        return ClassificationResult(
            primary=primary,
            confidence=confidence,
            secondary=secondary,
            matched_keywords=matched_keywords,
            scores=scores,
            priority=priority,
            breaking=breaking,
            location_type=location_type,
        )

    def score_categories(
        self,
        *,
        title: str,
        summary: str,
        body: str,
    ) -> tuple[dict[str, int], dict[str, int]]:
        """
        Score every configured category.

        Weight multipliers:

        - title: 3
        - summary: 2
        - body: 1

        A keyword contributes once per text section. This prevents a story
        containing the same word repeatedly from producing an excessive score.
        """

        scores: dict[str, int] = {}
        matched_keywords: dict[str, int] = {}

        sections = (
            (title, 3),
            (summary, 2),
            (body, 1),
        )

        for category, rule in self.category_rules.items():
            category_score = 0

            keywords = rule.get(
                "keywords",
                {},
            )

            if not isinstance(keywords, Mapping):
                scores[category] = 0
                continue

            for raw_keyword, raw_weight in keywords.items():
                keyword = self._normalise_text(
                    raw_keyword
                )

                if not keyword:
                    continue

                try:
                    weight = int(raw_weight)
                except (TypeError, ValueError):
                    continue

                keyword_score = 0

                for section_text, multiplier in sections:
                    if not section_text:
                        continue

                    if self._contains_keyword(
                        section_text,
                        keyword,
                    ):
                        keyword_score += (
                            weight * multiplier
                        )

                if keyword_score <= 0:
                    continue

                category_score += keyword_score

                current_weight = matched_keywords.get(
                    keyword,
                    0,
                )

                matched_keywords[keyword] = max(
                    current_weight,
                    keyword_score,
                )

            scores[category] = category_score

        return scores, matched_keywords

    def determine_primary(
        self,
        scores: Mapping[str, int],
    ) -> str:
        """Return the highest-scoring category."""

        eligible = [
            (category, score)
            for category, score in scores.items()
            if score >= self.minimum_score
        ]

        if not eligible:
            return DEFAULT_CATEGORY

        eligible.sort(
            key=lambda item: (
                item[1],
                self._category_priority(item[0]),
                item[0],
            ),
            reverse=True,
        )

        return eligible[0][0]

    def determine_secondary(
        self,
        scores: Mapping[str, int],
        *,
        primary: str,
    ) -> list[str]:
        """Return meaningful categories below the primary category."""

        if primary == DEFAULT_CATEGORY:
            return []

        primary_score = scores.get(
            primary,
            0,
        )

        if primary_score <= 0:
            return []

        required_score = max(
            self.minimum_score,
            round(
                primary_score
                * self.secondary_score_ratio
            ),
        )

        candidates = [
            (category, score)
            for category, score in scores.items()
            if (
                category != primary
                and score >= required_score
            )
        ]

        candidates.sort(
            key=lambda item: (
                item[1],
                self._category_priority(item[0]),
                item[0],
            ),
            reverse=True,
        )

        return [
            category
            for category, _score in candidates[
                : self.max_secondary_categories
            ]
        ]

    def calculate_confidence(
        self,
        scores: Mapping[str, int],
        *,
        primary: str,
    ) -> float:
        """
        Calculate a transparent confidence score between 0 and 1.

        Confidence increases when:

        - the primary category has a strong score
        - it clearly exceeds the second category

        Confidence decreases when two categories score similarly.
        """

        if primary == DEFAULT_CATEGORY:
            return 0.0

        ordered_scores = sorted(
            (
                score
                for score in scores.values()
                if score > 0
            ),
            reverse=True,
        )

        if not ordered_scores:
            return 0.0

        top_score = ordered_scores[0]

        second_score = (
            ordered_scores[1]
            if len(ordered_scores) > 1
            else 0
        )

        strength = min(
            1.0,
            top_score / 40.0,
        )

        separation = (
            (top_score - second_score) / top_score
            if top_score
            else 0.0
        )

        confidence = (
            strength * 0.65
            + separation * 0.35
        )

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        return round(
            confidence,
            2,
        )

    def determine_priority(
        self,
        *,
        primary: str,
        scores: Mapping[str, int],
    ) -> int:
        """Return the configured priority for the primary category."""

        if primary == DEFAULT_CATEGORY:
            return DEFAULT_PRIORITY

        priority = self._category_priority(
            primary
        )

        primary_score = scores.get(
            primary,
            0,
        )

        if primary_score >= 40:
            priority += 5

        if primary_score >= 70:
            priority += 5

        return min(
            100,
            max(0, priority),
        )

    def detect_breaking(
        self,
        text: str,
    ) -> bool:
        """Return True when the story contains a breaking-news trigger."""

        for keyword in BREAKING_KEYWORDS:
            clean_keyword = self._normalise_text(
                keyword
            )

            if self._contains_keyword(
                text,
                clean_keyword,
            ):
                return True

        return False

    def detect_location(
        self,
        *,
        location: str,
        text: str,
    ) -> str:
        """
        Return a broad editorial location classification.

        Possible values:

        - bassetlaw
        - nottinghamshire
        - outside_nottinghamshire
        - unknown
        """

        combined = " ".join(
            part
            for part in (
                location,
                text,
            )
            if part
        )

        if self._contains_any_location(
            combined,
            self.BASSETLAW_LOCATIONS,
        ):
            return "bassetlaw"

        if self._contains_any_location(
            combined,
            self.NOTTINGHAMSHIRE_LOCATIONS,
        ):
            return "nottinghamshire"

        if location:
            return "outside_nottinghamshire"

        return "unknown"

    def _category_priority(
        self,
        category: str,
    ) -> int:
        rule = self.category_rules.get(
            category,
            {},
        )

        try:
            return int(
                rule.get(
                    "priority",
                    DEFAULT_PRIORITY,
                )
            )
        except (TypeError, ValueError):
            return DEFAULT_PRIORITY

    def _contains_any_location(
        self,
        text: str,
        locations: set[str],
    ) -> bool:
        for location in locations:
            if self._contains_keyword(
                text,
                self._normalise_text(location),
            ):
                return True

        return False

    @staticmethod
    def _contains_keyword(
        text: str,
        keyword: str,
    ) -> bool:
        """
        Match whole words or phrases.

        This prevents short keywords such as ``car`` matching unrelated
        words such as ``career`` or ``carers``.
        """

        if not text or not keyword:
            return False

        pattern = (
            r"(?<!\w)"
            + re.escape(keyword)
            + r"(?!\w)"
        )

        return bool(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
        )

    def _story_body(
        self,
        story: Any,
    ) -> str:
        """Extract body text from common Story structures."""

        for attribute_name in (
            "paragraphs",
            "article_paragraphs",
            "body_paragraphs",
        ):
            value = getattr(
                story,
                attribute_name,
                None,
            )

            if callable(value):
                try:
                    value = value()
                except TypeError:
                    value = None

            if isinstance(value, (list, tuple)):
                return "\n\n".join(
                    str(item)
                    for item in value
                    if str(item or "").strip()
                )

        return self._story_value(
            story,
            "body",
            "article",
            "content",
            "text",
        )

    @staticmethod
    def _story_value(
        story: Any,
        *attribute_names: str,
    ) -> str:
        """Return the first populated attribute from a story-like object."""

        if story is None:
            return ""

        if isinstance(story, Mapping):
            for attribute_name in attribute_names:
                value = story.get(
                    attribute_name,
                    "",
                )

                if value:
                    return str(value)

            return ""

        for attribute_name in attribute_names:
            value = getattr(
                story,
                attribute_name,
                "",
            )

            if callable(value):
                try:
                    value = value()
                except TypeError:
                    continue

            if value:
                return str(value)

        return ""

    @staticmethod
    def _normalise_text(
        value: Any,
    ) -> str:
        """Normalise text while retaining meaningful punctuation."""

        text = str(value or "").casefold()

        text = text.replace(
            "’",
            "'",
        )
        text = text.replace(
            "–",
            "-",
        )
        text = text.replace(
            "—",
            "-",
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()