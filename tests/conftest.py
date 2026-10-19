import os
import pytest


@pytest.fixture(autouse=True)
def default_test_env(monkeypatch):
  """Ensure unit tests do not attempt external KMS network calls unless explicitly enabled.

  KMS integration tests configure their own client/settings fixtures.
  """
  if not os.getenv("KMS_TEST_RUN"):
    monkeypatch.setenv("KMS_ENABLED", "false")
