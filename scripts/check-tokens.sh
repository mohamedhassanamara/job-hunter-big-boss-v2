#!/usr/bin/env bash
# Design-system guard: components must use tokens, never raw colors or Tailwind palette classes.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/frontend/src"
PALETTE='(bg|text|border|ring|fill|stroke|from|to|via|outline|divide|shadow)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}'
HEX='#[0-9a-fA-F]{3,8}\b'
fail=0
if grep -rEn "$PALETTE" "$SRC" --include='*.tsx' --include='*.ts'; then
  echo "✗ Tailwind palette classes found — use design tokens (see docs/DESIGN.md)"; fail=1
fi
if grep -rEn "$HEX" "$SRC" --include='*.tsx' --include='*.ts'; then
  echo "✗ Raw hex colors found in components — use design tokens"; fail=1
fi
[ $fail -eq 0 ] && echo "✓ token check passed"
exit $fail
