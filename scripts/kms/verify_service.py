#!/usr/bin/env python3
"""Verify archive/media against a live API. Never invent or commit canonical research values."""
import argparse
import hashlib
import io
import os
from pathlib import Path
import sys
for candidate in Path(__file__).resolve().parents:
    if (candidate / 'src' / 'storage').is_dir() and (candidate / 'schema.sql').is_file():
        sys.path.insert(0, str(candidate))
        break

from dotenv import dotenv_values
from PIL import Image

from src.integrations.client import KmsClient
from src.storage.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, default=Path('/etc/cabai-kms/ui.env'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--image', type=Path)
    args = parser.parse_args()
    for name, value in dotenv_values(args.env_file).items():
        if value is not None:
            os.environ[name] = value
    client = KmsClient(Settings(_env_file=None))
    assert client.request('GET', '/healthz')['status'] == 'alive'
    ready = client.request('GET', '/readyz')
    assert ready.get('writable', True)
    original = args.source.read_bytes()
    source = client.source(original)
    recovered = client.request('GET', '/sources/' + source['sha256'])
    assert original == recovered
    assert source['sha256'] == hashlib.sha256(original).hexdigest()
    result = {'source_archive_roundtrip': True, 'canonical_values_written': 0}
    if args.image:
        raw = args.image.read_bytes()
        one = client.request('POST', '/assets', content=raw)
        two = client.request('POST', '/assets', content=raw)
        assert one['id'] == two['id']
        thumbnail = client.request('GET', '/media/' + one['id'] + '/thumbnail')
        with Image.open(io.BytesIO(thumbnail)) as image:
            assert image.size == (256, 256) and image.format == 'WEBP'
            assert not image.getexif()
        result['image_dedup_thumbnail'] = True
    print(result)


if __name__ == '__main__':
    main()
