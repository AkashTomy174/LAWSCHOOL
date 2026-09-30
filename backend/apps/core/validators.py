"""Upload validation shared by thumbnail/image fields.

Two layers of defence:

1. **Cheap pre-checks** (extension + declared size) run before Pillow touches
   the file, so a 500 MB upload is rejected without being read into memory.
2. **Real verification** via Pillow's own decoder, which confirms the bytes are
   actually an image rather than a renamed script.

SVG is *not* accepted: it is executable XML and would be a stored-XSS vector
when served from a same-origin media path.
"""

from __future__ import annotations

from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


@deconstructible
class ValidatedImageFile:
    """Validator for ``ImageField``/``FileField`` uploads.

    ``max_bytes`` defaults to ``settings.MAX_IMAGE_UPLOAD_BYTES``.
    """

    def __init__(self, max_bytes: int | None = None) -> None:
        self.max_bytes = max_bytes

    def __call__(self, value) -> None:
        max_bytes = self.max_bytes or settings.MAX_IMAGE_UPLOAD_BYTES

        size = getattr(value, "size", None)
        if size is not None and size > max_bytes:
            raise ValidationError(
                f"Image is too large ({size} bytes). Maximum is {max_bytes} bytes."
            )

        name = getattr(value, "name", "") or ""
        extension = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError(
                "Unsupported image type. Allowed: "
                + ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
            )

        # Decode with Pillow to prove the payload really is an image.
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError:  # pragma: no cover - Pillow is a hard dependency
            raise ValidationError("Image validation is unavailable.")

        try:
            if hasattr(value, "seek"):
                value.seek(0)
            payload = value.read() if hasattr(value, "read") else value
            if hasattr(value, "seek"):
                value.seek(0)
            with Image.open(BytesIO(payload)) as image:
                image.verify()
                if image.format not in ALLOWED_IMAGE_FORMATS:
                    raise ValidationError("Unsupported image format.")
        except ValidationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError):
            raise ValidationError("The uploaded file is not a valid image.")


validate_image_upload = ValidatedImageFile()
