from __future__ import annotations

import argparse
import hashlib
import hmac
import time
import uuid

import httpx
from sqlalchemy import text

from .config import get_settings
from .contracts import canonical_json
from .db import make_engine, transaction

CLAIM = '''WITH candidate AS (
 SELECT id FROM kms.outbox_events
 WHERE delivered_at IS NULL AND dead_letter_at IS NULL AND available_at<=now()
 AND (leased_until IS NULL OR leased_until<now())
 ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1
) UPDATE kms.outbox_events e SET lease_token=:token, leased_until=now()+interval '120 seconds',
 attempts=e.attempts+1 FROM candidate WHERE e.id=candidate.id RETURNING e.*'''


def deliver_one(engine, client: httpx.Client, url: str, secret: str) -> bool:
    token = uuid.uuid4()
    with transaction(engine) as session:
        row = session.execute(text(CLAIM), {'token': token}).mappings().first()
        event = dict(row) if row else None
    if event is None:
        return False
    body = canonical_json({'event_id': str(event['id']), 'type': event['event_type'], 'payload': event['payload']}).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    success, code = False, 'transport_error'
    try:
        response = client.post(url, content=body, headers={'Content-Type': 'application/json',
                               'Idempotency-Key': str(event['id']), 'X-KMS-Signature': signature}, timeout=30)
        success, code = 200 <= response.status_code < 300, f'http_{response.status_code}'
    except httpx.HTTPError:
        code = 'transport_error'
    with transaction(engine) as session:
        if success:
            session.execute(text('''UPDATE kms.outbox_events SET delivered_at=now(),lease_token=NULL,leased_until=NULL
              WHERE id=:i AND lease_token=:t'''), {'i': event['id'], 't': token})
        else:
            delay = min(3600, 2 ** min(event['attempts'], 11))
            session.execute(text('''UPDATE kms.outbox_events SET lease_token=NULL,leased_until=NULL,last_error_code=:e,
              available_at=now()+make_interval(secs=>:d),
              dead_letter_at=CASE WHEN attempts>=12 THEN now() ELSE NULL END
              WHERE id=:i AND lease_token=:t'''), {'i': event['id'], 't': token, 'e': code, 'd': delay})
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description='Deliver transactional outbox notifications (at least once).')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    settings = get_settings()
    if not settings.outbox_webhook_url or not settings.outbox_webhook_secret:
        raise SystemExit('Configure OUTBOX_WEBHOOK_URL and OUTBOX_WEBHOOK_SECRET; no external destination is assumed.')
    engine = make_engine(settings)
    try:
        with httpx.Client(follow_redirects=False) as client:
            while True:
                worked = deliver_one(engine, client, settings.outbox_webhook_url, settings.outbox_webhook_secret.get_secret_value())
                if args.once:
                    break
                if not worked:
                    time.sleep(2)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
