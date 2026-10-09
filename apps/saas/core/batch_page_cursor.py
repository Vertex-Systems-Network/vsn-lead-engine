"""Pure, short-lived continuation contract for future v3 result pages."""

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from rest_framework.exceptions import ValidationError

from .result_query import validate_filters

PAGE_SIZE = 25
MAX_AGE = 900
MAX_CURSOR_BYTES = 2048
DOMAIN = b"saas.v3.result-page.v1\0"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SOURCE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


@dataclass(frozen=True)
class PagePosition:
    source: str
    batch: int
    position: int
    row_id: str


@dataclass(frozen=True)
class PageContinuation:
    watermark: PagePosition
    after: PagePosition


def _invalid():
    raise ValidationError({"after": "Invalid or expired result continuation."})


def _uuid(value):
    if type(value) is not str or len(value) != 36:
        _invalid()
    try:
        parsed = UUID(value)
    except ValueError:
        _invalid()
    if str(parsed) != value:
        _invalid()
    return value


def _position(value):
    if type(value) is not list or len(value) != 4:
        _invalid()
    source, batch, position, row_id = value
    if (
        type(source) is not str
        or not SOURCE.fullmatch(source)
        or type(batch) is not int
        or not 1 <= batch <= 1000
        or type(position) is not int
        or not 1 <= position <= PAGE_SIZE
    ):
        _invalid()
    return PagePosition(source, batch, position, _uuid(row_id))


def _coordinates(value):
    if type(value) is not PagePosition:
        _invalid()
    return [value.source, value.batch, value.position, value.row_id]


def _key():
    key = getattr(settings, "SAAS_BATCH_PAGE_SIGNING_KEY", "")
    if type(key) is not str or len(key.encode("utf-8")) < 32:
        _invalid()
    return key.encode("utf-8")


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _filter_digest(country, category, source):
    validate_filters(country, category, source)
    encoded = json.dumps([country, category, source], separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _context(workspace_id, job_id, actor_id, request_hash, country, category, source):
    if type(request_hash) is not str or not HEX64.fullmatch(request_hash):
        _invalid()
    return [
        _uuid(str(workspace_id)),
        _uuid(str(job_id)),
        _uuid(str(actor_id)),
        request_hash,
        _filter_digest(country, category, source),
    ]


def encode_page_cursor(
    workspace_id,
    job_id,
    actor_id,
    request_hash,
    watermark,
    after,
    *,
    country="",
    category="",
    source="",
    now=None,
):
    """Issue only after a service has verified immutable completion and current rights."""
    key = _key()
    context = _context(workspace_id, job_id, actor_id, request_hash, country, category, source)
    upper = _position(_coordinates(watermark))
    last = _position(_coordinates(after))
    if tuple(last.__dict__.values()) > tuple(upper.__dict__.values()):
        _invalid()
    issued = int(time.time() if now is None else now)
    if issued < 0:
        _invalid()
    payload = [1, context, list(upper.__dict__.values()), list(last.__dict__.values()), issued]
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    signature = hmac.new(key, DOMAIN + body, hashlib.sha256).digest()
    cursor = f"{_b64(body)}.{_b64(signature)}"
    if len(cursor) > MAX_CURSOR_BYTES:
        _invalid()
    return cursor


def decode_page_cursor(
    cursor,
    workspace_id,
    job_id,
    actor_id,
    request_hash,
    *,
    country="",
    category="",
    source="",
    now=None,
):
    key = _key()
    expected = _context(workspace_id, job_id, actor_id, request_hash, country, category, source)
    if type(cursor) is not str or not 1 <= len(cursor) <= MAX_CURSOR_BYTES:
        _invalid()
    try:
        body_part, signature_part = cursor.split(".")
        body = base64.b64decode(
            body_part + "=" * (-len(body_part) % 4), altchars=b"-_", validate=True
        )
        signature = base64.b64decode(
            signature_part + "=" * (-len(signature_part) % 4), altchars=b"-_", validate=True
        )
        if _b64(body) != body_part or _b64(signature) != signature_part:
            _invalid()
        actual = hmac.new(key, DOMAIN + body, hashlib.sha256).digest()
        if len(signature) != 32 or not hmac.compare_digest(signature, actual):
            _invalid()
        data = json.loads(body)
    except (ValueError, UnicodeError, TypeError):
        _invalid()
    if type(data) is not list or len(data) != 5 or data[0] != 1 or type(data[0]) is not int:
        _invalid()
    if data[1] != expected or type(data[1]) is not list:
        _invalid()
    upper = _position(data[2])
    last = _position(data[3])
    issued = data[4]
    clock = int(time.time() if now is None else now)
    if (
        type(issued) is not int
        or issued < 0
        or issued > clock + 30
        or clock >= issued + MAX_AGE
        or tuple(last.__dict__.values()) > tuple(upper.__dict__.values())
    ):
        _invalid()
    return PageContinuation(upper, last)
