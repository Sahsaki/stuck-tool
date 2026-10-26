"""Small, bounded image inputs for local CLI and MCP callers."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Sequence

MAX_IMAGES = 3
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 8 * 1024 * 1024
MAX_BASE64_CHARS = 4 * ((MAX_IMAGE_BYTES + 2) // 3)

MIME_SIGNATURES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}
SUPPORTED_MIME_TYPES = {*MIME_SIGNATURES, "image/webp"}
PATH_MIMES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _matches_signature(mime_type: str, data: bytes) -> bool:
    if mime_type == "image/webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return data.startswith(MIME_SIGNATURES[mime_type])


def validate_images(images: Sequence[tuple[str, bytes]] | None) -> list[tuple[str, bytes]]:
    """Validate image count, size, MIME type, and file signature before provider use."""
    if images is None:
        return []
    if not isinstance(images, (list, tuple)) or len(images) > MAX_IMAGES:
        raise ValueError(f"Provide no more than {MAX_IMAGES} images")

    total = 0
    validated = []
    for image in images:
        if not isinstance(image, (list, tuple)) or len(image) != 2:
            raise ValueError("Each image must contain a MIME type and image bytes")
        mime_type, data = image
        if not isinstance(mime_type, str) or mime_type not in SUPPORTED_MIME_TYPES:
            raise ValueError("Images must be PNG, JPEG, or WebP bytes")
        if not isinstance(data, bytes):
            raise ValueError("Images must be PNG, JPEG, or WebP bytes")
        if not data or len(data) > MAX_IMAGE_BYTES or not _matches_signature(mime_type, data):
            raise ValueError("Image is empty, too large, or does not match its MIME type")
        total += len(data)
        if total > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError(
                f"Images must total no more than "
                f"{MAX_TOTAL_IMAGE_BYTES // (1024 * 1024)} MiB"
            )
        validated.append((mime_type, data))
    return validated


def decode_mcp_images(images) -> list[tuple[str, bytes]]:
    """Decode the MCP tool's base64 image objects without accepting URLs or files."""
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError(f"Provide no more than {MAX_IMAGES} images")

    decoded = []
    total = 0
    for image in images:
        if not isinstance(image, dict) or set(image) != {"mime_type", "data"}:
            raise ValueError("Each image must contain only 'mime_type' and base64 'data'")
        mime_type, encoded = image["mime_type"], image["data"]
        if not isinstance(mime_type, str) or mime_type not in SUPPORTED_MIME_TYPES:
            raise ValueError("Images must be base64 PNG, JPEG, or WebP data")
        if not isinstance(encoded, str):
            raise ValueError("Images must be base64 PNG, JPEG, or WebP data")
        if len(encoded) > MAX_BASE64_CHARS:
            raise ValueError("Image exceeds the 4 MiB per-image limit")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Image data must be valid base64") from None
        total += len(data)
        if total > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("Images must total no more than 8 MiB")
        decoded.append((mime_type, data))
    return validate_images(decoded)


def load_image(path: Path) -> tuple[str, bytes]:
    """Read one user-selected local image without an unbounded file read."""
    mime_type = PATH_MIMES.get(path.suffix.lower())
    if not mime_type:
        raise ValueError("Image files must use .png, .jpg, .jpeg, or .webp")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
    except OSError:
        raise ValueError("Could not read the selected image file") from None
    return validate_images([(mime_type, data)])[0]
