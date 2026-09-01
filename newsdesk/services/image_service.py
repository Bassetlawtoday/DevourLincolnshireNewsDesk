"""
Shared image downloading and caching for Devour Lincolnshire NewsDesk.

This module is intentionally independent of any individual intelligence
module. Fire Intelligence will be its first user; Police, Planning and future
modules can use the same service later.

The service:

- downloads remote lead images
- caches them under ``cache/images``
- avoids downloading the same URL twice
- validates downloaded files with Pillow
- records useful image metadata
- creates a local branded fallback placeholder
- treats image failure as non-fatal
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import mimetypes
from pathlib import Path
import shutil
import ssl
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


LOGGER = logging.getLogger(__name__)


DEFAULT_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0 Safari/537.36 "
    "BassetlawToday-NewsDesk/1.0"
)

ALLOWED_EXTENSIONS: Final[set[str]] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
}


@dataclass(frozen=True, slots=True)
class ImageAsset:
    """
    Result returned by :class:`ImageService`.

    ``available`` is true when ``local_path`` points to a valid local image.
    A fallback placeholder is also considered available, but ``is_fallback``
    identifies it clearly.
    """

    source_url: str = ""
    local_path: str = ""
    content_type: str = ""
    width: int = 0
    height: int = 0
    file_size: int = 0
    cached: bool = False
    is_fallback: bool = False
    error: str = ""

    @property
    def available(self) -> bool:
        return bool(self.local_path) and Path(self.local_path).is_file()

    @property
    def aspect_ratio(self) -> float:
        if self.height <= 0:
            return 0.0
        return self.width / self.height


class ImageService:
    """
    Download, validate and cache newsroom images.

    Parameters
    ----------
    cache_dir:
        Directory used for downloaded images. By default this is
        ``<project root>/cache/images``.
    timeout:
        Network timeout in seconds.
    max_bytes:
        Maximum accepted download size. Defaults to 15 MB.
    user_agent:
        HTTP user-agent sent to image hosts.
    """

    DEFAULT_TIMEOUT: Final[float] = 30.0
    DEFAULT_MAX_BYTES: Final[int] = 15 * 1024 * 1024

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero.")

        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero.")

        project_root = Path(__file__).resolve().parents[2]

        self.cache_dir = Path(
            cache_dir or project_root / "cache" / "images"
        ).resolve()

        self.timeout = float(timeout)
        self.max_bytes = int(max_bytes)
        self.user_agent = user_agent.strip() or DEFAULT_USER_AGENT

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.placeholder_path = (
            self.cache_dir / "newsdesk-image-placeholder.png"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        image_url: str | None,
        *,
        fallback_title: str = "Devour Lincolnshire",
        force_refresh: bool = False,
    ) -> ImageAsset:
        """
        Return a cached or newly downloaded image.

        Image errors never escape from this method. When downloading fails,
        a generated local placeholder is returned and the error is recorded
        in the resulting :class:`ImageAsset`.
        """

        url = str(image_url or "").strip()

        if not url:
            return self.fallback(
                title=fallback_title,
                error="No image URL was supplied.",
            )

        if not self._is_http_url(url):
            return self.fallback(
                title=fallback_title,
                error=f"Unsupported image URL: {url}",
                source_url=url,
            )

        cached_path = self._find_cached_file(url)

        if cached_path is not None and not force_refresh:
            try:
                return self._asset_from_file(
                    cached_path,
                    source_url=url,
                    cached=True,
                )
            except OSError:
                self._safe_unlink(cached_path)

        try:
            return self._download(url)
        except Exception as error:
            LOGGER.warning(
                "Could not obtain image %s: %s",
                url,
                error,
            )
            return self.fallback(
                title=fallback_title,
                error=str(error),
                source_url=url,
            )

    def fallback(
        self,
        *,
        title: str = "Devour Lincolnshire",
        error: str = "",
        source_url: str = "",
    ) -> ImageAsset:
        """
        Return the generated local placeholder image.
        """

        try:
            self._ensure_placeholder(title)
            asset = self._asset_from_file(
                self.placeholder_path,
                source_url=source_url,
                cached=True,
                is_fallback=True,
            )
            return ImageAsset(
                source_url=asset.source_url,
                local_path=asset.local_path,
                content_type=asset.content_type,
                width=asset.width,
                height=asset.height,
                file_size=asset.file_size,
                cached=asset.cached,
                is_fallback=True,
                error=error,
            )
        except Exception as placeholder_error:
            combined_error = error

            if placeholder_error:
                combined_error = (
                    f"{error} Placeholder creation failed: "
                    f"{placeholder_error}"
                ).strip()

            return ImageAsset(
                source_url=source_url,
                error=combined_error,
                is_fallback=True,
            )

    def clear_cache(
        self,
        *,
        include_placeholder: bool = False,
    ) -> int:
        """
        Remove cached image files and return the number removed.
        """

        removed = 0

        for path in self.cache_dir.iterdir():
            if not path.is_file():
                continue

            if (
                path == self.placeholder_path
                and not include_placeholder
            ):
                continue

            try:
                path.unlink()
                removed += 1
            except OSError:
                LOGGER.warning(
                    "Could not remove cached image %s.",
                    path,
                    exc_info=True,
                )

        return removed

    def remove_older_than(
        self,
        *,
        days: int,
        include_placeholder: bool = False,
    ) -> int:
        """
        Remove cache files older than ``days`` and return the number removed.
        """

        if days < 0:
            raise ValueError("days cannot be negative.")

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        removed = 0

        for path in self.cache_dir.iterdir():
            if not path.is_file():
                continue

            if (
                path == self.placeholder_path
                and not include_placeholder
            ):
                continue

            try:
                modified = datetime.fromtimestamp(
                    path.stat().st_mtime,
                    tz=timezone.utc,
                )

                if modified < cutoff:
                    path.unlink()
                    removed += 1

            except OSError:
                LOGGER.warning(
                    "Could not inspect or remove cached image %s.",
                    path,
                    exc_info=True,
                )

        return removed

    # ------------------------------------------------------------------
    # Downloading and validation
    # ------------------------------------------------------------------

    def _download(self, url: str) -> ImageAsset:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": (
                    "image/avif,image/webp,image/apng,image/svg+xml,"
                    "image/*,*/*;q=0.8"
                ),
                "Accept-Language": "en-GB,en;q=0.9",
            },
            method="GET",
        )

        temporary_path = self.cache_dir / (
            f".{self._url_digest(url)}.download"
        )

        try:
            with self._open_image_response(request, url) as response:
                status_code = int(
                    getattr(response, "status", 200)
                )

                if not 200 <= status_code < 300:
                    raise OSError(
                        f"Image server returned HTTP {status_code}."
                    )

                content_type = (
                    response.headers.get_content_type()
                    or ""
                ).lower()

                announced_size = response.headers.get("Content-Length")

                if announced_size:
                    try:
                        if int(announced_size) > self.max_bytes:
                            raise OSError(
                                "Image exceeds the configured size limit."
                            )
                    except ValueError:
                        pass

                total = 0

                with temporary_path.open("wb") as output:
                    while True:
                        chunk = response.read(64 * 1024)

                        if not chunk:
                            break

                        total += len(chunk)

                        if total > self.max_bytes:
                            raise OSError(
                                "Image exceeds the configured size limit."
                            )

                        output.write(chunk)

            extension = self._detect_extension(
                temporary_path,
                url=url,
                content_type=content_type,
            )

            final_path = self.cache_dir / (
                f"{self._url_digest(url)}{extension}"
            )

            if final_path.exists():
                self._safe_unlink(temporary_path)
                return self._asset_from_file(
                    final_path,
                    source_url=url,
                    cached=True,
                )

            shutil.move(str(temporary_path), str(final_path))

            return self._asset_from_file(
                final_path,
                source_url=url,
                cached=False,
            )

        except HTTPError as error:
            raise OSError(
                f"Image server returned HTTP {error.code}."
            ) from error

        except URLError as error:
            reason = getattr(error, "reason", error)
            raise OSError(
                f"Could not connect to image server: {reason}"
            ) from error

        finally:
            self._safe_unlink(temporary_path)

    def _open_image_response(
        self,
        request: Request,
        url: str,
    ):
        """
        Open an image response with normal certificate verification.

        Retford FC images are served through WordPress.com's ``i0.wp.com``
        image proxy. On some Windows/Python installations that endpoint can
        present a certificate chain which is rejected as expired. Only when
        that exact certificate-verification failure occurs, and only for the
        approved Retford image hosts, retry the request with verification
        disabled. All other hosts continue to use normal SSL verification.
        """

        try:
            return urlopen(
                request,
                timeout=self.timeout,
            )
        except URLError as error:
            reason = getattr(error, "reason", error)

            if not self._can_retry_without_ssl_verification(
                url,
                reason,
            ):
                raise

            LOGGER.warning(
                "Retrying Retford image with certificate verification "
                "disabled: %s",
                url,
            )

            context = ssl._create_unverified_context()

            return urlopen(
                request,
                timeout=self.timeout,
                context=context,
            )

    @staticmethod
    def _can_retry_without_ssl_verification(
        url: str,
        reason: object,
    ) -> bool:
        """Return true only for Retford image-host certificate failures."""

        host = (urlparse(url).hostname or "").casefold()

        approved_hosts = {
            "i0.wp.com",
            "retfordfc.co.uk",
            "www.retfordfc.co.uk",
        }

        if host not in approved_hosts:
            return False

        if isinstance(reason, ssl.SSLCertVerificationError):
            return True

        message = str(reason).casefold()

        return (
            "certificate_verify_failed" in message
            or "certificate verify failed" in message
            or "certificate has expired" in message
        )

    def _detect_extension(
        self,
        path: Path,
        *,
        url: str,
        content_type: str,
    ) -> str:
        try:
            with Image.open(path) as image:
                image.verify()
                image_format = str(image.format or "").upper()
        except (UnidentifiedImageError, OSError) as error:
            raise OSError(
                "Downloaded file is not a valid supported image."
            ) from error

        format_extensions = {
            "JPEG": ".jpg",
            "PNG": ".png",
            "WEBP": ".webp",
            "GIF": ".gif",
            "BMP": ".bmp",
        }

        extension = format_extensions.get(image_format)

        if extension:
            return extension

        guessed = mimetypes.guess_extension(content_type) or ""

        if guessed.lower() in ALLOWED_EXTENSIONS:
            return guessed.lower()

        url_extension = Path(
            urlparse(url).path
        ).suffix.lower()

        if url_extension in ALLOWED_EXTENSIONS:
            return url_extension

        raise OSError(
            f"Unsupported image format: {image_format or content_type}"
        )

    def _asset_from_file(
        self,
        path: Path,
        *,
        source_url: str,
        cached: bool,
        is_fallback: bool = False,
    ) -> ImageAsset:
        with Image.open(path) as image:
            width, height = image.size
            image_format = str(image.format or "").upper()

        content_types = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
            "GIF": "image/gif",
            "BMP": "image/bmp",
        }

        return ImageAsset(
            source_url=source_url,
            local_path=str(path),
            content_type=content_types.get(
                image_format,
                mimetypes.guess_type(path.name)[0] or "",
            ),
            width=int(width),
            height=int(height),
            file_size=int(path.stat().st_size),
            cached=cached,
            is_fallback=is_fallback,
        )

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _find_cached_file(self, url: str) -> Path | None:
        digest = self._url_digest(url)

        for extension in sorted(ALLOWED_EXTENSIONS):
            candidate = self.cache_dir / f"{digest}{extension}"

            if candidate.is_file():
                return candidate

        return None

    @staticmethod
    def _url_digest(url: str) -> str:
        return hashlib.sha256(
            url.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _is_http_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme.lower() in {"http", "https"} and bool(
            parsed.netloc
        )

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            LOGGER.debug(
                "Could not remove temporary image file %s.",
                path,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Placeholder
    # ------------------------------------------------------------------

    def _ensure_placeholder(self, title: str) -> None:
        if self.placeholder_path.is_file():
            return

        width = 1200
        height = 675

        image = Image.new(
            "RGB",
            (width, height),
            "#111827",
        )

        draw = ImageDraw.Draw(image)

        draw.rectangle(
            (0, 0, width, 18),
            fill="#ed3b35",
        )

        draw.rectangle(
            (0, height - 18, width, height),
            fill="#ed3b35",
        )

        font_large = self._load_font(58)
        font_small = self._load_font(30)

        heading = "BASSETLAW TODAY"
        subtitle = (
            str(title or "").strip()
            or "NewsDesk image unavailable"
        )

        heading_box = draw.textbbox(
            (0, 0),
            heading,
            font=font_large,
        )

        subtitle_box = draw.textbbox(
            (0, 0),
            subtitle,
            font=font_small,
        )

        heading_width = heading_box[2] - heading_box[0]
        subtitle_width = subtitle_box[2] - subtitle_box[0]

        draw.text(
            ((width - heading_width) / 2, 252),
            heading,
            font=font_large,
            fill="#f8fafc",
        )

        draw.text(
            ((width - subtitle_width) / 2, 340),
            subtitle,
            font=font_small,
            fill="#cbd5e1",
        )

        image.save(
            self.placeholder_path,
            format="PNG",
            optimize=True,
        )

    @staticmethod
    def _load_font(size: int) -> ImageFont.ImageFont:
        font_candidates = (
            "arialbd.ttf",
            "Arial Bold.ttf",
            "DejaVuSans-Bold.ttf",
        )

        for candidate in font_candidates:
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue

        return ImageFont.load_default()


__all__ = [
    "ImageAsset",
    "ImageService",
]