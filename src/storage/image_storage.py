from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import tempfile
import time
import threading
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Literal, Protocol
from urllib.parse import urlparse

from PIL import Image, ImageOps, features, __version__ as PILLOW_VERSION

from .config import Settings
from .contracts import digest_json

KEY_RE = re.compile(r'^(images|thumbs|originals|sources)/[a-f0-9]{2}/[a-f0-9]{2}/([a-f0-9]{64})\.(webp|bin|xlsx)$')


class MediaError(ValueError):
    pass


@dataclass(frozen=True)
class StoredBlob:
    uri: str
    sha256: str
    size: int


class BlobStore(Protocol):
    def put(self, payload: bytes, *, prefix: str, extension: str, mime_type: str) -> StoredBlob: ...
    def read(self, uri: str, *, max_bytes: int) -> bytes: ...


def object_key(payload: bytes, prefix: str, extension: str) -> tuple[str, str]:
    checksum = hashlib.sha256(payload).hexdigest()
    key = f'{prefix}/{checksum[:2]}/{checksum[2:4]}/{checksum}.{extension}'
    if not KEY_RE.fullmatch(key):
        raise MediaError('Invalid content-addressable key.')
    return key, checksum


def verify_blob(key: str, payload: bytes) -> bytes:
    match = KEY_RE.fullmatch(key)
    if not match or hashlib.sha256(payload).hexdigest() != match.group(2):
        raise MediaError('Stored object checksum mismatch.')
    return payload


class LocalCAS:
    def __init__(self, root: Path, *, min_free_bytes: int = 5 * 1024**3):
        self.root = root.resolve()
        self.root.mkdir(mode=0o750, parents=True, exist_ok=True)
        self.min_free_bytes = min_free_bytes

    def _path(self, key: str) -> Path:
        if not KEY_RE.fullmatch(key):
            raise MediaError('Invalid storage key.')
        target = self.root / key
        if not target.resolve().is_relative_to(self.root):
            raise MediaError('Path escapes storage root.')
        current = target
        while current != self.root:
            if current.is_symlink():
                raise MediaError('Symlinks are prohibited inside CAS.')
            current = current.parent
        return target

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def put(self, payload: bytes, *, prefix: str, extension: str, mime_type: str) -> StoredBlob:
        if not payload:
            raise MediaError('Empty object.')
        key, checksum = object_key(payload, prefix, extension)
        target = self._path(key)
        if target.exists():
            verify_blob(key, target.read_bytes())
            return StoredBlob('cas:///' + key, checksum, len(payload))
        # Serialize local space reservation across workers on this VM.
        import fcntl
        lock_path = self.root / '.write.lock'
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, 'a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if shutil.disk_usage(self.root).free - len(payload) < self.min_free_bytes:
                raise MediaError('Storage reserve reached. Stop ingestion; do not evict authoritative originals.')
            target.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            self._path(key)
            temporary: Path | None = None
            try:
                fd, name = tempfile.mkstemp(prefix='.upload-', dir=target.parent)
                temporary = Path(name)
                with os.fdopen(fd, 'wb') as output:
                    output.write(payload)
                    output.flush()
                    os.fchmod(output.fileno(), 0o640)
                    os.fsync(output.fileno())
                try:
                    # link() publishes atomically without replacing an existing CAS object.
                    os.link(temporary, target)
                except FileExistsError:
                    verify_blob(key, target.read_bytes())
                current = target.parent
                while True:
                    self._fsync_directory(current)
                    if current == self.root:
                        break
                    current = current.parent
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return StoredBlob('cas:///' + key, checksum, len(payload))

    def read(self, uri: str, *, max_bytes: int) -> bytes:
        if not uri.startswith('cas:///'):
            raise MediaError('CAS URI required.')
        key = uri[7:]
        path = self._path(key)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as source:
            payload = source.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise MediaError('Stored object exceeds read limit.')
        return verify_blob(key, payload)


class S3CAS:
    def __init__(self, settings: Settings):
        import boto3
        from botocore.config import Config
        self.bucket = settings.s3_bucket
        if not self.bucket:
            raise MediaError('Missing S3 bucket.')
        kwargs = {}
        if settings.s3_access_key_id:
            kwargs['aws_access_key_id'] = settings.s3_access_key_id.get_secret_value()
        if settings.s3_secret_access_key:
            kwargs['aws_secret_access_key'] = settings.s3_secret_access_key.get_secret_value()
        self.client = boto3.client(
            's3', endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region,
            config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=60,
                          retries={'max_attempts': 3, 'mode': 'standard'},
                          request_checksum_calculation='when_required', response_checksum_validation='when_required'),
            **kwargs,
        )

    def put(self, payload: bytes, *, prefix: str, extension: str, mime_type: str) -> StoredBlob:
        from botocore.exceptions import ClientError
        if not payload:
            raise MediaError('Empty object.')
        key, checksum = object_key(payload, prefix, extension)
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=payload, ContentType=mime_type,
                                   IfNoneMatch='*', Metadata={'sha256': checksum}, CacheControl='private, no-store')
        except ClientError as error:
            if error.response['ResponseMetadata']['HTTPStatusCode'] != 412:
                raise
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            if head.get('Metadata', {}).get('sha256') != checksum or head['ContentLength'] != len(payload):
                raise MediaError('Existing S3 object metadata mismatch.') from error
        return StoredBlob(f's3://{self.bucket}/{key}', checksum, len(payload))

    def read(self, uri: str, *, max_bytes: int) -> bytes:
        parsed = urlparse(uri)
        key = parsed.path.lstrip('/')
        if parsed.scheme != 's3' or parsed.netloc != self.bucket or not KEY_RE.fullmatch(key):
            raise MediaError('Invalid S3 URI/bucket/key.')
        result = self.client.get_object(Bucket=self.bucket, Key=key)
        body = result['Body']
        try:
            if result['ContentLength'] > max_bytes:
                raise MediaError('Stored object exceeds read limit.')
            payload = body.read(max_bytes + 1)
        finally:
            body.close()
        if len(payload) > max_bytes:
            raise MediaError('Stored object exceeds read limit.')
        return verify_blob(key, payload)


def make_blob_store(settings: Settings) -> BlobStore:
    if settings.media_backend == 's3':
        return S3CAS(settings)
    return LocalCAS(settings.media_storage_path, min_free_bytes=settings.media_min_free_bytes)


@dataclass(frozen=True)
class ImageAsset:
    id: str
    original_sha256: str
    transform_profile: str
    original_uri: str
    storage_uri: str
    thumbnail_uri: str
    image_sha256: str
    thumbnail_sha256: str
    mime_type: str
    file_size: int
    original_size: int
    thumbnail_size: int
    width: int
    height: int

    def as_dict(self) -> dict:
        return asdict(self)


class ImageStorageManager:
    def __init__(self, store: BlobStore, *, max_bytes: int = 25 * 1024**2,
                 max_pixels: int = 40_000_000, max_dimension: int = 2560):
        self.store, self.max_bytes, self.max_pixels, self.max_dimension = store, max_bytes, max_pixels, max_dimension
        self._decode_slots = threading.BoundedSemaphore(2)
        self.profile = f'webp-v1-q80-thumb256-pad-max{max_dimension}-pillow{PILLOW_VERSION}-webp{features.version("webp")}'

    def from_stream(self, source: BinaryIO) -> ImageAsset:
        chunks, total = [], 0
        while True:
            chunk = source.read(min(64 * 1024, self.max_bytes - total + 1))
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise MediaError('A binary stream is required.')
            total += len(chunk)
            if total > self.max_bytes:
                raise MediaError('Image exceeds byte limit.')
            chunks.append(chunk)
        return self.from_bytes(b''.join(chunks))

    def from_bytes(self, payload: bytes) -> ImageAsset:
        with self._decode_slots:
            return self._from_bytes(payload)

    def _from_bytes(self, payload: bytes) -> ImageAsset:
        if not payload or len(payload) > self.max_bytes:
            raise MediaError('Image is empty or exceeds byte limit.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(payload)) as probe:
                    if probe.format not in {'JPEG', 'PNG', 'WEBP'}:
                        raise MediaError('Only decoded JPEG, PNG and WebP are supported; never trust extension/MIME alone.')
                    if getattr(probe, 'n_frames', 1) != 1:
                        raise MediaError('Animated/multipage images require explicit curation.')
                    if probe.width * probe.height > self.max_pixels:
                        raise MediaError('Image exceeds decoded pixel limit.')
                    probe.verify()
                with Image.open(io.BytesIO(payload)) as original:
                    oriented = ImageOps.exif_transpose(original)
                    mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
                    clean = oriented.convert(mode)
                    clean.info.clear()  # Remove EXIF/GPS/comments/ICC/XMP from served derivatives.
                    clean.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)
                    width, height = clean.size
                    main = io.BytesIO()
                    clean.save(main, format='WEBP', quality=80, method=6, exif=b'', icc_profile=b'', xmp=b'')
                    thumbnail = ImageOps.pad(clean, (256, 256), method=Image.Resampling.LANCZOS,
                                             color=(255, 255, 255, 0) if mode == 'RGBA' else (255, 255, 255))
                    small = io.BytesIO()
                    thumbnail.save(small, format='WEBP', quality=80, method=6, exif=b'', icc_profile=b'', xmp=b'')
        except MediaError:
            raise
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise MediaError('Unsafe, corrupt, or unsupported image.') from error
        # Originals are evidence; never overwrite them with lossy WebP or serve them publicly.
        raw = self.store.put(payload, prefix='originals', extension='bin', mime_type='application/octet-stream')
        image = self.store.put(main.getvalue(), prefix='images', extension='webp', mime_type='image/webp')
        thumb = self.store.put(small.getvalue(), prefix='thumbs', extension='webp', mime_type='image/webp')
        return ImageAsset(id=digest_json([raw.sha256, self.profile]), original_sha256=raw.sha256,
                          transform_profile=self.profile, original_uri=raw.uri, storage_uri=image.uri,
                          thumbnail_uri=thumb.uri, image_sha256=image.sha256, thumbnail_sha256=thumb.sha256,
                          mime_type='image/webp', file_size=image.size, original_size=raw.size,
                          thumbnail_size=thumb.size, width=width, height=height)

    def from_drive(self, file_id: str, *, credentials) -> ImageAsset:
        """Authorized, bounded download from a fixed Google endpoint, not an arbitrary URL."""
        from google.auth.transport.requests import AuthorizedSession
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', file_id):
            raise MediaError('Invalid Google Drive file ID.')
        deadline = time.monotonic() + 120
        with AuthorizedSession(credentials) as client:
            with client.get(f'https://www.googleapis.com/drive/v3/files/{file_id}',
                            params={'alt': 'media', 'supportsAllDrives': 'true'}, stream=True,
                            timeout=(5, 60), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise MediaError(f'Drive download failed (HTTP {response.status_code}).')
                if int(response.headers.get('Content-Length', '0')) > self.max_bytes:
                    raise MediaError('Drive image exceeds byte limit.')
                data = io.BytesIO()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if data.tell() + len(chunk) > self.max_bytes or time.monotonic() > deadline:
                        raise MediaError('Drive image byte/time budget exceeded.')
                    data.write(chunk)
        return self.from_bytes(data.getvalue())
