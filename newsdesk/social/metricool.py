"""Small, standard-library Metricool API client."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class MetricoolError(RuntimeError):
    pass


class MetricoolImageError(MetricoolError):
    """Raised when an image cannot be prepared for a Metricool draft."""


class MetricoolClient:
    BASE = "https://app.metricool.com/api"

    def __init__(self, *, token: str, user_id: str, blog_id: str = "", timeout: int = 30) -> None:
        self.token = token.strip()
        self.user_id = user_id.strip()
        self.blog_id = blog_id.strip()
        self.timeout = timeout

    def _request(self, method: str, path: str, *, query: dict[str, str] | None = None, body=None):
        query = query or {}
        url = f"{self.BASE}{path}?{urlencode(query)}"
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=encoded, method=method, headers={"X-Mc-Auth": self.token, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                if not text.strip():
                    return {}
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # Metricool's image normalisation action can return the
                    # imported media URL as an unquoted plain-text response.
                    # Preserve it for normalize_image() instead of treating a
                    # successful import as malformed JSON.
                    return text.strip()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise MetricoolError(f"Metricool returned HTTP {exc.code}: {detail or exc.reason}") from exc
        except (URLError, TimeoutError) as exc:
            raise MetricoolError(f"Metricool could not be reached: {exc}") from exc

    def list_brands(self):
        if not self.token or not self.user_id:
            raise MetricoolError("API token and user ID are required.")
        return self._request("GET", "/admin/simpleProfiles", query={"userId": self.user_id})

    def connection_details(self) -> list[dict[str, Any]]:
        response = self.list_brands()
        if isinstance(response, dict): response = response.get("data") or response.get("profiles") or []
        if not isinstance(response, list): raise MetricoolError("Metricool returned an unexpected brand list.")
        brands = []
        fields = {"facebook": "facebook", "instagram": "instagram", "twitter": "twitter",
                  "linkedin": "linkedinCompany", "threads": "threads", "bluesky": "bluesky"}
        for row in response:
            if not isinstance(row, dict) or row.get("id") is None: continue
            networks = {network: str(row.get(field) or "").strip() for network, field in fields.items() if str(row.get(field) or "").strip()}
            brands.append({"id": str(row["id"]), "name": str(row.get("label") or row.get("title") or row["id"]),
                           "user_id": str(row.get("userId") or self.user_id), "timezone": str(row.get("timezone") or "Europe/London"),
                           "networks": networks})
        if not brands: raise MetricoolError("No Metricool brands are available for this API user.")
        return brands

    def normalize_image(self, image_url: str) -> str:
        if not image_url.strip(): return ""
        try:
            response = self._request("GET", "/actions/normalize/image/url", query={"url": image_url.strip(), "folder": "newsdesk-social"})
        except MetricoolImageError:
            raise
        except Exception as exc:
            raise MetricoolImageError(str(exc)) from exc
        if isinstance(response, str): value = response.strip()
        elif isinstance(response, dict):
            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            value = str(response.get("url") or response.get("mediaUrl") or data.get("url") or "")
        else: value = ""
        if not value.casefold().startswith(("https://", "http://")):
            raise MetricoolImageError("Metricool could not validate the public image URL.")
        return value

    @staticmethod
    def _data(response: Any) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {}
        data = response.get("data")
        return data if isinstance(data, dict) else response

    def upload_local_image(self, image_path: str) -> str:
        """Upload a local JPEG/PNG through Metricool's documented planner-media route."""
        path = Path(image_path)
        try:
            if not path.is_file():
                raise MetricoolImageError("The selected local image file no longer exists.")
            content_type = mimetypes.guess_type(path.name)[0] or ""
            if content_type not in {"image/jpeg", "image/png"}:
                raise MetricoolImageError("Choose a JPEG or PNG image.")
            payload = path.read_bytes()
            if not payload:
                raise MetricoolImageError("The selected image file is empty.")
            if len(payload) > 30 * 1024 * 1024:
                raise MetricoolImageError("The selected image exceeds Facebook's 30 MB limit.")
            checksum = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
            request_body = {
                "resourceType": "planner",
                "contentType": content_type,
                "fileExtension": path.suffix.lstrip(".").lower(),
                "parts": [{"size": len(payload), "startByte": 0, "endByte": len(payload), "hash": checksum}],
            }
            query = {"blogId": self.blog_id, "userId": self.user_id}
            transaction = self._data(self._request("PUT", "/v2/media/s3/upload-transactions", query=query, body=request_body))
            presigned_url = str(transaction.get("presignedUrl") or "")
            file_url = str(transaction.get("fileUrl") or "")
            if not presigned_url or not file_url:
                raise MetricoolImageError("Metricool did not provide a local-image upload address.")
            upload = Request(
                presigned_url,
                data=payload,
                method="PUT",
                headers={"Content-Type": content_type, "x-amz-checksum-sha256": checksum},
            )
            with urlopen(upload, timeout=self.timeout) as response:
                response.read()
            completed = self._data(self._request(
                "PATCH",
                "/v2/media/s3/upload-transactions",
                query=query,
                body={"simple": {"fileUrl": file_url}},
            ))
            value = str(completed.get("convertedFileUrl") or completed.get("fileUrl") or file_url)
            if not value:
                raise MetricoolImageError("Metricool did not return the uploaded image.")
            return value
        except MetricoolImageError:
            raise
        except Exception as exc:
            raise MetricoolImageError(str(exc)) from exc

    def import_source_image(self, image_url: str) -> str:
        """Import a source image, uploading it when URL normalisation is refused."""

        try:
            return self.normalize_image(image_url)
        except MetricoolImageError as normalise_error:
            request = Request(
                image_url.strip(),
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; DevourLincolnshireNewsDesk/1.0)",
                    "Accept": "image/jpeg,image/png,image/*;q=0.8",
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = response.read(30 * 1024 * 1024 + 1)
                    content_type = str(response.headers.get_content_type() or "").casefold()
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                raise MetricoolImageError(
                    f"Metricool rejected the source image URL and NewsDesk could not download the image: {exc}"
                ) from exc
            if not payload:
                raise MetricoolImageError("The source website returned an empty image.")
            if len(payload) > 30 * 1024 * 1024:
                raise MetricoolImageError("The source image exceeds Facebook's 30 MB limit.")
            suffix = Path(urlsplit(image_url).path).suffix.casefold()
            if content_type == "image/jpeg" or suffix in {".jpg", ".jpeg"}:
                suffix = ".jpg"
            elif content_type == "image/png" or suffix == ".png":
                suffix = ".png"
            else:
                raise MetricoolImageError(
                    "Metricool rejected the source image URL and the downloaded file is not a JPEG or PNG."
                ) from normalise_error
            with TemporaryDirectory(prefix="newsdesk-metricool-") as folder:
                temporary_image = Path(folder) / f"source{suffix}"
                temporary_image.write_bytes(payload)
                return self.upload_local_image(str(temporary_image))

    def create_draft(self, *, text: str, providers: list[str], publication_datetime: str, timezone: str, image_url: str = "", image_path: str = ""):
        if not self.token or not self.user_id or not self.blog_id:
            raise MetricoolError("API token, user ID and brand/blog ID are required.")
        body = {
            "publicationDate": {"dateTime": publication_datetime, "timezone": timezone},
            "text": text,
            "providers": [{"network": value} for value in providers],
            "autoPublish": False,
            "draft": True,
            "shortener": False,
            "saveExternalMediaFiles": bool(image_url),
        }
        if image_path:
            body["media"] = [self.upload_local_image(image_path)]
        elif image_url:
            body["media"] = [self.import_source_image(image_url)]
        return self._request("POST", "/v2/scheduler/posts", query={"blogId": self.blog_id, "userId": self.user_id}, body=body)

    @staticmethod
    def draft_id(response: Any) -> str:
        if not isinstance(response, dict): return ""
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        return str(data.get("id") or data.get("postId") or "")
