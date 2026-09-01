"""
content_selector.py

Selects the most likely HTML container containing the main article.

This class deliberately performs NO text extraction or cleaning.
It simply returns the best BeautifulSoup Tag for ArticleScraper
to process.

Author: NewsDesk Refactor
"""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Tag


LOGGER = logging.getLogger(__name__)


class ContentSelector:

    POSITIVE_KEYWORDS = (
        "article",
        "articlebody",
        "article-body",
        "story",
        "content",
        "entry",
        "post",
        "main",
        "body",
    )

    NEGATIVE_KEYWORDS = (
        "share",
        "sharing",
        "social",
        "comment",
        "related",
        "recommend",
        "sidebar",
        "widget",
        "advert",
        "promo",
        "newsletter",
        "subscription",
        "subscribe",
        "modal",
        "popup",
        "overlay",
        "footer",
        "nav",
        "navigation",
        "cookie",
    )

    BOILERPLATE_PHRASES = (
        "discover more from",
        "continue reading",
        "sign up to continue",
        "subscribe to continue",
        "unlock this article",
        "you may also like",
        "recommended for you",
    )

    # These are checked before generic scoring.
    # They cover common structured article layouts, including BBC pages.
    PREFERRED_SELECTORS = (
        "[itemprop='articleBody']",
        "[data-component='article-body']",
        "[data-testid='article-body']",
        ".article-body",
        ".story-body",
        ".entry-content",
        ".post-content",
        ".wpr-post-content",
        ".elementor-widget-wpr-post-content",
        "article",
    )

    CANDIDATE_SELECTORS = (
        "article",
        "[itemprop='articleBody']",
        "[data-component='article-body']",
        "[data-testid='article-body']",
        "main",
        ".article",
        ".article-body",
        ".story-body",
        ".story",
        ".entry-content",
        ".post-content",
        ".content",
        ".main-content",
        "div",
        "section",
    )

    def select(self, soup: BeautifulSoup) -> Tag:

        preferred = self._select_preferred_container(soup)

        if preferred is not None:
            return preferred

        bbc_container = self._select_bbc_container(soup)

        if bbc_container is not None:
            return bbc_container

        candidates: list[tuple[int, Tag]] = []
        seen: set[int] = set()

        for selector in self.CANDIDATE_SELECTORS:

            for node in soup.select(selector):

                if not isinstance(node, Tag):
                    continue

                node_id = id(node)

                if node_id in seen:
                    continue

                seen.add(node_id)

                if not self._is_viable_candidate(node):
                    continue

                score = self._score(node)

                if score > 0:
                    candidates.append((score, node))

        if not candidates:

            article = soup.find("article")

            if isinstance(article, Tag):
                return article

            main = soup.find("main")

            if isinstance(main, Tag):
                return main

            body = soup.body

            if isinstance(body, Tag):
                return body

            return soup

        candidates.sort(
            key=lambda candidate: candidate[0],
            reverse=True,
        )

        return candidates[0][1]

    def _select_preferred_container(
        self,
        soup: BeautifulSoup,
    ) -> Tag | None:

        LOGGER.debug("Selecting preferred article container")

        candidates: list[Tag] = []
        seen: set[int] = set()

        for selector in self.PREFERRED_SELECTORS:
            for node in soup.select(selector):
                if not isinstance(node, Tag):
                    continue

                node_id = id(node)
                if node_id in seen:
                    continue

                seen.add(node_id)

                if self._is_suitable_article_container(node):
                    candidates.append(node)

        LOGGER.debug("Preferred article candidate count=%d", len(candidates))

        if not candidates:
            LOGGER.debug("No preferred article candidates")
            return None


        for node in candidates:
            LOGGER.debug(
                "Article candidate score=%s tag=%s classes=%s",
                self._score(node), node.name, node.get("class"),
            )

        winner = max(
            candidates,
            key=lambda node: (
                self._score(node),
                self._content_length(node),
            ),
        )

        LOGGER.debug(
            "Selected article candidate score=%s tag=%s classes=%s",
            self._score(winner), winner.name, winner.get("class"),
        )

        return winner    


    def _select_bbc_container(
        self,
        soup: BeautifulSoup,
    ) -> Tag | None:
        """
        Locate the shared parent containing BBC article text blocks.

        BBC pages commonly store individual article paragraphs inside elements
        carrying data-component="text-block". Selecting div#root captures the
        whole application, so this method finds the smallest useful ancestor
        containing the article's text blocks instead.
        """

        text_blocks = [
            node
            for node in soup.select(
                "[data-component='text-block']"
            )
            if isinstance(node, Tag)
            and len(node.get_text(" ", strip=True).split()) >= 4
        ]

        if len(text_blocks) < 2:
            return None

        first_block = text_blocks[0]
        ancestor = first_block.parent

        while isinstance(ancestor, Tag):

            matching_blocks = ancestor.select(
                "[data-component='text-block']"
            )

            if len(matching_blocks) >= len(text_blocks):

                parent = ancestor.parent

                if not isinstance(parent, Tag):
                    return ancestor

                parent_blocks = parent.select(
                    "[data-component='text-block']"
                )

                if len(parent_blocks) > len(matching_blocks):
                    return ancestor

            ancestor = ancestor.parent

        return None

    def _is_suitable_article_container(
        self,
        node: Tag,
    ) -> bool:

        attrs = self._attribute_text(node)

        if self._contains_negative_keyword(attrs):
            return False

        if self._looks_like_boilerplate(node):
            return False

        words = len(node.get_text(" ", strip=True).split())
        article_words = self._article_text_words(node)

        # Modern Elementor / BBC / WordPress article widgets
        if (
            node.name == "article"
            or node.get("itemprop") == "articleBody"
            or node.get("data-component") == "article-body"
            or node.get("data-testid") == "article-body"
            or any(
                keyword in attrs
                for keyword in (
                    "article-body",
                    "articlebody",
                    "entry-content",
                    "post-content",
                    "story-body",
                    "wpr-post-content",
                )
            )
        ):
            return words >= 20

        return (
            words >= 40
            and article_words >= 30
        )

    def _is_viable_candidate(self, node: Tag) -> bool:

        attrs = self._attribute_text(node)
        words = len(node.get_text(" ", strip=True).split())
        paragraphs = len(node.find_all("p"))

        if self._looks_like_boilerplate(node):
            LOGGER.debug(
                "Rejected boilerplate tag=%s words=%d paragraphs=%d classes=%s",
                node.name, words, paragraphs, node.get("class"),
            )
            return False

        strongly_semantic = (
            node.name == "article"
            or node.get("itemprop") == "articleBody"
            or node.get("data-component") == "article-body"
            or node.get("data-testid") == "article-body"
            or any(
                keyword in attrs
                for keyword in (
                    "article-body",
                    "articlebody",
                    "entry-content",
                    "post-content",
                    "story-body",
                )
            )
        )
   
        if strongly_semantic:
            ok = words >= 20
            LOGGER.debug(
                "%s semantic candidate tag=%s words=%d paragraphs=%d classes=%s",
                "Accepted" if ok else "Rejected", node.name, words,
                paragraphs, node.get("class"),
            )
            return ok

        ok = paragraphs >= 2 and words >= 40

        LOGGER.debug(
            "%s generic candidate tag=%s words=%d paragraphs=%d classes=%s",
            "Accepted" if ok else "Rejected", node.name, words,
            paragraphs, node.get("class"),
        )

        return ok

    def _looks_like_boilerplate(self, node: Tag) -> bool:
        text = " ".join(
            node.get_text(" ", strip=True).casefold().split()
        )

        if not text:
            return True

        phrase_hits = sum(
            phrase in text
            for phrase in self.BOILERPLATE_PHRASES
        )

        words = text.split()

        if phrase_hits >= 2 and len(words) < 120:
            return True

        if (
            "discover more from" in text
            and "continue reading" in text
            and len(words) < 180
        ):
            return True

        return False

    @staticmethod
    def _article_text_words(node: Tag) -> int:
        total = 0

        for element in node.find_all(
            ["p", "blockquote", "li"],
        ):
            if not isinstance(element, Tag):
                continue

            if element.find_parent(
                ["nav", "aside", "footer", "form"],
            ) is not None:
                continue

            total += len(
                element.get_text(" ", strip=True).split()
            )

        return total

    @staticmethod
    def _content_length(node: Tag) -> int:
        return len(node.get_text(" ", strip=True).split())

    def _score(self, node: Tag) -> int:

        score = 0

        score += self._semantic_score(node)
        score += self._paragraph_score(node)
        score += self._heading_score(node)
        score += self._text_score(node)
        score -= self._penalty_score(node)
        score -= self._wrapper_penalty(node)
        score -= self._boilerplate_penalty(node)

        return score

    def _semantic_score(self, node: Tag) -> int:

        score = 0
        attrs = self._attribute_text(node)

        if node.name == "article":
            score += 300

        if node.get("itemprop") == "articleBody":
            score += 250

        if node.get("data-component") == "article-body":
            score += 300

        if node.get("data-testid") == "article-body":
            score += 300

        for word in self.POSITIVE_KEYWORDS:

            if word in attrs:
                score += 40

        return score

    def _paragraph_score(self, node: Tag) -> int:

        paragraphs = len(node.find_all("p"))

        if paragraphs < 2:
            return -150

        # Prevent enormous application wrappers winning simply because they
        # contain every paragraph on the page.
        return min(paragraphs, 30) * 25

    def _heading_score(self, node: Tag) -> int:

        h2 = len(node.find_all("h2"))
        h3 = len(node.find_all("h3"))

        return min(h2, 10) * 20 + min(h3, 10) * 10

    def _text_score(self, node: Tag) -> int:

        words = len(node.get_text(" ", strip=True).split())

        # Cap this score so div#root and other application wrappers do not
        # automatically beat the actual article container.
        return min(words // 20, 150)

    def _penalty_score(self, node: Tag) -> int:

        attrs = self._attribute_text(node)
        penalty = 0

        for word in self.NEGATIVE_KEYWORDS:

            if word in attrs:
                penalty += 300

        return penalty

    def _boilerplate_penalty(self, node: Tag) -> int:
        return 5000 if self._looks_like_boilerplate(node) else 0

    @staticmethod
    def _wrapper_penalty(node: Tag) -> int:
        """
        Penalise broad document/application wrappers.

        BBC's div#root previously won generic scoring because it contained the
        entire rendered page.
        """

        node_id = str(node.get("id", "") or "").casefold()

        if node_id in {"root", "app", "__next"}:
            return 5000

        if node.name == "main":
            return 500

        if node.name in {"body", "html"}:
            return 5000

        return 0

    @staticmethod
    def _attribute_text(node: Tag) -> str:

        classes = node.get("class", [])

        if isinstance(classes, str):
            class_text = classes
        else:
            class_text = " ".join(
                str(value)
                for value in classes
            )

        values = (
            node.get("id", ""),
            class_text,
            node.get("role", ""),
            node.get("itemprop", ""),
            node.get("data-component", ""),
            node.get("data-testid", ""),
        )

        return " ".join(
            str(value or "")
            for value in values
        ).casefold()

    def _contains_negative_keyword(
        self,
        attrs: str,
    ) -> bool:

        return any(
            keyword in attrs
            for keyword in self.NEGATIVE_KEYWORDS
        )
