$ErrorActionPreference = "Stop"
$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { ".venv-test\Scripts\python.exe" }

Write-Host "[1/6] Validando suite principal"
& $python -m pytest tests -q
Write-Host "[2/6] Validando Fase 3/4"
& $python scripts/validate_phase3_4.py
Write-Host "[3/6] Validando Fase 5"
& $python scripts/validate_phase5_billing_admin.py
Write-Host "[4/6] Validando Fase 6/7"
& $python scripts/validate_phase6_7_scrapers.py
if ($env:DATABASE_URL) {
  Write-Host "[5/6] Validando schema/RLS"
  & $python scripts/verify_phase1_db.py
} else { Write-Host "[5/6] Schema/RLS externo não configurado; ignorado" }
if ($env:SUPABASE_URL -and $env:SUPABASE_ANON_KEY -and $env:SUPABASE_SERVICE_ROLE_KEY) {
  Write-Host "[6/6] Validando Supabase Auth"
  & $python scripts/validate_phase2_auth_profile.py
} else { Write-Host "[6/6] Supabase Auth não configurado; ignorado" }
Write-Host "Todas as validações disponíveis foram aprovadas."
