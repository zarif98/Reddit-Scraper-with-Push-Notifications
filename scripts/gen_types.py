#!/usr/bin/env python3
"""Generate frontend TypeScript types from the Pydantic models (single source of truth).

Usage:  python3 scripts/gen_types.py        (or: npm --prefix frontend run gen:types)

Pipeline: each model -> JSON Schema (pydantic) -> TypeScript (json-schema-to-typescript).
Requires pydantic (Python) and the frontend devDependency json-schema-to-typescript.
The generated file is committed; CI re-runs this and fails if it's stale (see test workflow).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reddit_scraper.models import Monitor  # noqa: E402  (needs sys.path set first)

MODELS = [Monitor]
OUT = ROOT / 'frontend' / 'types' / 'generated.ts'
JSON2TS = ROOT / 'frontend' / 'node_modules' / '.bin' / 'json2ts'

BANNER = (
    '// AUTO-GENERATED from reddit_scraper/models.py — do not edit by hand.\n'
    '// Regenerate with: npm run gen:types (from frontend/) or python3 scripts/gen_types.py\n'
)


def _model_to_ts(model):
    schema = model.model_json_schema()
    # Drop per-property titles so json2ts inlines primitives (string, number[]) instead of
    # emitting a named alias (export type Id = string) for every field. Keep the top title.
    for prop in schema.get('properties', {}).values():
        prop.pop('title', None)
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(schema, f)
        schema_path = f.name
    try:
        result = subprocess.run(
            [str(JSON2TS), '-i', schema_path, '--bannerComment', '', '--additionalProperties', 'false'],
            capture_output=True,
            text=True,
        )
    finally:
        Path(schema_path).unlink(missing_ok=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        sys.exit(1)
    return result.stdout.strip()


def main():
    if not JSON2TS.exists():
        sys.exit("json2ts not found — run `npm install` in frontend/ first.")
    blocks = [_model_to_ts(m) for m in MODELS]
    OUT.write_text(BANNER + '\n' + '\n\n'.join(blocks) + '\n')
    print(f'wrote {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
