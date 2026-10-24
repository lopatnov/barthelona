"""Name similarity and merge decision logic for World Model."""

from __future__ import annotations

from typing import Any
import difflib


def levenshtein(a: str, b: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    
    previous_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def name_similarity(name1: str, name2: str) -> float:
    """
    Calculate normalized name similarity using Levenshtein distance.
    
    Returns a value between 0.0 (completely different) and 1.0 (identical).
    """
    norm1 = name1.lower().strip()
    norm2 = name2.lower().strip()
    
    if norm1 == norm2:
        return 1.0
    
    max_len = max(len(norm1), len(norm2))
    if max_len == 0:
        return 1.0
    
    distance = levenshtein(norm1, norm2)
    return 1.0 - (distance / max_len)


def jaccard(set1: set[str], set2: set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union


def decide(similarity: float, auto_merge_at: float = 0.85, review_band: tuple[float, float] = (0.82, 0.85)) -> str:
    """
    Decide merge action based on similarity score.
    
    Returns:
        "auto-merge" if similarity >= auto_merge_at
        "review" if review_band[0] <= similarity < auto_merge_at
        "new" if similarity < review_band[0]
    """
    if similarity >= auto_merge_at:
        return "auto-merge"
    elif similarity >= review_band[0]:
        return "review"
    else:
        return "new"