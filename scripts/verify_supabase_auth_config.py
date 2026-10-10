"""Verify Supabase Auth settings that are not visible through normal SQL.

The leaked-password setting is a hosted Auth configuration. This script uses
the Supabase Management API when SUPABASE_ACCESS_TOKEN and a project ref are
available, and deliberately never prints credentials or the full config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


KNOWN_KEYS = (
    "pwned_passwords_enabled",
    "password_hibp_enabled",
    "leaked_password_protection",
)


def _project_ref() -> str:
    value = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    if value:
        return value
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return url.split("//", 1)[-1].split(".", 1)[0] if url else ""


def _fetch_config(project_ref: str, access_token: str) -> dict:
    request = Request(
        f"https://api.supabase.com/v1/projects/{project_ref}/config/auth",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    token = os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()
    project_ref = _project_ref()
    if not token or not project_ref:
        print("Auth config: inconclusivo (defina SUPABASE_ACCESS_TOKEN e SUPABASE_PROJECT_REF).")
        return 2

    try:
        config = _fetch_config(project_ref, token)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        print(f"Auth config: falha ao consultar Management API ({type(exc).__name__}).")
        return 2

    values = {key: config.get(key) for key in KNOWN_KEYS if key in config}
    if args.as_json:
        print(json.dumps({"project_ref": project_ref, "recognized": values}, ensure_ascii=False))
    elif values:
        print(f"Auth config reconhecida: {', '.join(f'{key}={value!r}' for key, value in values.items())}")
    else:
        print("Auth config consultada, mas a API não expôs uma chave conhecida de proteção contra senhas vazadas.")

    enabled = next((value for value in values.values() if isinstance(value, bool)), None)
    if enabled is True:
        print("pwned_passwords_enabled: habilitado")
        return 0
    if enabled is False:
        print("pwned_passwords_enabled: DESABILITADO; habilite em Authentication > Password Protection.")
        return 1
    print("pwned_passwords_enabled: não confirmado; valide no Dashboard do Supabase.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
