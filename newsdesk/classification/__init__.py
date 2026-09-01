"""Story classification services."""

from .classifier import StoryClassifier
from .result import ClassificationResult

__all__ = [
    "ClassificationResult",
    "StoryClassifier",
]