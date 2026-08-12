"""Thumbnails for the file list, generated once and cached.

Why this is a backend path rather than a URL per file
-----------------------------------------------------
The obvious way to show a picture in a listing is to presign each file and hand the
URLs to an `<img>`. That costs one Lambda invocation per row -- a hundred for a
hundred-file page -- and the browser then downloads the full original to draw
something 96 pixels wide. On a phone over cellular that is the whole file for a
thumbnail.

So the work happens here: one call for the whole page, and what comes back are URLs
for downscaled JPEGs held in a cache bucket. A cache entry is keyed by the source
ETag, so an edited file gets a new thumbnail and a re-uploaded one does not serve the
old picture.

What this deliberately does not do
----------------------------------
It does not fail a page because one file is awkward. Anything not eligible -- an
unsupported type, a source over the size limit, a key the caller may not read -- comes
back under `skipped` with a reason, and the UI keeps its icon for that row. A batch
that raised on the first oddity would make the feature less reliable than no feature.

It does not carry EXIF into the thumbnail. Saving a resized image writes a new JPEG
with no metadata, so the location a phone recorded in the original is not republished
in a picture the list shows to everyone who can see the row.

It does not generate without bound. Cache lookups are cheap and every key gets one;
generation is capped per invocation, and keys past the cap return under `pending` for
the next call to pick up. The alternative is a timeout, which loses the work already
done.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os

import boto3
from botocore.config import Config
from PIL import Image, ImageOps, UnidentifiedImageError

from shared.portal_path_scope import allowed_prefixes, reject_key
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

# Presigning is a client-side SigV4 calculation, and for FSx for ONTAP S3 AP it only
# produces a working URL with the regional endpoint and signature version pinned. The
# cache bucket is an ordinary bucket, but the same client serves both.
#
# This is the one place a portal handler builds its own S3 client instead of going
# through S3ApHelper: the helper covers access-point objects, and the cache bucket is
# neither an access point nor user data. Source reads below do go through the helper.
_s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)

GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
CACHE_BUCKET = os.environ.get("THUMBNAIL_CACHE_BUCKET", "")

# The longest edge of the generated image. A list row shows it far smaller; the extra
# pixels are for high-density screens, which is most phones.
EDGE_PX = int(os.environ.get("THUMBNAIL_EDGE_PX", "192"))

# Sources larger than this are not decoded. A limit in bytes rather than pixels
# because it is what HeadObject can tell us before spending the download.
MAX_SOURCE_BYTES = int(os.environ.get("THUMBNAIL_MAX_SOURCE_BYTES", str(25 * 1024 * 1024)))

# How long a returned URL stays valid. Long enough to scroll a page, short enough that
# a copied link is not a lasting way to read the thumbnail.
URL_TTL_SECONDS = min(int(os.environ.get("THUMBNAIL_URL_TTL", "900")), 3600)

# Keys accepted in one call. The listing page is the caller, so this matches a page.
MAX_KEYS_PER_CALL = 100

# Generations attempted in one call, the rest reported as pending. Each generation is
# a download plus a decode; the cap is what keeps a cold page inside the timeout.
GENERATE_BUDGET = 12

# Types Pillow reads that are worth showing. Raw camera formats and EXR are excluded
# on purpose: Pillow either cannot read them or needs plugins this layer does not
# carry, and a format that fails on every attempt should not cost a download first.
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff")

# A decode bound, not a size bound. Pillow raises above this rather than allocating,
# which is what stops a small file that claims enormous dimensions from taking the
# function down. 40 megapixels is past any phone camera and far below a bomb.
Image.MAX_IMAGE_PIXELS = 40_000_000


def _resolve_ap_alias(groups: list[str]) -> str:
    """The access point this caller reads through.

    Same mapping as the listing, because a thumbnail must come from the same place
    the row did. Reading it from a different alias would show one team a picture of
    another team's file.
    """
    if GROUP_AP_MAPPING and groups:
        for group_name, ap_alias in GROUP_AP_MAPPING.items():
            if group_name in groups:
                return ap_alias
    return DEFAULT_AP_ALIAS


def _cache_key(alias: str, key: str, etag: str) -> str:
    """Where the thumbnail for this exact version of this object lives.

    The ETag is in the hash, so editing a file produces a different cache key rather
    than serving the previous picture. The alias is in it too: the same key under two
    access points is two different objects, and one must not answer for the other.

    The digest is a cache address, not a signature -- it is not relied on for
    authorization, which happens before this is called.
    """
    material = f"{alias}\0{key}\0{etag}\0{EDGE_PX}".encode()
    return f"thumbnails/v1/{hashlib.sha256(material).hexdigest()}.jpg"


def _presign_cached(cache_key: str) -> str:
    """A time-limited URL for a thumbnail that exists."""
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": CACHE_BUCKET, "Key": cache_key},
        ExpiresIn=URL_TTL_SECONDS,
    )


def _cache_hit(cache_key: str) -> bool:
    """Whether this thumbnail has already been generated.

    A denied HeadObject is indistinguishable from a missing object here, and that is
    acceptable: the generation that follows writes to the same key, and if writing is
    denied too the caller sees that error instead of a wrong answer from here.
    """
    try:
        _s3.head_object(Bucket=CACHE_BUCKET, Key=cache_key)
        return True
    except Exception:
        return False


def _render(source: bytes) -> bytes:
    """A downscaled JPEG of `source`.

    `exif_transpose` first, because a phone writes the sensor's orientation into EXIF
    rather than rotating the pixels; without it a portrait photo arrives on its side.
    The result is then flattened to RGB -- JPEG has no alpha channel, and saving an
    RGBA or palette image without converting raises rather than dropping it quietly.
    """
    with Image.open(io.BytesIO(source)) as image:
        upright = ImageOps.exif_transpose(image) or image
        if upright.mode not in ("RGB", "L"):
            upright = upright.convert("RGB")
        upright.thumbnail((EDGE_PX, EDGE_PX), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        # No `exif=` argument, so the thumbnail carries none of the original's
        # metadata. See the module docstring.
        upright.save(out, format="JPEG", quality=80, optimize=True)
        return out.getvalue()


def _eligible(key: str) -> str | None:
    """Why this key cannot have a thumbnail, or None if it can."""
    lowered = key.lower()
    if not lowered.endswith(SUPPORTED_EXTENSIONS):
        return "unsupported type"
    return None


def get_thumbnails(event: dict) -> dict:
    """Thumbnail URLs for a page of files, generating what is missing.

    Args:
        event: `keys` (the object keys to render), plus `groups` and `userId` supplied
            by the resolver from the caller's Cognito identity.

    Returns:
        `thumbnails` maps a key to a URL. `pending` lists keys whose thumbnail is not
        built yet because the generation budget was spent. `skipped` maps a key to the
        reason it will never have one, so the caller can stop asking.
    """
    if not CACHE_BUCKET:
        return {"error": "THUMBNAIL_CACHE_BUCKET is not configured"}

    keys = event.get("keys")
    if not isinstance(keys, list) or not keys:
        return {"error": "keys is required"}
    if len(keys) > MAX_KEYS_PER_CALL:
        return {"error": f"keys exceeds the {MAX_KEYS_PER_CALL}-key limit for one call"}

    groups = event.get("groups") if isinstance(event.get("groups"), list) else []
    alias = _resolve_ap_alias(groups)
    if not alias:
        return {"error": "S3_AP_ALIAS is not configured"}
    allowed = allowed_prefixes(groups, GROUP_PATH_PREFIXES)
    helper = S3ApHelper(alias)

    thumbnails: dict[str, str] = {}
    pending: list[str] = []
    skipped: dict[str, str] = {}
    generated = 0

    for key in keys:
        if not isinstance(key, str):
            continue
        # Authorization before anything else, and the same check the listing applies.
        # Without it this endpoint would read any key a caller cared to name.
        refused = reject_key(key, allowed, field="key")
        if refused:
            skipped[key] = refused["error"]
            continue
        reason = _eligible(key)
        if reason:
            skipped[key] = reason
            continue

        try:
            head = helper.head_object(key)
        except Exception as error:  # noqa: BLE001 - one bad key must not fail the page
            logger.info("thumbnail head failed for %s: %s", key, error)
            skipped[key] = "not readable"
            continue

        size = int(head.get("ContentLength", 0) or 0)
        if size > MAX_SOURCE_BYTES:
            skipped[key] = f"larger than {MAX_SOURCE_BYTES} bytes"
            continue
        etag = str(head.get("ETag", "")).strip('"')
        if not etag:
            # Without a version to key on, a cached thumbnail could outlive the file
            # it depicts. Better to show the icon than the wrong picture.
            skipped[key] = "no ETag to key the cache on"
            continue

        cached = _cache_key(alias, key, etag)
        if _cache_hit(cached):
            thumbnails[key] = _presign_cached(cached)
            continue
        if generated >= GENERATE_BUDGET:
            pending.append(key)
            continue

        try:
            body = helper.get_object(key)["Body"].read()
            image = _render(body)
        except (UnidentifiedImageError, Image.DecompressionBombError) as error:
            # The extension said it was an image and the bytes disagree, or the
            # dimensions are past the decode bound. Neither is retryable.
            logger.info("thumbnail render refused for %s: %s", key, error)
            skipped[key] = "not a readable image"
            continue
        except Exception as error:  # noqa: BLE001 - one bad key must not fail the page
            logger.warning("thumbnail generation failed for %s: %s", key, error)
            skipped[key] = "generation failed"
            continue

        try:
            _s3.put_object(
                Bucket=CACHE_BUCKET,
                Key=cached,
                Body=image,
                ContentType="image/jpeg",
                # Read back by nothing but this function, and only ever regenerated,
                # so the source key is recorded for operators rather than for logic.
                Metadata={"source-etag": etag},
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("thumbnail cache write failed for %s: %s", key, error)
            skipped[key] = "cache write failed"
            continue

        generated += 1
        thumbnails[key] = _presign_cached(cached)

    logger.info(
        "thumbnails: %d served, %d generated, %d pending, %d skipped",
        len(thumbnails),
        generated,
        len(pending),
        len(skipped),
    )
    return {
        "thumbnails": thumbnails,
        "pending": pending,
        "skipped": skipped,
        "expiresIn": URL_TTL_SECONDS,
        "error": None,
    }


def handler(event: dict, context: object) -> dict:
    """Dispatch entry point.

    One action today. The shape matches the other dispatch endpoints so the resolver,
    the generated action types and the parameter check all treat it the same way.
    """
    action = event.get("action", "")
    if action == "getThumbnails":
        return get_thumbnails(event)
    return {"error": f"Unknown action: {action}"}
