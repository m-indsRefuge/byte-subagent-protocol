from dataclasses import FrozenInstanceError

import pytest

from bsap.models import Budget, ContextManifest, PermissionSet


def test_budget_is_immutable() -> None:
    budget = Budget(max_steps=25, max_tool_calls=20)
    with pytest.raises(FrozenInstanceError):
        budget.max_steps = 30  # type: ignore[misc]


def test_permissions_are_immutable() -> None:
    permissions = PermissionSet(filesystem_read=True, tests_run=True)
    with pytest.raises(FrozenInstanceError):
        permissions.filesystem_write = True  # type: ignore[misc]


def test_context_manifest_uses_immutable_sequences() -> None:
    manifest = ContextManifest(files=("settings.py",))
    assert isinstance(manifest.files, tuple)

from bsap.canonical import canonical_json, sha256_hex
from bsap.models import LifecycleState


def test_hash_ignores_mapping_key_order() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}
    assert sha256_hex(left) == sha256_hex(right)


def test_hash_preserves_sequence_order() -> None:
    assert sha256_hex(("a", "b")) != sha256_hex(("b", "a"))


def test_enum_serializes_as_protocol_string() -> None:
    assert canonical_json(LifecycleState.RUNNING) == '"RUNNING"'


def test_context_hash_changes_when_one_filename_changes() -> None:
    first = ContextManifest(files=("settings.py",))
    second = ContextManifest(files=("settingx.py",))
    assert sha256_hex(first) != sha256_hex(second)
