#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "[1/6] Validando suite principal"
"$PYTHON_BIN" -m pytest tests -q

echo "[2/6] Validando Fase 3/4 (LGPD, IA e e-book)"
"$PYTHON_BIN" scripts/validate_phase3_4.py

echo "[3/6] Validando Fase 5 (billing e painel administrativo)"
"$PYTHON_BIN" scripts/validate_phase5_billing_admin.py

echo "[4/6] Validando Fase 6/7 (e-mails, scrapers e endpoint assíncrono)"
"$PYTHON_BIN" scripts/validate_phase6_7_scrapers.py

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "[5/6] Validando schema/RLS no banco configurado"
  "$PYTHON_BIN" scripts/verify_phase1_db.py
else
  echo "[5/6] Schema/RLS externo não configurado; validação online ignorada"
fi

if [[ -n "${SUPABASE_URL:-}" && -n "${SUPABASE_ANON_KEY:-}" && -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
  echo "[6/6] Validando autenticação e perfil no Supabase"
  "$PYTHON_BIN" scripts/validate_phase2_auth_profile.py
else
  echo "[6/6] Supabase Auth não configurado; validação online ignorada"
fi

echo "Todas as validações disponíveis foram aprovadas."
