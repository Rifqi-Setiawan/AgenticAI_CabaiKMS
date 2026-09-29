# Validation report - v1.0.0-rc1

## Executed checks

Validation date: 29 September 2026. Execution environment: Linux, Python 3.13.5.

| Check | Actual result |
|---|---|
| Python compileall: src, scripts, tests | PASS |
| pytest, complete collected enhancement suite | **53 passed, 10 skipped** |
| PostgreSQL integration tests | **NOT EXECUTED**: no disposable PostgreSQL / TEST_DATABASE_URL |
| S3 SDK contract tests | PASS using botocore Stubber, not a live cloud bucket |
| Full additive installer dry run | PASS: no target file mutation |
| Full additive installer apply | PASS on a synthetic Git working tree with observed upstream anchors |
| Second installer apply | PASS: zero changed files |
| Existing README, .env and catalog overrides | Preserved in the synthetic fixture |
| Target Python syntax after installer apply | PASS |
| Unfinished-code scan of implementation | No TODO, FIXME or NotImplementedError found |

The test run completed in 3.47 seconds. This is local test execution duration, not a prediction of VPS ingestion throughput.

## Evidence files

`docs/qa/pytest.xml` contains the collected test report; `docs/qa/pytest.log` contains its console summary. `docs/qa/installer.json` records the synthetic installer checks. No customer dataset or real credentials were used.

## Executed dependency versions

- `SQLAlchemy==2.0.50`
- `fastapi==0.128.2`
- `pydantic==2.13.4`
- `pydantic-settings==2.14.1`
- `Pillow==12.3.0`
- `httpx==0.28.1`
- `boto3==1.43.18`
- `python-dotenv==1.2.2`
- `uvicorn==0.48.0`
- `pytest==9.0.2`
- `pandas==2.2.3`

psycopg and google-auth versions in requirements are selected dependency pins, not locally executed drivers. Existing Streamlit, LangGraph, Instructor, model gateway and repository dependencies must be resolved together in an isolated VPS environment. Direct pins are not a transitive hash lock.

## What these results do not establish

There is no live PostgreSQL server or psycopg driver in this execution environment. SQL constraints, migrations, trigger syntax/runtime, least-privilege grants, true concurrent commits and transactional rollback require the included real PostgreSQL tests. SQLite was not substituted. The API tests inject an in-memory repository for transport/authentication contracts; they are not database durability tests.

There is no live Drive, R2/S3 credential, VPS connection, Caddy/systemd service or full upstream checkout. Actual cloud policy/conditional PUT support, image inference stability, original pipeline review replay, UI behavior and end-to-end model output have not been validated here. Public source inspection is file-level, not a complete clone pinned to a single Git commit. The installer fixture is synthetic and only exercises the patch contract and preservation/idempotency behavior.

## Mandatory release gates

1. Record and inspect the real target Git commit; review the installer plan and diff without replacing model/provider settings.
2. Resolve dependencies and run the upstream regression suite plus enhancement tests in an isolated environment.
3. Execute all PostgreSQL integration tests on a disposable database; run readiness against the actual non-owner production app role.
4. Test private source/media upload, duplicate processing, source/archive integrity, review recovery, commit retry and stale/concurrent commit behavior using approved real research fixtures.
5. Validate thumbnail/vision transformations against accepted labels; test live Drive and private bucket access boundaries.
6. Prove backup and restore on persistent disks and off-host storage. Set explicit RPO/RTO, retention and operational alerting.
7. Activate KMS only after all relevant gates pass. No production certification or absolute zero-loss/zero-leak guarantee is implied.
