"""Stable ID generation and normalization for World Model."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


def normalize_name(name: str) -> str:
    """
    Normalize a name for stable ID generation.

    NFKD decomposition, strip combining marks, lowercase, collapse whitespace.
    """
    # NFKD decomposition
    nfkd = unicodedata.normalize("NFKD", name)
    # Strip combining marks
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase
    lower = stripped.lower()
    # Replace NBSP and other special spaces with regular space
    lower = lower.replace("\u00a0", " ")
    # Collapse whitespace
    collapsed = re.sub(r"\s+", " ", lower).strip()
    return collapsed


def entity_id_from_name(entity_type: str, name: str) -> str:
    """
    Generate a stable entity ID from type and normalized name.

    Format: ent_<sha256(type:normalized_name)[:16]>
    """
    normalized = normalize_name(name)
    content = f"{entity_type}:{normalized}"
    hash_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"ent_{hash_hex}"


def external_id(entity_type: str, system: str, external_id: str) -> str:
    """
    Generate a stable entity ID from an external system key.

    Format: ext_<sha256(type:system:external_id)[:16]>
    """
    content = f"{entity_type}:{system}:{external_id}"
    hash_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"ext_{hash_hex}"


def context_id_from_attrs(context_type: str, attrs: dict[str, Any], parent: str | None = None) -> str:
    """
    Generate a stable context ID from type and attributes.

    Format: ctx_<sha256(type:parent:attrs_json)[:16]>
    """
    import json
    # Sort keys for deterministic output
    attrs_json = json.dumps(attrs, sort_keys=True, separators=(",", ":"))
    parent_str = parent or ""
    content = f"{context_type}:{parent_str}:{attrs_json}"
    hash_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"ctx_{hash_hex}"


def fact_id(about: str, predicate: str, value: Any, at: str, kind: str, url: str | None = None) -> str:
    """
    Generate a stable fact ID.

    Format: fact_<sha256(about:predicate:value:at:kind:url)[:16]>
    """
    import json
    value_json = json.dumps(value, sort_keys=True, separators=(",", ":"))
    url_str = url or ""
    content = f"{about}:{predicate}:{value_json}:{at}:{kind}:{url_str}"
    hash_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"fact_{hash_hex}"


def relationship_id(
    from_: str,
    rel_type: str,
    to: str,
    context: str | None = None,
    valid_from: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> str:
    """
    Generate a stable relationship ID.

    Format: rel_<sha256(from:type:to:context:valid_from:attrs)[:16]>
    """
    import json
    context_str = context or ""
    valid_from_str = valid_from or ""
    attrs_json = json.dumps(attrs or {}, sort_keys=True, separators=(",", ":"))
    content = f"{from_}:{rel_type}:{to}:{context_str}:{valid_from_str}:{attrs_json}"
    hash_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"rel_{hash_hex}"


def sha256_hex(content: str, length: int = 16) -> str:
    """Generate a SHA256 hex digest of the given length."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:length]


def canonical_json(obj: Any) -> str:
    """Generate canonical JSON string for state comparison."""
    import json
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
