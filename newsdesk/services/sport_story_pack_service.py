from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping


OutputBuilder = Callable[[Any], str]
CreditResolver = Callable[[Any], str]


class SportStoryPackService:
    """Build and export publication-ready Sport story packs."""

    CHANNELS = ("website", "facebook", "newsletter")
    DEFAULT_IMAGE_CREDIT = "Devour Lincolnshire Sport"

    def publication_outputs(
        self,
        *,
        story: Any,
        publish_result: Any = None,
        website_builder: OutputBuilder,
        facebook_builder: OutputBuilder,
        newsletter_builder: OutputBuilder,
        credit_resolver: CreditResolver | None = None,
    ) -> dict[str, str]:
        """Return credited website, Facebook and newsletter copy."""

        outputs = {
            "website": "",
            "facebook": "",
            "newsletter": "",
        }

        if publish_result is not None:
            for channel in self.CHANNELS:
                value = str(
                    getattr(publish_result, channel, "") or ""
                ).strip()

                if value:
                    outputs[channel] = self.with_image_credit(
                        value,
                        story=story,
                        channel=channel,
                        credit_resolver=credit_resolver,
                    )

        builders = {
            "website": website_builder,
            "facebook": facebook_builder,
            "newsletter": newsletter_builder,
        }

        for channel, builder in builders.items():
            if outputs[channel]:
                continue

            outputs[channel] = self.with_image_credit(
                builder(story),
                story=story,
                channel=channel,
                credit_resolver=credit_resolver,
            )

        return outputs

    def with_image_credit(
        self,
        output: Any,
        *,
        story: Any,
        channel: str,
        credit_resolver: CreditResolver | None = None,
    ) -> str:
        """Append a publication-ready image credit once."""

        text = str(output or "").strip()

        if not text or story is None:
            return text

        credit = self.image_credit(
            story,
            credit_resolver=credit_resolver,
        )

        credit_line = (
            f"📷 Image: {credit}"
            if channel in {"facebook", "newsletter"}
            else f"Image credit: {credit}"
        )

        if credit.casefold() in text.casefold():
            return text

        return f"{text}\n\n{credit_line}".strip()

    def export(
        self,
        destination: str | Path,
        *,
        story: Any,
        outputs: Mapping[str, Any],
        image_path: str | Path | None = None,
        image_credit: str | None = None,
        image_quality: Mapping[str, Any] | None = None,
        credit_resolver: CreditResolver | None = None,
    ) -> Path:
        """Create a ZIP containing image, copy, credits and metadata."""

        if story is None:
            raise ValueError("A story is required to export a Story Pack.")

        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        resolved_image_path = self._existing_image_path(image_path)
        credit = (
            str(image_credit or "").strip()
            or self.image_credit(
                story,
                credit_resolver=credit_resolver,
            )
        )
        quality = self._normalise_image_quality(image_quality)

        metadata = self._metadata(
            story=story,
            credit=credit,
            quality=quality,
        )
        image_details = self._image_details(
            story=story,
            credit=credit,
            quality=quality,
        )

        with zipfile.ZipFile(
            destination_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.writestr(
                "website-article.txt",
                str(outputs.get("website", "") or ""),
            )
            archive.writestr(
                "facebook-post.txt",
                str(outputs.get("facebook", "") or ""),
            )
            archive.writestr(
                "newsletter-copy.txt",
                str(outputs.get("newsletter", "") or ""),
            )
            archive.writestr(
                "image-details.txt",
                "\n".join(image_details),
            )
            archive.writestr(
                "source-link.txt",
                str(getattr(story, "url", "") or ""),
            )
            archive.writestr(
                "metadata.json",
                json.dumps(
                    metadata,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
            )

            if resolved_image_path is not None:
                suffix = resolved_image_path.suffix.lower() or ".jpg"
                archive.write(
                    resolved_image_path,
                    arcname=f"image{suffix}",
                )

        return destination_path

    def image_credit(
        self,
        story: Any,
        *,
        credit_resolver: CreditResolver | None = None,
    ) -> str:
        """Resolve the most specific available image credit."""

        if story is None:
            return self.DEFAULT_IMAGE_CREDIT

        if credit_resolver is not None:
            resolved = str(credit_resolver(story) or "").strip()
            if resolved:
                return resolved

        credit = str(
            getattr(story, "image_credit", "") or ""
        ).strip()

        if credit:
            return credit

        source = str(
            getattr(story, "source", "") or ""
        ).strip()

        return source or self.DEFAULT_IMAGE_CREDIT

    @staticmethod
    def _existing_image_path(
        image_path: str | Path | None,
    ) -> Path | None:
        if not image_path:
            return None

        path = Path(image_path)
        return path if path.is_file() else None

    @staticmethod
    def _normalise_image_quality(
        image_quality: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        defaults = {
            "score": 0,
            "rating": "Unavailable",
            "width": 0,
            "height": 0,
            "megapixels": 0,
            "aspect_ratio": 0,
            "file_size_bytes": 0,
            "sha256": "",
            "duplicate_story_count": 0,
            "cache_reused": False,
            "reasons": [],
        }

        if image_quality:
            defaults.update(dict(image_quality))

        return defaults

    @staticmethod
    def _metadata(
        *,
        story: Any,
        credit: str,
        quality: Mapping[str, Any],
    ) -> dict[str, Any]:
        extras = getattr(story, "extras", {}) or {}

        return {
            "title": str(getattr(story, "title", "") or ""),
            "source": str(getattr(story, "source", "") or ""),
            "source_url": str(getattr(story, "url", "") or ""),
            "published": str(getattr(story, "published", "") or ""),
            "classification": str(
                getattr(story, "classification", "") or ""
            ),
            "editorial_decision": str(
                getattr(story, "editorial_decision", "") or ""
            ),
            "tags": list(getattr(story, "tags", []) or []),
            "image": {
                "source_url": str(
                    getattr(story, "image_url", "") or ""
                ),
                "caption": str(
                    getattr(story, "image_caption", "") or ""
                ),
                "credit": credit,
                "alt_text": str(
                    getattr(story, "image_alt_text", "") or ""
                ),
                "is_fallback": bool(
                    getattr(story, "image_is_fallback", False)
                ),
                "quality": dict(quality),
            },
            "editorial": {
                "priority_score": extras.get("priority_score"),
                "priority_rating": extras.get("priority_rating"),
                "priority_level": extras.get("priority_level"),
                "editorial_zone": extras.get(
                    "editorial_zone_label"
                ),
                "matched_place": extras.get("matched_place"),
                "priority_reasons": extras.get(
                    "priority_reasons",
                    [],
                ),
            },
        }

    @staticmethod
    def _image_details(
        *,
        story: Any,
        credit: str,
        quality: Mapping[str, Any],
    ) -> list[str]:
        return [
            f"Image credit: {credit}",
            (
                "Caption: "
                f"{getattr(story, 'image_caption', '') or '(none)'}"
            ),
            (
                "Alt text: "
                f"{getattr(story, 'image_alt_text', '') or '(none)'}"
            ),
            (
                "Original image URL: "
                f"{getattr(story, 'image_url', '') or '(none)'}"
            ),
            (
                f"Quality: {quality.get('rating', 'Unavailable')} "
                f"({quality.get('score', 0)}/100)"
            ),
            (
                f"Dimensions: {quality.get('width', 0)}×"
                f"{quality.get('height', 0)} pixels"
            ),
            (
                "Cache reused: "
                f"{'Yes' if quality.get('cache_reused', False) else 'No'}"
            ),
        ]