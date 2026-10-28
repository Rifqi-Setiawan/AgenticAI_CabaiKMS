from __future__ import annotations

import pytest

from scripts.ninerouter_preflight import run_preflight


@pytest.mark.ninerouter_live
def test_local_ninerouter_text_and_vision_capabilities():
    assert run_preflight()
