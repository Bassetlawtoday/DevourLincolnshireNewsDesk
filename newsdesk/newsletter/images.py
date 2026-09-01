"""Tenant-aware approved image library and non-destructive derivatives."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from .models import ImageRights, RightsStatus, utc_now
from .store import NewsletterStore


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_MASTER_BYTES = 30 * 1024 * 1024


@dataclass(slots=True)
class ImageAsset:
    asset_id: str = field(default_factory=lambda: uuid4().hex)
    tenant_key: str = ""
    title: str = ""
    master_path: str = ""
    master_sha256: str = ""
    width: int = 0
    height: int = 0
    topics: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    alt_text: str = ""
    rights: ImageRights = field(default_factory=ImageRights)
    created_at: datetime = field(default_factory=utc_now)
    created_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["rights"] = self.rights.to_dict()
        result["created_at"] = self.created_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageAsset":
        values = dict(data)
        values["rights"] = ImageRights.from_dict(values.get("rights") or {})
        values["created_at"] = datetime.fromisoformat(
            str(values.get("created_at") or utc_now().isoformat()).replace("Z", "+00:00")
        )
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ImageDerivative:
    asset_id: str
    path: str
    sha256: str
    branded: bool
    credit: str
    alt_text: str


class ImageLibrary:
    """Persist approved masters separately and generate auditable derivatives."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        logo_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root or Path("data") / "newsletter" / "images")
        self.index_path = self.root / "library.json"
        self.master_dir = self.root / "masters"
        self.derivative_dir = self.root / "derivatives"
        self.logo_path = Path(logo_path or Path("assets") / "devour_lincolnshire_logo.png")

    def list_assets(self, *, tenant_key: str) -> list[ImageAsset]:
        tenant = _tenant(tenant_key)
        return sorted(
            (asset for asset in self._load() if asset.tenant_key == tenant),
            key=lambda asset: (asset.title.casefold(), asset.asset_id),
        )

    def search_assets(
        self,
        *,
        tenant_key: str,
        query: str = "",
        availability: str = "all",
        sort_by: str = "newest",
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ImageAsset], int]:
        """Return one filtered page so the UI never renders the whole library."""
        tenant = _tenant(tenant_key)
        needle = str(query or "").strip().casefold()
        availability_key = str(availability or "all").strip().casefold()
        matches: list[ImageAsset] = []
        for asset in self._load():
            if asset.tenant_key != tenant:
                continue
            usable = asset.rights.usable(tenant_key=tenant)
            if availability_key == "usable" and not usable:
                continue
            if availability_key == "blocked" and usable:
                continue
            searchable = " ".join(
                [
                    asset.title,
                    asset.alt_text,
                    *asset.topics,
                    *asset.locations,
                    asset.rights.copyright_owner,
                    asset.rights.supplier,
                    asset.rights.attribution,
                    asset.rights.licence_type,
                ]
            ).casefold()
            if needle and needle not in searchable:
                continue
            matches.append(asset)

        if str(sort_by or "").strip().casefold() == "title":
            matches.sort(key=lambda asset: (asset.title.casefold(), asset.asset_id))
        else:
            matches.sort(key=lambda asset: (asset.created_at, asset.asset_id), reverse=True)
        total = len(matches)
        start = max(0, int(offset or 0))
        page_size = min(100, max(1, int(limit or 50)))
        return matches[start : start + page_size], total

    def get(self, asset_id: str, *, tenant_key: str) -> ImageAsset:
        tenant = _tenant(tenant_key)
        for asset in self._load():
            if asset.asset_id == asset_id and asset.tenant_key == tenant:
                return asset
        raise KeyError("Approved image was not found for this newsroom.")

    def update_details(
        self,
        asset_id: str,
        *,
        tenant_key: str,
        title: str,
        alt_text: str,
        attribution: str,
        topics: list[str] | None = None,
        locations: list[str] | None = None,
    ) -> ImageAsset:
        """Correct descriptive metadata without changing the master or rights evidence."""
        tenant = _tenant(tenant_key)
        clean_title = str(title).strip()
        clean_alt = str(alt_text).strip()
        if not clean_title or not clean_alt:
            raise ValueError("Image title and alt text are required.")

        assets = self._load()
        selected = None
        for asset in assets:
            if asset.asset_id == asset_id and asset.tenant_key == tenant:
                selected = asset
                break
        if selected is None:
            raise KeyError("Approved image was not found for this newsroom.")

        master = Path(selected.master_path)
        if not master.is_file() or _sha256(master) != selected.master_sha256:
            raise ValueError("The approved master is missing or has changed.")

        selected.title = clean_title
        selected.alt_text = clean_alt
        selected.topics = _clean_terms(topics)
        selected.locations = _clean_terms(locations)
        selected.rights.attribution = str(attribution).strip()
        self._save(assets)
        return selected

    def import_asset(
        self,
        source_path: str | Path,
        *,
        tenant_key: str,
        title: str,
        rights: ImageRights,
        alt_text: str,
        topics: list[str] | None = None,
        locations: list[str] | None = None,
        actor: str = "",
    ) -> ImageAsset:
        source = Path(source_path)
        if not source.is_file() or source.suffix.casefold() not in ALLOWED_EXTENSIONS:
            raise ValueError("Choose a JPG, PNG or WebP image file.")
        if source.stat().st_size > MAX_MASTER_BYTES:
            raise ValueError("The image is larger than the 30 MB safety limit.")
        tenant = _tenant(tenant_key)
        if rights.tenant_key and rights.tenant_key.casefold() != tenant:
            raise ValueError("The rights record belongs to a different newsroom.")
        rights.tenant_key = tenant
        if rights.status == RightsStatus.RED:
            raise ValueError("Red or unknown-rights images cannot enter the approved library.")
        if not rights.usable(tenant_key=tenant):
            raise ValueError("The rights record is incomplete or does not permit newsletter use.")
        if not str(title).strip() or not str(alt_text).strip():
            raise ValueError("Image title and alt text are required.")
        try:
            with Image.open(source) as image:
                image.verify()
            with Image.open(source) as image:
                width, height = image.size
        except (UnidentifiedImageError, OSError, ValueError):
            raise ValueError("The selected file is not a valid supported image.") from None
        digest = _sha256(source)
        assets = self._load()
        duplicate = next(
            (asset for asset in assets if asset.tenant_key == tenant and asset.master_sha256 == digest),
            None,
        )
        if duplicate:
            raise ValueError(f"This master is already in the library as ‘{duplicate.title}’.")
        asset_id = uuid4().hex
        destination = self.master_dir / tenant / f"{asset_id}{source.suffix.casefold()}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        asset = ImageAsset(
            asset_id=asset_id,
            tenant_key=tenant,
            title=str(title).strip(),
            master_path=str(destination),
            master_sha256=digest,
            width=width,
            height=height,
            topics=_clean_terms(topics),
            locations=_clean_terms(locations),
            alt_text=str(alt_text).strip(),
            rights=rights,
            created_by=str(actor).strip(),
        )
        asset.rights.asset_id = asset.asset_id
        assets.append(asset)
        try:
            self._save(assets)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return asset

    def create_derivative(self, asset_id: str, *, tenant_key: str) -> ImageDerivative:
        asset = self.get(asset_id, tenant_key=tenant_key)
        master = Path(asset.master_path)
        if not master.is_file() or _sha256(master) != asset.master_sha256:
            raise ValueError("The approved master is missing or has changed.")
        if not asset.rights.usable(tenant_key=asset.tenant_key):
            raise ValueError("The image rights are no longer valid for this newsletter.")
        branded = asset.rights.brandable(tenant_key=asset.tenant_key)
        signature = hashlib.sha256(
            (asset.master_sha256 + "|" + str(branded) + "|stage4-v1").encode("utf-8")
        ).hexdigest()[:20]
        destination = self.derivative_dir / asset.tenant_key / f"{asset.asset_id}-{signature}.jpg"
        if not destination.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._render_derivative(master, destination, branded=branded)
        return ImageDerivative(
            asset_id=asset.asset_id,
            path=str(destination),
            sha256=_sha256(destination),
            branded=branded,
            credit=asset.rights.attribution.strip() or asset.rights.copyright_owner.strip(),
            alt_text=asset.alt_text,
        )

    def _render_derivative(self, master: Path, destination: Path, *, branded: bool) -> None:
        with Image.open(master) as source:
            image = source.convert("RGB")
            image.thumbnail((1600, 1000), Image.Resampling.LANCZOS)
            if branded:
                image = self._brand(image)
            temporary = destination.with_suffix(".tmp")
            image.save(temporary, format="JPEG", quality=88, optimize=True)
            os.replace(temporary, destination)

    def _brand(self, image: Image.Image) -> Image.Image:
        result = image.copy()
        width, height = result.size
        band = max(34, min(72, height // 10))
        canvas = Image.new("RGB", (width, height + band), "#111827")
        canvas.paste(result, (0, 0))
        if self.logo_path.is_file():
            try:
                with Image.open(self.logo_path) as logo_source:
                    logo = logo_source.convert("RGBA")
                    logo.thumbnail((max(80, width // 5), band - 10), Image.Resampling.LANCZOS)
                    canvas.paste(logo, (width - logo.width - 12, height + (band - logo.height) // 2), logo)
                    return canvas
            except (UnidentifiedImageError, OSError):
                pass
        draw = ImageDraw.Draw(canvas)
        draw.text((12, height + band // 3), "Devour Lincolnshire", fill="white", font=ImageFont.load_default())
        return canvas

    def _load(self) -> list[ImageAsset]:
        if not self.index_path.exists():
            return []
        try:
            document = json.loads(self.index_path.read_text(encoding="utf-8"))
            if int(document.get("schema_version", -1)) != self.SCHEMA_VERSION:
                raise ValueError("Unsupported image-library schema.")
            NewsletterStore._reject_secrets(document)
            return [ImageAsset.from_dict(value) for value in document.get("assets", [])]
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("The image library could not be read safely.") from exc

    def _save(self, assets: list[ImageAsset]) -> None:
        document = {"schema_version": self.SCHEMA_VERSION, "assets": [a.to_dict() for a in assets]}
        NewsletterStore._reject_secrets(document)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".library.", suffix=".tmp", dir=self.index_path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.index_path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise


def _tenant(value: str) -> str:
    tenant = str(value or "").strip().casefold()
    if not tenant:
        raise ValueError("Tenant key is required.")
    return tenant


def _clean_terms(values) -> list[str]:
    return sorted({str(value).strip() for value in (values or []) if str(value).strip()}, key=str.casefold)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
