"""
Factory methods for creating Story objects from external sources.
"""

from __future__ import annotations

from newsdesk.story import Story


class StoryFactory:
    """Creates Story objects from supported source formats."""

    @staticmethod
    def from_facebook(
        post: dict,
        *,
        source_name: str,
    ) -> Story:
        """
        Convert a Facebook Graph API post into a Story.
        """

        message = (
            str(post.get("message", "")).strip()
        )

        lines = [
            line.strip()
            for line in message.splitlines()
            if line.strip()
        ]

        if lines:
            title = lines[0][:120]
            summary = lines[0][:250]
        else:
            title = "Facebook update"
            summary = ""

        return Story(
            title=title,
            summary=summary,
            body=message,
            source=source_name,
            url=post.get("permalink_url", ""),
            published=post.get("created_time", ""),
            story_id=post.get("id", ""),
            extras={
                "facebook": post,
            },
        )