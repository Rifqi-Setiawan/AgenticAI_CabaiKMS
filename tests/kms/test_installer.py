import ast
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'install_into_repo.py'
# Installed overlay tests do not copy the installer; test it from the extracted package.
if not PATH.exists():
    pytest.skip('Installer tests run from the extracted enhancement package.', allow_module_level=True)
spec = importlib.util.spec_from_file_location('kms_installer', PATH)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_patch_app_is_idempotent():
    source = 'from src.ui.pipeline_runner import run_pipeline_ui\nresult = run_pipeline_ui(\n    tmp_path,\n    source_format="x",\n)\n'
    patched = installer.patch_app(source)
    ast.parse(patched)
    assert 'kms_source_filename=uploaded_file.name' in patched
    assert installer.patch_app(patched) == patched


def test_unknown_upstream_fails_closed():
    with pytest.raises(ValueError):
        installer.patch_app('print("other application")\n')


def test_graph_hook_parses_and_reuses_original():
    original = 'def vision_classification(state, config):\n    return {}\n'
    patched = installer.patch_graph(original)
    ast.parse(patched)
    assert 'if enabled():' in patched
    assert patched.endswith('    return {}\n')
