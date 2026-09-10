"""Turn an uploaded photo into the two sizes the app actually displays.

Recipe pictures used to come from an image model at 1024x640, so every one of
them was already small and already a known format. A photo out of a phone is
neither: 4000px wide, 6 MB, HEIC-turned-JPEG, and rotated by an EXIF flag that
only some viewers honour. Everything here exists to flatten those differences
before anything reaches the object store.

Two sizes are produced from one upload: the cards load thumbnails by the
dozen, and only the detail page ever needs the full picture.
"""

import logging
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

# Longest side, in pixels. The full size is generous enough to fill a desktop
# detail panel on a retina screen and no more; the thumbnail is twice the
# 184px card width, for the same reason.
FULL_MAX = 1600
THUMB_MAX = 480

FULL_QUALITY = 82
THUMB_QUALITY = 78

# Everything is re-encoded to JPEG, whatever came in: it is the one format
# every browser and the Android WebView decode, and a photo gains nothing from
# PNG but bytes. The alpha channel of a transparent PNG is flattened onto
# white rather than turned into black, which is what JPEG would do on its own.
CONTENT_TYPE = "image/jpeg"
SUFFIX = "jpg"


class UnreadableImage(Exception):
    """The upload is not an image, or is one Pillow cannot decode."""


def _encode(image: Image.Image, max_side: int, quality: int) -> bytes:
    # `thumbnail` shrinks in place and never enlarges, so a small picture is
    # re-encoded rather than blown up into a blurry "full size".
    resized = image.copy()
    resized.thumbnail((max_side, max_side), Image.LANCZOS)

    buffer = BytesIO()
    resized.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def render(data: bytes) -> tuple[bytes, bytes]:
    """Return (full, thumbnail) JPEG bytes for one uploaded image."""
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise UnreadableImage(str(exc)) from exc

    # Phones store the sensor's own frame plus a rotation flag. Applying it
    # here means the picture is upright everywhere afterwards, including in
    # the <img> tags of browsers that ignore EXIF on a re-encoded file.
    image = ImageOps.exif_transpose(image) or image

    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        flattened.paste(image, mask=image.split()[-1])
        image = flattened
    elif image.mode != "RGB":
        image = image.convert("RGB")

    return _encode(image, FULL_MAX, FULL_QUALITY), _encode(image, THUMB_MAX, THUMB_QUALITY)
