from __future__ import annotations
"""Simple grouping helper for log issues.

A lightweight normalization that drops the first two CSV fields (severity, timestamp)
so repeating errors differing only by time or host collapse into one group.
Adjust later if over/under-grouping.
"""

def group_key(message: str) -> str:
    if not message:
        return ""
    # Split into at most 3 parts: severity, timestamp, remainder
    parts = message.split(',', 2)
    if len(parts) >= 3:
        core = parts[2]
    else:
        core = message
    return core.lower().strip()
