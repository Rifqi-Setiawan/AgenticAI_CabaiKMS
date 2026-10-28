
import asyncio
import hmac
import io
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.storage.config import Settings, get_settings
from src.storage.contracts import CommitRequest, PromoteAliasRequest, RebaseRequest, StageRequest
from src.storage.db import make_engine, preflight
from src.storage.document_contracts import StageV2Request
from src.storage.document_repository import DocumentRepository
from src.storage.errors import Conflict, InvalidState, KmsError, NotFound
from src.storage.image_storage import ImageStorageManager, MediaError, make_blob_store
from src.storage.learning import LearningRepository
from src.storage.repository import KmsRepository


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


class BoundedBodyMiddleware:
    """Bound body allocation before JSON/image parsing, including chunked requests."""
    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            advertised = int(headers.get(b'content-length', b'0'))
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        if advertised > self.limit:
            return await JSONResponse({'detail': 'Request too large.'}, status_code=413)(scope, receive, send)
        chunks, length = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            length += len(message.get('body', b''))
            if length > self.limit:
                return await JSONResponse({'detail': 'Request too large.'}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body', False):
                break
        iterator = iter(chunks)
        async def replay():
            return next(iterator, {'type': 'http.request', 'body': b'', 'more_body': False})
        return await self.app(scope, replay, send)


def validate_xlsx(payload: bytes, limit: int) -> None:
    if not payload or len(payload) > limit:
        raise InvalidState('Source is empty or exceeds the upload limit.')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            items = archive.infolist()
            if len(items) > 10000 or sum(item.file_size for item in items) > 500 * 1024**2:
                raise InvalidState('Workbook expansion budget exceeded.')
            names = set(archive.namelist())
            if 'xl/workbook.xml' not in names or '[Content_Types].xml' not in names:
                raise InvalidState('A real .xlsx workbook is required.')
            if any('vbaProject' in name for name in names):
                raise InvalidState('Macro-enabled workbooks are not accepted.')
    except zipfile.BadZipFile as error:
        raise InvalidState('Invalid .xlsx archive.') from error


def _unwrap_decision(body: dict[str, Any]) -> dict[str, Any]:
    if not body or not isinstance(body, dict):
        raise HTTPException(422, "Decision body must be a non-empty object.")
    if "decision" in body:
        if len(body) != 1 or not isinstance(body["decision"], dict) or not body["decision"]:
            raise HTTPException(422, "Malformed decision payload.")
        return body["decision"]
    return body


def create_app(
    settings: Settings | None = None,
    repository=None,
    blob_store=None,
    document_repository: DocumentRepository | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    principals = settings.principals()
    injected = repository is not None
    engine = None if injected else make_engine(settings)
    repo = repository or KmsRepository(engine, allow_legacy_sourceless_runs=settings.allow_legacy_sourceless_runs)
    store = blob_store or make_blob_store(settings)
    images = ImageStorageManager(store, max_bytes=settings.media_max_bytes, max_pixels=settings.media_max_pixels)

    doc_engine = getattr(repo, "engine", None) or engine
    doc_repo = document_repository or (DocumentRepository(doc_engine) if doc_engine is not None else None)

    @asynccontextmanager
    async def lifespan(app):
        if not injected:
            if settings.db_auto_migrate:
                from src.storage.migrate import migrate
                await asyncio.to_thread(migrate, settings.database_admin_url.get_secret_value())
            report = await asyncio.to_thread(preflight, engine)
            if report['privileged_runtime_role']:
                raise RuntimeError('Refusing privileged DATABASE_URL. Use the least-privilege app role.')
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(title='CABAI-KMS Core', version='1.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BoundedBodyMiddleware, limit=settings.api_max_body_bytes)
    security = HTTPBearer(auto_error=False)

    def authenticate(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]) -> Principal:
        if credentials is None:
            raise HTTPException(401, 'Bearer token required.', headers={'WWW-Authenticate': 'Bearer'})
        found = None
        for token, data in principals.items():
            if hmac.compare_digest(credentials.credentials.encode(), token.encode()):
                found = Principal(subject=data['subject'], role=data['role'])
        if found is None:
            raise HTTPException(401, 'Invalid token.', headers={'WWW-Authenticate': 'Bearer'})
        return found

    def writer(principal: Annotated[Principal, Depends(authenticate)]) -> Principal:
        if principal.role not in {'reviewer', 'curator'}:
            raise HTTPException(403, 'Reviewer role required.')
        return principal

    def curator(principal: Annotated[Principal, Depends(authenticate)]) -> Principal:
        if principal.role != 'curator':
            raise HTTPException(403, 'Curator role required.')
        return principal

    @app.exception_handler(KmsError)
    async def kms_error(request, error):
        code = 409 if isinstance(error, Conflict) else 404 if isinstance(error, NotFound) else 422
        return JSONResponse({'detail': str(error)}, status_code=code)

    @app.exception_handler(MediaError)
    async def media_error(request, error):
        return JSONResponse({'detail': str(error)}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        # Do not log repr(error), SQL parameters, DSNs, tokens, or spreadsheet values.
        return JSONResponse({'detail': 'Database operation failed. No successful commit was acknowledged.'}, status_code=503)

    @app.get('/livez')
    @app.get('/healthz')
    def livez():
        return {'status': 'alive'}

    @app.get('/readyz')
    def ready(principal: Annotated[Principal, Depends(authenticate)]):
        import hashlib
        import logging
        from src.storage.migrate import MIGRATIONS

        logger = logging.getLogger("kms_api.readyz")
        required_tables = [
            "kms.acquisition_runs",
            "kms.source_artifacts",
            "kms.knowledge_documents",
            "kms.document_attribute_changes",
        ]
        target_engine = doc_repo.engine if doc_repo is not None else engine
        if target_engine is None:
            return JSONResponse({'status': 'not_ready', 'error': 'Database engine not initialized'}, status_code=503)
        try:
            with target_engine.connect() as conn:
                missing_tables = []
                for tbl in required_tables:
                    exists = conn.scalar(text(f"SELECT to_regclass('{tbl}') IS NOT NULL"))
                    if not exists:
                        missing_tables.append(tbl)
                if missing_tables:
                    return JSONResponse({'status': 'not_ready', 'missing_tables': missing_tables}, status_code=503)

                db_rows = conn.execute(
                    text("SELECT version, sha256 FROM kms.schema_migrations")
                ).mappings().all()
                db_migrations = {r["version"]: r["sha256"] for r in db_rows}

                missing_migrations = []
                checksum_mismatch = []
                for version, path in MIGRATIONS:
                    if version not in db_migrations:
                        missing_migrations.append(version)
                    else:
                        file_sha = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
                        if db_migrations[version] != file_sha:
                            checksum_mismatch.append(version)

                if missing_migrations:
                    return JSONResponse({'status': 'not_ready', 'missing_migrations': missing_migrations}, status_code=503)
                if checksum_mismatch:
                    return JSONResponse({'status': 'not_ready', 'checksum_mismatch': checksum_mismatch}, status_code=503)

            return {'status': 'ready'}
        except Exception as e:
            logger.error("Readiness check database failure: %s", type(e).__name__)
            return JSONResponse({'status': 'not_ready', 'error': 'Database check failed'}, status_code=503)

    @app.post('/runs/stage')
    def stage(request: StageRequest, principal: Annotated[Principal, Depends(writer)]):
        return repo.stage(request.draft, expected_revision=request.expected_revision, actor=principal.subject)

    @app.get('/runs/{run_id}')
    def get_run(run_id: str, principal: Annotated[Principal, Depends(authenticate)]):
        return repo.get_run(run_id)

    @app.post('/runs/{run_id}/commit')
    def commit(run_id: str, request: CommitRequest, principal: Annotated[Principal, Depends(writer)]):
        return repo.commit(run_id, request.expected_revision, request.payload_sha256, actor=principal.subject)

    @app.post('/runs/{run_id}/rebase')
    def rebase(run_id: str, request: RebaseRequest, principal: Annotated[Principal, Depends(curator)]):
        return repo.rebase(run_id, request.expected_revision, request.reason, actor=principal.subject)

    @app.post('/runs/v2/stage')
    def stage_v2(request: StageV2Request, principal: Annotated[Principal, Depends(writer)]):
        if doc_repo is None:
            raise InvalidState('Document endpoints require a database.')
        return doc_repo.stage(request.draft, expected_revision=request.expected_revision, actor=principal.subject)

    @app.get('/runs/v2/{run_id}')
    def get_run_v2(run_id: str, principal: Annotated[Principal, Depends(authenticate)]):
        if doc_repo is None:
            raise InvalidState('Document endpoints require a database.')
        return doc_repo.get_run(run_id)

    @app.post('/runs/v2/{run_id}/commit')
    def commit_v2(run_id: str, request: CommitRequest, principal: Annotated[Principal, Depends(writer)]):
        if doc_repo is None:
            raise InvalidState('Document endpoints require a database.')
        return doc_repo.commit(run_id, request.expected_revision, request.payload_sha256, actor=principal.subject)

    @app.post('/runs/v2/{run_id}/reviews/{item_id}/resolve')
    def resolve_review_v2(run_id: str, item_id: str, decision: dict[str, Any], principal: Annotated[Principal, Depends(writer)]):
        if doc_repo is None:
            raise InvalidState('Document endpoints require a database.')
        unwrapped = _unwrap_decision(decision)
        return doc_repo.resolve_review(run_id, item_id, unwrapped, actor=principal.subject, actor_role=principal.role)

    @app.get('/documents')
    def list_documents(
        principal: Annotated[Principal, Depends(authenticate)],
        variety_id: str | None = None,
        habitat_id: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ):
        if doc_repo is None:
            raise InvalidState('Document endpoints require a database.')
        return {'items': doc_repo.list_documents(variety_id=variety_id, habitat_id=habitat_id, limit=limit, offset=offset)}

    @app.get('/documents/{doc_id}')
    def get_document(doc_id: str, principal: Annotated[Principal, Depends(authenticate)]):
        if doc_repo is None:
            raise InvalidState('Document endpoints require a database.')
        doc = doc_repo.get_document(doc_id)
        if doc is None:
            raise NotFound(f'Document {doc_id} not found.')
        return doc

    @app.get('/values')
    def values(principal: Annotated[Principal, Depends(authenticate)], limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return {'items': repo.inspect_values(limit=limit, offset=offset)}

    @app.post('/sources')
    async def source(request: Request, principal: Annotated[Principal, Depends(writer)]):
        data = await request.body()
        def save():
            validate_xlsx(data, settings.source_max_bytes)
            blob = store.put(data, prefix='sources', extension='xlsx', mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            return repo.register_source(blob.sha256, blob.uri, blob.size, actor=principal.subject)
        return await asyncio.to_thread(save)

    @app.get('/sources/{sha256}')
    def source_read(sha256: str, principal: Annotated[Principal, Depends(authenticate)]):
        source = repo.get_source(sha256)
        payload = store.read(source['storage_uri'], max_bytes=settings.source_max_bytes)
        return Response(payload, media_type='application/octet-stream',
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.post('/assets')
    async def asset(request: Request, principal: Annotated[Principal, Depends(writer)]):
        data = await request.body()
        def save():
            return repo.register_asset(images.from_bytes(data).as_dict(), actor=principal.subject)
        return await asyncio.to_thread(save)

    @app.post('/assets/drive/{file_id}')
    def drive_asset(file_id: str, principal: Annotated[Principal, Depends(writer)]):
        if settings.google_drive_credentials_path is None:
            raise InvalidState('Drive service account is not configured.')
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            str(settings.google_drive_credentials_path), scopes=['https://www.googleapis.com/auth/drive.readonly'])
        return repo.register_asset(images.from_drive(file_id, credentials=credentials).as_dict(), actor=principal.subject)

    @app.get('/media/{asset_id}/{variant}')
    def media(asset_id: str, variant: Literal['image','thumbnail'], principal: Annotated[Principal, Depends(authenticate)]):
        asset = repo.get_asset(asset_id)
        uri = asset['storage_uri'] if variant == 'image' else asset['thumbnail_uri']
        payload = store.read(uri, max_bytes=settings.media_max_bytes * 2)
        return Response(payload, media_type='image/webp', headers={'Cache-Control': 'private, no-store',
                        'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})

    @app.post('/aliases/promote')
    def promote(request: PromoteAliasRequest, principal: Annotated[Principal, Depends(curator)]):
        if engine is None:
            raise InvalidState('Learning endpoints require a database.')
        try:
            gold_id = UUID(request.gold_id)
        except ValueError as error:
            raise InvalidState('Invalid gold ID.') from error
        return {'alias_id': LearningRepository(engine).promote(gold_id, request.evaluation_reference, request.reason, actor=principal.subject)}

    return app
