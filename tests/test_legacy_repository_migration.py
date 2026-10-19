import pytest
from legacy_repository_migration import migrate_one, FAMILIES

def test_rejects_unknown_family_before_storage():
    with pytest.raises(ValueError, match="Unsupported"):
        migrate_one("trades")

def test_all_supported_families_have_id_columns():
    assert len(FAMILIES) == 7
    assert all(field.endswith("_id") for field in FAMILIES.values())
