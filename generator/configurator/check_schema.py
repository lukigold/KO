#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate KO layout files against generator/schema/ko-layout-1.schema.json.

    python3 generator/configurator/check_schema.py FILE...

A FILE may hold one layout or a JSON array of layouts (as written by check_builder.js).
"""
import json
import pathlib
import sys

import jsonschema

SCHEMA = pathlib.Path(__file__).resolve().parents[1] / "schema" / "ko-layout-1.schema.json"


def main() -> int:
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    count = bad = 0
    for name in sys.argv[1:]:
        data = json.loads(pathlib.Path(name).read_text())
        for layout in data if isinstance(data, list) else [data]:
            count += 1
            for err in validator.iter_errors(layout):
                bad += 1
                print(f"FAIL {name} {layout.get('name')}: {'/'.join(map(str, err.path))}: {err.message}")
    print(f"{count} layout files checked, {bad} schema errors")
    print("RESULT: PASS" if count and not bad else "RESULT: FAIL")
    return 0 if count and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
