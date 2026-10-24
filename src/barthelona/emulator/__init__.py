"""Emulator child package: V3 static ABI lint (Capstone) and V4 dynamic ABI checks (Unicorn).

This package is the "emulator child" from architecture §3:
- Runs as a separate Windows child process
- Killed on timeout
- Contains unicorn + capstone (SDK containment, D-045)

See D-056 for implementation approach.
"""

__all__ = []
