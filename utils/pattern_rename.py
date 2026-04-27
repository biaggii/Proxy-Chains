"""
Shared pattern-based rename utility.

Supports templates like ``US{1-8}`` or ``HK{3-10}`` and is used by
both the Nodes batch-create-chain and the Chains batch-rename features.
"""

import re

_PATTERN_RE = re.compile(r"\{(\d+)(?:-(\d+))?\}")


def expand_pattern(pattern: str, index: int, total: int) -> str:
    """Return the name for *index* (0-based) given a pattern template.

    If *pattern* contains ``{N}`` or ``{N-M}``, the number is
    ``N + index``.  Otherwise the pattern is used as-is (with a
    trailing index when *total* > 1).
    """
    if not pattern:
        return ""

    match = _PATTERN_RE.search(pattern)
    if match:
        start_num = int(match.group(1))
        prefix = pattern[: match.start()]
        suffix = pattern[match.end() :]
        return f"{prefix}{start_num + index}{suffix}"

    if total > 1:
        return f"{pattern}{index + 1}"
    return pattern
