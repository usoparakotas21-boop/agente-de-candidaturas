"""End-to-end Supabase Auth, profile, preferences and RLS validation.

The script creates two short-lived users with the ``test_auto_`` prefix using
the Supabase Admin API, authenticates both through the normal password grant,
updates a ``public.candidatos`` profile as user A, verifies derived search
terms, and proves that user B cannot read or update A's row through PostgREST.
All users and profile rows are removed in ``finally``. Credentials are read
from the environment and are never printed.

Required environment variables:
  SUPABASE_URL (or SUPABASE_PROJECT_URL)
  SUPABASE_ANON_KEY (or SUPABASE_PUBLISHABLE_KEY)
  SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY)
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class ValidationError(RuntimeError):
    pass


@dataclass
class TestUser:
    email: str
    password: str
    user_id: str = ""
    access_token: str = ""


def _env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _api_root() -> str:
    url = _env("SUPABASE_URL", "SUPABASE_PROJECT_URL").rstrip("/")
    if not url:
        raise ValidationError("SUPABASE_URL não foi definido.")
    return url


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    expected: tuple[int, ...] = (200, 201, 204),
) -> Any:
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=45) as response:
            status = response.status
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise ValidationError(f"{method} {url.split('?')[0]} retornou HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise ValidationError(f"{method} {url.split('?')[0]} falhou: {type(exc).__name__}") from exc
    if status not in expected:
        raise ValidationError(f"{method} {url.split('?')[0]} retornou HTTP {status}.")
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return raw.decode("utf-8", errors="replace")


def _headers(api_key: str, token: str | None = None, *, service: bool = False) -> dict[str, str]:
    bearer = token or api_key
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {bearer}",
        **({"Prefer": "return=representation"} if not service else {}),
    }


def _new_user(label: str) -> TestUser:
    suffix = f"{int(time.time())}_{secrets.token_hex(4)}"
    return TestUser(
        email=f"test_auto_{label}_{suffix}@example.invalid",
        password=f"T3st-Auto!{secrets.token_urlsafe(12)}",
    )


def _create_user(root: str, service_key: str, user: TestUser) -> None:
    data = _json_request(
        f"{root}/auth/v1/admin/users",
        method="POST",
        payload={
            "email": user.email,
            "password": user.password,
            "email_confirm": True,
            "user_metadata": {"test_prefix": "test_auto_", "role": "phase2_validation"},
        },
        headers=_headers(service_key, service_key, service=True),
        expected=(200, 201),
    )
    user.user_id = str((data or {}).get("id") or (data or {}).get("user", {}).get("id") or "")
    if not user.user_id:
        raise ValidationError("Admin API criou o usuário sem devolver o id.")


def _login(root: str, anon_key: str, user: TestUser) -> None:
    data = _json_request(
        f"{root}/auth/v1/token?grant_type=password",
        method="POST",
        payload={"email": user.email, "password": user.password},
        headers={"apikey": anon_key},
        expected=(200,),
    )
    user.access_token = str((data or {}).get("access_token") or "")
    if not user.access_token:
        raise ValidationError("Login não devolveu access_token/JWT.")


def _terms(role: str, location: str, modalities: list[str]) -> list[str]:
    values = [role, location, *modalities]
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split()).strip()
        if cleaned and cleaned.casefold() not in {item.casefold() for item in result}:
            result.append(cleaned)
    return result


def _postgrest(root: str, table: str, query: str, user: TestUser, anon_key: str, **kwargs: Any) -> Any:
    extra_headers = kwargs.pop("headers", {}) or {}
    request_headers = _headers(anon_key, user.access_token)
    request_headers.update(extra_headers)
    return _json_request(
        f"{root}/rest/v1/{table}?{query}" if query else f"{root}/rest/v1/{table}",
        headers=request_headers,
        **kwargs,
    )


def _assert_profile_and_rls(root: str, anon_key: str, service_key: str, user_a: TestUser, user_b: TestUser) -> None:
    role = "Analista de RH"
    location = "Salvador, BA"
    modalities = ["Remoto", "Híbrido", "Presencial"]
    terms = _terms(role, location, modalities)
    profile = {
        "user_id": user_a.user_id,
        "owner_id": user_a.user_id,
        "nome": "Teste Automático",
        "email": user_a.email,
        "telefone": "71999999999",
        "cargo_interesse": role,
        "localidade": location,
        "modalidades": modalities,
        "termos_derivados": terms,
    }

    created = _postgrest(
        root,
        "candidatos",
        "",
        user_a,
        anon_key,
        method="POST",
        payload=profile,
        headers={"Prefer": "return=representation"},
        expected=(201,),
    )
    if not isinstance(created, list) or not created:
        raise ValidationError("Cadastro de candidato não devolveu o perfil criado.")

    candidate_id = str(created[0].get("id") or "")
    if not candidate_id:
        raise ValidationError("Perfil criado sem id.")

    updated = _postgrest(
        root,
        "candidatos",
        f"id=eq.{quote(candidate_id, safe='')}",
        user_a,
        anon_key,
        method="PATCH",
        payload={"cargo_interesse": role, "localidade": location, "modalidades": modalities, "termos_derivados": terms},
        headers={"Prefer": "return=representation"},
        expected=(200,),
    )
    if not isinstance(updated, list) or not updated:
        raise ValidationError("Atualização do perfil não retornou linha para o proprietário.")
    row = updated[0]
    if row.get("cargo_interesse") != role or row.get("localidade") != location:
        raise ValidationError("Cargo/localidade não persistiram no perfil.")
    if row.get("modalidades") != modalities or row.get("termos_derivados") != terms:
        raise ValidationError("Modalidades ou termos derivados não persistiram.")

    visible_to_b = _postgrest(
        root,
        "candidatos",
        f"select=id,user_id&user_id=eq.{quote(user_a.user_id, safe='')}",
        user_b,
        anon_key,
        expected=(200,),
    )
    if visible_to_b:
        raise ValidationError("RLS falhou: Usuário B conseguiu ler o perfil de A.")

    changed_by_b = _postgrest(
        root,
        "candidatos",
        f"id=eq.{quote(candidate_id, safe='')}",
        user_b,
        anon_key,
        method="PATCH",
        payload={"localidade": "Acesso indevido"},
        headers={"Prefer": "return=representation"},
        expected=(200,),
    )
    if changed_by_b:
        raise ValidationError("RLS falhou: Usuário B conseguiu alterar o perfil de A.")

    print("Phase 2: cadastro, login/JWT, perfil, termos derivados e isolamento RLS: PASS")


def _cleanup(root: str, service_key: str, user: TestUser) -> None:
    if not user.user_id:
        return
    headers = _headers(service_key, service_key, service=True)
    try:
        _json_request(
            f"{root}/rest/v1/candidatos?user_id=eq.{quote(user.user_id, safe='')}",
            method="DELETE",
            headers=headers,
            expected=(204, 200),
        )
    finally:
        _json_request(
            f"{root}/auth/v1/admin/users/{quote(user.user_id, safe='')}",
            method="DELETE",
            headers=headers,
            expected=(204, 200),
        )


def main() -> int:
    root = _api_root() if _env("SUPABASE_URL", "SUPABASE_PROJECT_URL") else ""
    anon_key = _env("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY")
    service_key = _env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY")
    if not root or not anon_key or not service_key:
        print("Phase 2: inconclusivo; defina SUPABASE_URL, SUPABASE_ANON_KEY e SUPABASE_SERVICE_ROLE_KEY.")
        return 2

    user_a, user_b = _new_user("a"), _new_user("b")
    failure: Exception | None = None
    try:
        _create_user(root, service_key, user_a)
        _create_user(root, service_key, user_b)
        _login(root, anon_key, user_a)
        _login(root, anon_key, user_b)
        print("Phase 2: usuários temporários criados e login/JWT emitido.")
        _assert_profile_and_rls(root, anon_key, service_key, user_a, user_b)
        return 0
    except Exception as exc:
        failure = exc
        print(f"Phase 2: FAIL — {exc}")
        return 1
    finally:
        for user in (user_a, user_b):
            try:
                _cleanup(root, service_key, user)
            except Exception as exc:
                print(f"Phase 2: limpeza incompleta para usuário temporário ({type(exc).__name__}).")
                if failure is None:
                    failure = exc


if __name__ == "__main__":
    sys.exit(main())
