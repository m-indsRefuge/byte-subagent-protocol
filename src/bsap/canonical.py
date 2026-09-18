from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum


def to_canonical_data(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_canonical_data(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_canonical_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_canonical_data(item) for item in value]
    raise TypeError(f"Unsupported canonical type: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(
        to_canonical_data(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
