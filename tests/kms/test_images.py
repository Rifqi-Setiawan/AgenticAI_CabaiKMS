import io
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from src.storage.image_storage import ImageStorageManager, LocalCAS, MediaError


def manager(tmp_path):
    return ImageStorageManager(LocalCAS(tmp_path, min_free_bytes=0))


def test_webp_and_thumbnail(tmp_path, png_bytes):
    service = manager(tmp_path)
    asset = service.from_bytes(png_bytes)
    assert asset.original_sha256 == hashlib.sha256(png_bytes).hexdigest()
    assert service.store.read(asset.original_uri, max_bytes=100000) == png_bytes
    with Image.open(io.BytesIO(service.store.read(asset.storage_uri, max_bytes=100000))) as image:
        assert image.format == 'WEBP'
        assert image.size == (600, 300)
    with Image.open(io.BytesIO(service.store.read(asset.thumbnail_uri, max_bytes=100000))) as thumbnail:
        assert thumbnail.size == (256, 256)


def test_dedup_under_concurrent_puts(tmp_path, png_bytes):
    service = manager(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assets = list(pool.map(service.from_bytes, [png_bytes]*8))
    assert len({asset.id for asset in assets}) == 1
    assert len(list(tmp_path.rglob('*.webp'))) == 2
    assert len(list(tmp_path.rglob('*.bin'))) == 1


def test_partial_stream(tmp_path, png_bytes):
    class PartialReader(io.BytesIO):
        def read(self, amount=-1):
            return super().read(min(13, amount))
    assert manager(tmp_path).from_stream(PartialReader(png_bytes)).original_sha256 == hashlib.sha256(png_bytes).hexdigest()


def test_metadata_removed(tmp_path):
    payload = io.BytesIO()
    image = Image.new('RGB', (100, 200))
    exif = Image.Exif()
    exif[270] = 'secret farm location'
    exif[274] = 6
    image.save(payload, format='JPEG', exif=exif)
    service = manager(tmp_path)
    asset = service.from_bytes(payload.getvalue())
    with Image.open(io.BytesIO(service.store.read(asset.storage_uri, max_bytes=100000))) as output:
        assert output.size == (200, 100)
        assert not output.getexif()
        assert b'secret farm location' not in service.store.read(asset.storage_uri, max_bytes=100000)


@pytest.mark.parametrize('payload', [b'', b'not-an-image', b'<svg/>', b'GIF89a'])
def test_invalid_decoders(tmp_path, payload):
    with pytest.raises(MediaError):
        manager(tmp_path).from_bytes(payload)


def test_budget_limits(tmp_path, png_bytes):
    with pytest.raises(MediaError):
        ImageStorageManager(LocalCAS(tmp_path, min_free_bytes=0), max_pixels=1000).from_bytes(png_bytes)
    with pytest.raises(MediaError):
        ImageStorageManager(LocalCAS(tmp_path, min_free_bytes=0), max_bytes=100).from_stream(io.BytesIO(png_bytes))


def test_disk_reserve(tmp_path, png_bytes):
    with pytest.raises(MediaError):
        ImageStorageManager(LocalCAS(tmp_path, min_free_bytes=10**30)).from_bytes(png_bytes)


def test_uri_traversal(tmp_path):
    with pytest.raises(MediaError):
        LocalCAS(tmp_path, min_free_bytes=0).read('cas:///../../etc/passwd', max_bytes=100)


def test_symlink_refused(tmp_path, png_bytes):
    other = tmp_path / 'outside'
    other.mkdir()
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'images').symlink_to(other, target_is_directory=True)
    with pytest.raises(MediaError):
        manager(root).from_bytes(png_bytes)


def test_corrupted_existing_blob_detected(tmp_path, png_bytes):
    service = manager(tmp_path)
    asset = service.from_bytes(png_bytes)
    filename = tmp_path / asset.storage_uri.removeprefix('cas:///')
    filename.write_bytes(b'corrupt')
    with pytest.raises(MediaError):
        service.store.read(asset.storage_uri, max_bytes=100000)
