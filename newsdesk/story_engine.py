"""
newsdesk.story_engine

Central story-processing engine for Devour Lincolnshire NewsDesk.

The StoryEngine coordinates validation, statistics, metadata generation,
content formatting and creation of a PublishResult. Business logic remains
inside the dedicated service and formatter modules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from newsdesk.formatters import Formatters
from newsdesk.publish_result import PublishResult
from newsdesk.services.metadata import MetadataService, StoryMetadata
from newsdesk.services.statistics import StatisticsService, StoryStatistics
from newsdesk.services.validator import StoryValidator, ValidationResult
from newsdesk.story import Story


class StoryEngineError(RuntimeError):
    """
    Base exception for StoryEngine failures.
    """


class InvalidStoryError(StoryEngineError):
    """
    Raised when a story fails validation.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)

        message = "Story validation failed"

        if self.errors:
            message = f"{message}: {'; '.join(self.errors)}"

        super().__init__(message)


class FormatterError(StoryEngineError):
    """
    Raised when a formatter cannot generate its output.
    """

    def __init__(
        self,
        formatter_name: str,
        original_error: Exception,
    ) -> None:
        self.formatter_name = formatter_name
        self.original_error = original_error

        super().__init__(
            f"Formatter '{formatter_name}' failed: "
            f"{original_error}"
        )


class StoryEngine:
    """
    Coordinates the NewsDesk story-processing pipeline.

    Pipeline:

        Story
          -> validation
          -> statistics
          -> metadata
          -> formatters
          -> PublishResult

    Parameters
    ----------
    validator:
        Optional custom story validator.

    statistics_service:
        Optional custom statistics service.

    metadata_service:
        Optional custom metadata service.

    formatters:
        Formatter collection or factory. Defaults to the application's
        Formatters class.

    strict_validation:
        When True, invalid stories raise InvalidStoryError.

        When False, the engine returns a PublishResult containing validation
        errors in its extras dictionary.

    strict_formatting:
        When True, formatter failures raise FormatterError.

        When False, failed formatter outputs are left empty and details are
        stored in the result extras.
    """

    FORMATTER_OUTPUTS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("website", ("website",)),
        ("facebook", ("facebook",)),
        ("newsletter", ("newsletter",)),
        ("breaking_news", ("breaking", "breaking_news")),
        ("html", ("html",)),
        ("markdown", ("markdown",)),
        ("plain_text", ("text", "plain_text")),
    )

    def __init__(
        self,
        validator: StoryValidator | None = None,
        statistics_service: StatisticsService | None = None,
        metadata_service: MetadataService | None = None,
        formatters: Any = None,
        *,
        strict_validation: bool = True,
        strict_formatting: bool = True,
    ) -> None:
        self.validator = validator or StoryValidator()

        self.statistics_service = (
            statistics_service
            or StatisticsService()
        )

        self.metadata_service = (
            metadata_service
            or MetadataService()
        )

        self.formatters = (
            formatters
            if formatters is not None
            else Formatters()
        )

        self.strict_validation = strict_validation
        self.strict_formatting = strict_formatting

    def process(self, story: Story) -> PublishResult:
        """
        Process a Story and return all publication outputs.

        Raises
        ------
        TypeError
            If story is not a Story instance.

        InvalidStoryError
            If validation fails and strict validation is enabled.

        FormatterError
            If a formatter fails and strict formatting is enabled.
        """

        self._check_story_type(story)

        validation = self.validator.validate(story)

        if not validation.valid and self.strict_validation:
            raise InvalidStoryError(validation.errors)

        statistics = self.statistics_service.calculate(story)
        metadata = self.metadata_service.generate(story)

        self._apply_metadata_to_story(
            story=story,
            metadata=metadata,
        )

        result = PublishResult()

        self._populate_source_details(
            result=result,
            story=story,
        )

        self._populate_editorial_details(
            result=result,
            story=story,
        )

        self._populate_statistics(
            result=result,
            statistics=statistics,
        )

        self._populate_metadata(
            result=result,
            metadata=metadata,
        )

        self._store_validation(
            result=result,
            validation=validation,
        )

        formatter_errors = self._populate_formatted_outputs(
            result=result,
            story=story,
        )

        if formatter_errors:
            self._store_extra(
                result,
                "formatter_errors",
                formatter_errors,
            )

        self._store_extra(
            result,
            "validation_passed",
            validation.valid,
        )

        self._store_extra(
            result,
            "character_count",
            statistics.character_count,
        )

        self._store_extra(
            result,
            "paragraph_count",
            statistics.paragraph_count,
        )

        self._store_extra(
            result,
            "sentence_count",
            statistics.sentence_count,
        )

        return result

    def validate(self, story: Story) -> ValidationResult:
        """
        Validate a story without processing it.
        """

        self._check_story_type(story)

        return self.validator.validate(story)

    def calculate_statistics(
        self,
        story: Story,
    ) -> StoryStatistics:
        """
        Calculate statistics without performing the full pipeline.
        """

        self._check_story_type(story)

        return self.statistics_service.calculate(story)

    def generate_metadata(
        self,
        story: Story,
    ) -> StoryMetadata:
        """
        Generate metadata without performing the full pipeline.
        """

        self._check_story_type(story)

        return self.metadata_service.generate(story)

    @staticmethod
    def _check_story_type(story: Story) -> None:
        if not isinstance(story, Story):
            raise TypeError(
                "StoryEngine.process() requires a Story instance."
            )

    @staticmethod
    def _apply_metadata_to_story(
        story: Story,
        metadata: StoryMetadata,
    ) -> None:
        """
        Synchronise generated metadata back to the Story model.
        """

        story.slug = metadata.slug
        story.seo_title = metadata.seo_title
        story.meta_description = metadata.meta_description
        story.image_prompt = metadata.image_prompt
        story.tags = list(metadata.tags or [])

    @staticmethod
    def _populate_source_details(
        result: PublishResult,
        story: Story,
    ) -> None:
        StoryEngine._set_result_value(
            result,
            "source",
            story.source,
        )

        StoryEngine._set_result_value(
            result,
            "published",
            story.published,
        )

        StoryEngine._set_result_value(
            result,
            "url",
            story.url,
        )

    @staticmethod
    def _populate_editorial_details(
        result: PublishResult,
        story: Story,
    ) -> None:
        StoryEngine._set_result_value(
            result,
            "priority",
            story.priority,
        )

        StoryEngine._set_result_value(
            result,
            "classification",
            story.classification,
        )

        StoryEngine._set_result_value(
            result,
            "editorial_decision",
            story.editorial_decision,
        )

    @staticmethod
    def _populate_statistics(
        result: PublishResult,
        statistics: StoryStatistics,
    ) -> None:
        StoryEngine._set_result_value(
            result,
            "word_count",
            statistics.word_count,
        )

        StoryEngine._set_result_value(
            result,
            "reading_time",
            statistics.reading_time,
        )

    @staticmethod
    def _populate_metadata(
        result: PublishResult,
        metadata: StoryMetadata,
    ) -> None:
        StoryEngine._set_result_value(
            result,
            "seo_title",
            metadata.seo_title,
        )

        StoryEngine._set_result_value(
            result,
            "slug",
            metadata.slug,
        )

        StoryEngine._set_result_value(
            result,
            "meta_description",
            metadata.meta_description,
        )

        StoryEngine._set_result_value(
            result,
            "image_prompt",
            metadata.image_prompt,
        )

        StoryEngine._set_result_value(
            result,
            "tags",
            list(metadata.tags or []),
        )

    @staticmethod
    def _store_validation(
        result: PublishResult,
        validation: ValidationResult,
    ) -> None:
        StoryEngine._store_extra(
            result,
            "validation_errors",
            list(validation.errors),
        )

    def _populate_formatted_outputs(
        self,
        result: PublishResult,
        story: Story,
    ) -> dict[str, str]:
        formatter_errors: dict[str, str] = {}

        for output_name, formatter_names in self.FORMATTER_OUTPUTS:
            formatter = self._find_formatter(
                formatter_names
            )

            if formatter is None:
                message = (
                    "No compatible formatter was found. "
                    f"Tried: {', '.join(formatter_names)}"
                )

                if self.strict_formatting:
                    raise FormatterError(
                        output_name,
                        LookupError(message),
                    )

                formatter_errors[output_name] = message

                self._set_result_value(
                    result,
                    output_name,
                    "",
                )

                continue

            try:
                output = self._run_formatter(
                    formatter=formatter,
                    story=story,
                )

            except Exception as error:
                if self.strict_formatting:
                    raise FormatterError(
                        output_name,
                        error,
                    ) from error

                formatter_errors[output_name] = str(error)
                output = ""

            self._set_result_value(
                result,
                output_name,
                output,
            )

        return formatter_errors

    def _find_formatter(
        self,
        formatter_names: tuple[str, ...],
    ) -> Any | None:
        """
        Find the first available formatter using compatible names.
        """

        for formatter_name in formatter_names:
            if hasattr(self.formatters, formatter_name):
                return getattr(
                    self.formatters,
                    formatter_name,
                )

        return None

    @staticmethod
    def _run_formatter(
        formatter: Any,
        story: Story,
    ) -> str:
        """
        Execute a formatter using a supported formatter interface.

        Supported interfaces:

        - formatter.format(story)
        - formatter.render(story)
        - formatter.generate(story)
        - formatter.create(story)
        - formatter(story)
        """

        if isinstance(formatter, type):
            formatter = formatter()

        formatter_callable: Callable[..., Any] | None = None

        for method_name in (
            "format",
            "render",
            "generate",
            "create",
        ):
            candidate = getattr(
                formatter,
                method_name,
                None,
            )

            if callable(candidate):
                formatter_callable = candidate
                break

        if formatter_callable is None and callable(formatter):
            formatter_callable = formatter

        if formatter_callable is None:
            raise TypeError(
                "Formatter must be callable or provide format(), "
                "render(), generate() or create()."
            )

        output = formatter_callable(story)

        if output is None:
            return ""

        if isinstance(output, str):
            return output

        return str(output)

    @staticmethod
    def _set_result_value(
        result: PublishResult,
        field_name: str,
        value: Any,
    ) -> None:
        """
        Set a PublishResult field when the model supports it.
        """

        if hasattr(result, field_name):
            setattr(
                result,
                field_name,
                value,
            )
            return

        StoryEngine._store_extra(
            result,
            field_name,
            value,
        )

    @staticmethod
    def _store_extra(
        result: PublishResult,
        key: str,
        value: Any,
    ) -> None:
        """
        Store supplementary information using PublishResult.add_extra()
        when available, otherwise use its extras dictionary.
        """

        add_extra = getattr(
            result,
            "add_extra",
            None,
        )

        if callable(add_extra):
            add_extra(
                key,
                value,
            )
            return

        extras = getattr(
            result,
            "extras",
            None,
        )

        if extras is None:
            extras = {}
            setattr(
                result,
                "extras",
                extras,
            )

        extras[key] = value