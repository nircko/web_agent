#!/usr/bin/env python3
"""When used as GIT_EDITOR: remove _is_broker_card and _classify_seller_type from patch, keep _fix_hebrew_encoding and _process_file_decode."""
import sys

path = sys.argv[-1]
with open(path) as f:
    lines = f.readlines()

out = []
skip = False
for i, line in enumerate(lines):
    if "+def _is_broker_card" in line:
        skip = True
        continue
    if skip:
        if line.startswith(" "):
            skip = False
        else:
            continue
    out.append(line)

with open(path, "w") as f:
    f.writelines(out)
