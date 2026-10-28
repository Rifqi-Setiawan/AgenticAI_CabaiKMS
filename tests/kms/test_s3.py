import io
import hashlib
from types import SimpleNamespace

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from src.storage.image_storage import S3CAS, MediaError, object_key


def store():
    instance = object.__new__(S3CAS)
    instance.bucket = 'test-private'
    instance.client = boto3.client('s3', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test')
    return instance


def test_conditional_put_uses_immutable_key():
    service = store()
    payload = b'example'
    key, digest = object_key(payload, 'originals', 'bin')
    with Stubber(service.client) as stub:
        stub.add_response('put_object', {}, {'Bucket': 'test-private', 'Key': key, 'Body': payload,
            'ContentType': 'application/octet-stream', 'IfNoneMatch': '*', 'Metadata': {'sha256': digest}, 'CacheControl': 'private, no-store'})
        assert service.put(payload, prefix='originals', extension='bin', mime_type='application/octet-stream').sha256 == digest


def test_duplicate_checks_metadata():
    service = store()
    payload = b'example'
    key, digest = object_key(payload, 'originals', 'bin')
    with Stubber(service.client) as stub:
        stub.add_client_error('put_object', service_error_code='PreconditionFailed', http_status_code=412)
        stub.add_response('head_object', {'Metadata': {'sha256': digest}, 'ContentLength': len(payload)}, {'Bucket': 'test-private', 'Key': key})
        assert service.put(payload, prefix='originals', extension='bin', mime_type='application/octet-stream').size == len(payload)


def test_read_verifies_checksum():
    service = store()
    key, digest = object_key(b'example', 'originals', 'bin')
    with Stubber(service.client) as stub:
        stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(b'corrupt'), 7), 'ContentLength': 7})
        with pytest.raises(MediaError):
            service.read('s3://test-private/' + key, max_bytes=100)
