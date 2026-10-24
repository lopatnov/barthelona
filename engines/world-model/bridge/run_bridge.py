#!/usr/bin/env python3
"""Wrapper script that runs the bridge with proper environment setup."""

import os
import sys
import subprocess
import json
import tempfile

# Get the project root (go up from engines/world-model/bridge to project root)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
dev_script = os.path.join(project_root, "scripts", "dev.ps1")
bridge_script = os.path.join(current_dir, "bridge.py")

# Read stdin
input_data = sys.stdin.read()

# If stdin is empty, try reading from a temp file passed as argument
if not input_data and len(sys.argv) > 1:
    with open(sys.argv[1], 'r') as f:
        input_data = f.read()

if not input_data:
    print(json.dumps({"error": "empty input"}))
    sys.exit(1)

# Write input to a temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(json.loads(input_data), f)
    temp_input = f.name

# Run via PowerShell with dev.ps1, passing the temp file
cmd = [
    "powershell", "-Command",
    f"& '{dev_script}' python '{bridge_script}' '{temp_input}'"
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root, timeout=30)
finally:
    # Clean up temp file
    try:
        os.unlink(temp_input)
    except:
        pass

if result.returncode != 0:
    print(json.dumps({"error": f"Bridge failed: {result.stderr}"}), file=sys.stdout)
    sys.exit(1)

print(result.stdout)