"""Investigation tests for Temuan 5: AttributeCatalog persistence across process restarts.

Verifies:
- AttributeCatalog is constructed in memory from template_kanonik.xlsx seed.
- When an attribute is registered or approved during runtime review, it does NOT survive
  a simulated process restart / re-instantiation of AttributeCatalog.
- Confirms the architectural gap that necessitates a persistent catalog storage schema in DB.
"""

from __future__ import annotations

import uuid
from src.storage.attribute_policy import AttributeCatalog, AttributeDefinition


def test_approved_new_attribute_does_not_persist_across_restarts():
    """Temuan 5: After curator approves NEW_ATTRIBUTE review, definition does NOT survive catalog re-instantiation.

    Proves the finding: AttributeCatalog is purely in-memory and reloads from template_kanonik.xlsx seed.
    Approving a review item in draft does not persist the attribute definition to any durable database table.
    """
    novel_label = f"Kadar Capsaicin Buah Segar ({uuid.uuid4().hex[:6]})"

    # Step 1: In a running process, catalog does not have the novel attribute
    process1_catalog = AttributeCatalog()
    assert process1_catalog.lookup(novel_label) is None

    # Step 2: Curator registers it in-memory in process 1
    new_defn = AttributeDefinition(
        attribute_id="attr_kadar_capsaicin_novel",
        canonical_key="kadar_capsaicin_novel",
        label=novel_label,
        organ="buah",
        value_type="number",
        unit="ppm",
    )
    process1_catalog.register_attribute(new_defn)
    assert process1_catalog.lookup(novel_label) is not None

    # Step 3: Simulate process restart / fresh request in another worker process
    process2_catalog = AttributeCatalog()

    # EVIDENCE FOR FINDING 5: The novel attribute definition is completely lost after restart!
    assert process2_catalog.lookup(novel_label) is None, (
        "Proof of Finding 5: AttributeCatalog re-initializes from template seed and does not persist novel attributes."
    )
