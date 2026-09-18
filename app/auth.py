import os
import re
import logging
import threading
import time
import hashlib
from collections import deque
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from app import distributed_rate_limit


def _app_base_url() -> str:
    explicit_url = os.getenv("APP_BASE_URL", "").strip()
    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    render_url = (
        f"https://{render_hostname}" if render_hostname else ""
    )
    candidate = explicit_url or render_url
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.netloc or any(char.isspace() for char in candidate):
        return render_url.rstrip("/")
    return candidate.rstrip("/")


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
ACCESS_COOKIE_NAME = "agente_access_token"
REFRESH_COOKIE_NAME = "agente_refresh_token"
MFA_PENDING_ACCESS_COOKIE_NAME = "agente_mfa_pending_access"
MFA_PENDING_REFRESH_COOKIE_NAME = "agente_mfa_pending_refresh"
MFA_PENDING_FACTOR_COOKIE_NAME = "agente_mfa_pending_factor"
MFA_PENDING_CHALLENGE_COOKIE_NAME = "agente_mfa_pending_challenge"
MFA_PENDING_MAX_AGE = 5 * 60
APP_BASE_URL = _app_base_url()
PWNED_PASSWORD_CHECK = os.getenv("PWNED_PASSWORD_CHECK", "false").lower() == "true"
PWNED_PASSWORD_TIMEOUT = 4.0
# Keep the legal text versioned so each signup records exactly what the user
# accepted.  A future policy change can bump these values without changing the
# authentication contract.
TERMS_VERSION = "2026-09-10"
PRIVACY_VERSION = "2026-09-10"
logger = logging.getLogger(__name__)

# A small in-process limiter protects the public auth endpoints even when the
# Supabase project is configured without its own throttling. Render can run
# more than one instance later, so this remains a first layer; the production
# deployment should also enforce limits at the edge/provider level.
_RATE_LIMITS = {
    "login": (10, 10 * 60),
    "signup": (5, 15 * 60),
    "forgot-password": (5, 15 * 60),
    "resend-confirmation": (3, 15 * 60),
    "password": (5, 15 * 60),
    "email": (5, 15 * 60),
    "mfa": (5, 10 * 60),
}
_rate_attempts: dict[str, deque[float]] = {}
_rate_lock = threading.Lock()


def _request_client_key(request: Request | None) -> str:
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "unknown") or "unknown")


def _enforce_rate_limit(
    request: Request | None,
    scope: str,
    account: str = "",
) -> None:
    """Limit an auth operation by both source address and account identifier."""
    limit, window = _RATE_LIMITS[scope]
    now = time.monotonic()
    keys = [f"{scope}:ip:{_request_client_key(request)}"]
    normalized_account = str(account or "").strip().casefold()
    if normalized_account:
        keys.append(f"{scope}:account:{normalized_account}")

    if distributed_rate_limit.is_configured():
        try:
            blocked, distributed_retry_after = distributed_rate_limit.check(
                keys,
                limit,
                window,
            )
        except Exception:
            # Availability remains the default while an instance is being
            # configured.  Production can set the required flag after the
            # shared store is verified, making an unavailable store fail closed.
            if os.getenv("RATE_LIMIT_DISTRIBUTED_REQUIRED", "false").lower() == "true":
                raise HTTPException(
                    503,
                    "Proteção contra excesso de tentativas indisponível.",
                )
            logger.warning("Distributed rate limiter unavailable", exc_info=True)
        else:
            if blocked:
                raise HTTPException(
                    429,
                    "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
                    headers={"Retry-After": str(distributed_retry_after or window)},
                )

    retry_after = 0
    with _rate_lock:
        for key in keys:
            attempts = _rate_attempts.setdefault(key, deque())
            while attempts and now - attempts[0] >= window:
                attempts.popleft()
            if len(attempts) >= limit:
                retry_after = max(retry_after, int(window - (now - attempts[0])) + 1)
        if retry_after:
            raise HTTPException(
                429,
                "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
                headers={"Retry-After": str(retry_after)},
            )
        for key in keys:
            _rate_attempts[key].append(now)

        # Keep this bounded on a long-lived worker when many addresses rotate.
        if len(_rate_attempts) > 5000:
            stale = [
                key
                for key, attempts in _rate_attempts.items()
                if not attempts or now - attempts[-1] >= window
            ]
            for key in stale[:1000]:
                _rate_attempts.pop(key, None)

router = APIRouter(prefix="/auth", tags=["autenticacao"])


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(LoginRequest):
    name: str = ""
    terms_accepted: bool = False
    privacy_accepted: bool = False


class EmailRequest(BaseModel):
    email: str


class SessionRequest(BaseModel):
    access_token: str
    refresh_token: str = ""
    expires_in: int = 3600


class PasswordUpdateRequest(BaseModel):
    password: str


class EmailUpdateRequest(BaseModel):
    email: str


class MfaCodeRequest(BaseModel):
    factor_id: str
    challenge_id: str
    code: str


class MfaLoginCodeRequest(BaseModel):
    factor_id: str
    challenge_id: str
    code: str


def _validated_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(422, "Informe um e-mail valido.")
    return normalized


def _validated_password(password: str) -> str:
    if len(password) < 10:
        raise HTTPException(422, "A senha deve ter pelo menos 10 caracteres.")
    if not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password):
        raise HTTPException(422, "Inclua letras maiusculas e minusculas.")
    if not re.search(r"\d", password):
        raise HTTPException(422, "Inclua pelo menos um numero.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(422, "Inclua pelo menos um simbolo.")
    return password


async def _password_was_compromised(password: str) -> bool:
    """Check a password with k-anonymity; never send the password or full hash."""
    if not PWNED_PASSWORD_CHECK:
        return False
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(
            timeout=PWNED_PASSWORD_TIMEOUT,
            headers={
                "Add-Padding": "true",
                "User-Agent": "Agente-de-Candidaturas-password-check",
            },
        ) as client:
            response = await client.get(
                f"https://api.pwnedpasswords.com/range/{prefix}"
            )
        if response.status_code != 200:
            logger.warning("Password compromise service returned status=%s", response.status_code)
            return False
        for line in response.text.splitlines():
            candidate, _, count = line.partition(":")
            if candidate.strip().upper() == suffix:
                try:
                    return int(count.strip()) > 0
                except ValueError:
                    return True
    except httpx.HTTPError:
        logger.warning("Password compromise service unavailable", exc_info=True)
    return False


async def _reject_compromised_password(password: str) -> None:
    if await _password_was_compromised(password):
        raise HTTPException(
            422,
            "Escolha uma senha que nao apareca em vazamentos conhecidos.",
        )


def _email_is_verified(user: dict | None) -> bool:
    """Return whether Supabase explicitly considers the account confirmed.

    Older/local test doubles may omit both confirmation fields. In that case
    there is no provider signal to enforce, so keep the existing behavior. A
    real Supabase user includes these fields, and an explicit null value means
    the confirmation link is still pending.
    """
    if not isinstance(user, dict):
        return False
    fields = ("email_confirmed_at", "confirmed_at")
    if not any(field in user for field in fields):
        return True
    return any(bool(user.get(field)) for field in fields)


def _email_confirmation_error() -> HTTPException:
    return HTTPException(
        403,
        "Confirme seu e-mail antes de entrar. Enviamos um link para o endereço cadastrado.",
        headers={"X-Auth-Reason": "email_not_verified"},
    )
def _auth_redirect_url() -> str:
    if not APP_BASE_URL.startswith("https://"):
        raise HTTPException(
            503,
            "APP_BASE_URL deve conter a URL HTTPS publica do site.",
        )
    return f"{APP_BASE_URL}/dashboard"


def _supabase_error(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback
    raw_message = (
        payload.get("msg")
        or payload.get("message")
        or payload.get("error_description")
        or payload.get("error")
        or ""
    )
    message = str(raw_message)
    normalized = message.casefold()
    error_code = str(payload.get("error_code") or payload.get("code") or "").casefold()
    if "already registered" in normalized or "already exists" in normalized or error_code in {"user_already_exists", "email_exists"}:
        return "Este e-mail ja possui cadastro. Use Entrar ou Reenviar confirmacao."
    if "rate limit" in normalized or "too many" in normalized or response.status_code == 429:
        return "Limite de tentativas atingido. Aguarde alguns minutos e tente novamente."
    if error_code in {"email_not_confirmed", "email_not_verified"} or "email not confirmed" in normalized:
        return "Confirme seu e-mail antes de entrar."
    if error_code in {"invalid_credentials", "invalid_grant"} or "invalid login credentials" in normalized:
        return "E-mail ou senha invalidos."
    if error_code:
        return f"Supabase recusou o cadastro ({error_code}). Confira os dados e tente novamente."
    return message or fallback


def _configuration_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY)


async def _supabase_request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json: dict | None = None,
) -> httpx.Response:
    if not _configuration_ready():
        raise HTTPException(503, "Autenticacao ainda nao configurada.")

    headers = {"apikey": SUPABASE_PUBLISHABLE_KEY}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.request(
            method,
            f"{SUPABASE_URL}{path}",
            headers=headers,
            json=json,
        )


async def user_from_token(token: str) -> dict | None:
    try:
        response = await _supabase_request("GET", "/auth/v1/user", token=token)
    except (HTTPException, httpx.HTTPError):
        return None
    return response.json() if response.status_code == 200 else None


async def _refresh_session(refresh_token: str) -> dict | None:
    try:
        response = await _supabase_request(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": refresh_token},
        )
    except (HTTPException, httpx.HTTPError):
        return None
    return response.json() if response.status_code == 200 else None


def _set_session_cookies(response: Response, session: dict) -> None:
    cookie_options = {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        session["access_token"],
        max_age=int(session.get("expires_in", 3600)),
        **cookie_options,
    )
    if session.get("refresh_token"):
        response.set_cookie(
            REFRESH_COOKIE_NAME,
            session["refresh_token"],
            max_age=60 * 60 * 24 * 30,
            **cookie_options,
        )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


def _set_mfa_pending_cookies(response: Response, session: dict, factor_id: str, challenge_id: str) -> None:
    options = {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": "lax",
        "path": "/",
        "max_age": MFA_PENDING_MAX_AGE,
    }
    response.set_cookie(MFA_PENDING_ACCESS_COOKIE_NAME, session["access_token"], **options)
    if session.get("refresh_token"):
        response.set_cookie(MFA_PENDING_REFRESH_COOKIE_NAME, session["refresh_token"], **options)
    response.set_cookie(MFA_PENDING_FACTOR_COOKIE_NAME, factor_id, **options)
    response.set_cookie(MFA_PENDING_CHALLENGE_COOKIE_NAME, challenge_id, **options)


def _clear_mfa_pending_cookies(response: Response) -> None:
    for name in (
        MFA_PENDING_ACCESS_COOKIE_NAME,
        MFA_PENDING_REFRESH_COOKIE_NAME,
        MFA_PENDING_FACTOR_COOKIE_NAME,
        MFA_PENDING_CHALLENGE_COOKIE_NAME,
    ):
        response.delete_cookie(name, path="/")


def _mfa_login_enforced() -> bool:
    return os.getenv("MFA_LOGIN_ENFORCE", "false").strip().casefold() in {"1", "true", "yes"}


async def _verified_mfa_factor(access_token: str) -> dict | None:
    """Return the user's verified MFA factor from the authenticated user payload.

    Supabase exposes enrolled factors as part of ``GET /auth/v1/user`` (the same
    response used by ``auth.getUser``/``mfa.listFactors``).  Keeping this lookup
    on the Auth API avoids relying on the project database REST schema, where
    ``/rest/v1/auth/factors`` is not available.
    """
    try:
        response = await _supabase_request("GET", "/auth/v1/user", token=access_token)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Servico de autenticacao indisponivel.") from exc
    if response.status_code != 200:
        logger.warning("Supabase user MFA lookup returned HTTP %s", response.status_code)
        raise HTTPException(503, "Nao foi possivel verificar o segundo fator agora.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(503, "Resposta invalida do servico de autenticacao.") from exc
    factors = payload.get("factors") if isinstance(payload, dict) else []
    if not isinstance(factors, list):
        factors = []
    return next(
        (
            factor
            for factor in factors
            if isinstance(factor, dict)
            and (factor.get("factor_type") or factor.get("type")) == "totp"
            and factor.get("status") == "verified"
        ),
        None,
    )


async def _resolve_session(request: Request) -> tuple[dict | None, dict | None]:
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    user = await user_from_token(access_token) if access_token else None
    if user is not None:
        return user, None

    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    session = await _refresh_session(refresh_token) if refresh_token else None
    if session is None:
        return None, None
    return session.get("user"), session


async def authenticated_user(request: Request) -> dict:
    if not AUTH_REQUIRED:
        return {"id": None, "email": None, "local_mode": True}

    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, "Login necessario.")
    return user


@router.post("/login")
async def login(payload: LoginRequest, request: Request = None):
    email = _validated_email(payload.email)
    _enforce_rate_limit(request, "login", email)
    try:
        response = await _supabase_request(
            "POST",
            "/auth/v1/token?grant_type=password",
            json={"email": email, "password": payload.password},
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de autenticacao indisponivel.")

    if response.status_code != 200:
        raise HTTPException(
            401,
            _supabase_error(response, "E-mail ou senha invalidos."),
        )

    session = response.json()
    session_user = session.get("user")
    authenticated = bool(session.get("access_token") and session_user and _email_is_verified(session_user))
    confirmation_required = bool(session_user) and not _email_is_verified(session_user)
    if confirmation_required:
        result = JSONResponse(
            {
                "authenticated": False,
                "confirmation_required": True,
                "code": "email_not_verified",
                "detail": _email_confirmation_error().detail,
            },
            status_code=403,
            headers={"X-Auth-Reason": "email_not_verified"},
        )
    else:
        result = JSONResponse(
            {
                "authenticated": authenticated,
                "confirmation_required": False,
                "user": {
                    "id": session_user["id"],
                    "email": session_user.get("email"),
                } if session_user else None,
            }
        )
    if authenticated and _mfa_login_enforced():
        factor = await _verified_mfa_factor(session["access_token"])
        if factor:
            try:
                challenge_response = await _supabase_request(
                    "POST",
                    f"/auth/v1/factors/{factor.get('id')}/challenge",
                    token=session["access_token"],
                    json={},
                )
            except httpx.HTTPError as exc:
                raise HTTPException(503, "Servico de autenticacao indisponivel.") from exc
            if challenge_response.status_code not in {200, 201}:
                raise HTTPException(503, "Nao foi possivel iniciar a verificacao 2FA.")
            challenge = challenge_response.json()
            challenge_id = str(challenge.get("id") or "").strip()
            factor_id = str(factor.get("id") or "").strip()
            if not factor_id or not challenge_id:
                raise HTTPException(503, "Resposta invalida do servico de autenticacao.")
            result = JSONResponse(
                {
                    "authenticated": False,
                    "mfa_required": True,
                    "factor_id": factor_id,
                    "challenge_id": challenge_id,
                    "message": "Digite o código do seu aplicativo autenticador para continuar.",
                }
            )
            _set_mfa_pending_cookies(result, session, factor_id, challenge_id)
            return result
    if authenticated:
        _set_session_cookies(result, session)
    return result


@router.post("/signup")
async def signup(payload: SignupRequest, request: Request = None):
    email = _validated_email(payload.email)
    if not payload.terms_accepted or not payload.privacy_accepted:
        raise HTTPException(
            422,
            "Leia e aceite os Termos de Uso e a Política de Privacidade para criar sua conta.",
        )
    _enforce_rate_limit(request, "signup", email)
    password = _validated_password(payload.password)
    await _reject_compromised_password(password)
    redirect_to = quote(_auth_redirect_url(), safe="")
    consented_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        response = await _supabase_request(
            "POST",
            f"/auth/v1/signup?redirect_to={redirect_to}",
            json={
                "email": email,
                "password": password,
                "data": {
                    "name": payload.name.strip(),
                    "terms_accepted": True,
                    "privacy_accepted": True,
                    "terms_version": TERMS_VERSION,
                    "privacy_version": PRIVACY_VERSION,
                    "consented_at": consented_at,
                },
            },
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de cadastro indisponivel.")

    if response.status_code not in {200, 201}:
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = {}
        logger.warning(
            "Supabase signup rejected status=%s code=%s message=%s",
            response.status_code,
            error_payload.get("error_code") or error_payload.get("code") or "unknown",
            error_payload.get("msg") or error_payload.get("message") or "unknown",
        )
        status = 429 if response.status_code == 429 else 400
        raise HTTPException(
            status,
            _supabase_error(response, "Nao foi possivel criar a conta."),
        )

    session = response.json()
    session_user = session.get("user")
    authenticated = bool(session.get("access_token") and session_user and _email_is_verified(session_user))
    confirmation_required = bool(session_user) and not _email_is_verified(session_user)
    result = JSONResponse(
        {
            "created": True,
            "authenticated": authenticated,
            "confirmation_required": not authenticated or confirmation_required,
            "message": (
                "Conta criada. Confira seu e-mail para confirmar o cadastro."
                if not authenticated or confirmation_required
                else "Conta criada com sucesso."
            ),
        },
        status_code=201,
    )
    if authenticated:
        _set_session_cookies(result, session)
    return result


@router.post("/session")
async def accept_session(payload: SessionRequest):
    user = await user_from_token(payload.access_token)
    if user is None:
        raise HTTPException(401, "Sessao de confirmacao invalida ou expirada.")
    if not _email_is_verified(user):
        raise _email_confirmation_error()

    result = JSONResponse(
        {
            "authenticated": True,
            "user": {"id": user["id"], "email": user.get("email")},
        }
    )
    _set_session_cookies(
        result,
        {
            "access_token": payload.access_token,
            "refresh_token": payload.refresh_token,
            "expires_in": payload.expires_in,
        },
    )
    return result


@router.post("/forgot-password")
async def forgot_password(payload: EmailRequest, request: Request = None):
    email = _validated_email(payload.email)
    _enforce_rate_limit(request, "forgot-password", email)
    redirect_to = quote(_auth_redirect_url(), safe="")
    try:
        response = await _supabase_request(
            "POST",
            f"/auth/v1/recover?redirect_to={redirect_to}",
            json={"email": email},
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de recuperacao indisponivel.")

    if response.status_code == 429:
        raise HTTPException(429, "Aguarde antes de solicitar outro e-mail.")
    if response.status_code >= 500:
        raise HTTPException(503, "Servico de recuperacao indisponivel.")
    return {
        "message": (
            "Se o e-mail estiver cadastrado, enviaremos as instrucoes de recuperacao."
        )
    }


@router.post("/resend-confirmation")
async def resend_confirmation(payload: EmailRequest, request: Request = None):
    email = _validated_email(payload.email)
    _enforce_rate_limit(request, "resend-confirmation", email)
    redirect_to = quote(_auth_redirect_url(), safe="")
    try:
        response = await _supabase_request(
            "POST",
            f"/auth/v1/resend?redirect_to={redirect_to}",
            json={"type": "signup", "email": email},
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de confirmacao indisponivel.")

    if response.status_code == 429:
        raise HTTPException(429, "Aguarde antes de solicitar outro e-mail.")
    if response.status_code >= 500:
        raise HTTPException(503, "Servico de confirmacao indisponivel.")
    return {"message": "Se houver um cadastro pendente, o e-mail sera reenviado."}


@router.put("/password")
async def update_password(
    payload: PasswordUpdateRequest,
    request: Request,
    user: dict = Depends(authenticated_user),
):
    password = _validated_password(payload.password)
    await _reject_compromised_password(password)
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id"):
        raise HTTPException(401, "Login necessario.")
    _enforce_rate_limit(request, "password", str(user.get("id")))
    try:
        response = await _supabase_request(
            "PUT",
            "/auth/v1/user",
            token=access_token,
            json={"password": password},
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de autenticacao indisponivel.")
    if response.status_code != 200:
        raise HTTPException(
            400,
            _supabase_error(response, "Nao foi possivel alterar a senha."),
        )
    return {"updated": True}


@router.put("/email")
async def update_email(
    payload: EmailUpdateRequest,
    request: Request,
    user: dict = Depends(authenticated_user),
):
    email = _validated_email(payload.email)
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id"):
        raise HTTPException(401, "Login necessario.")
    _enforce_rate_limit(request, "email", str(user.get("id")))
    try:
        response = await _supabase_request(
            "PUT",
            "/auth/v1/user",
            token=access_token,
            json={"email": email},
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de autenticacao indisponivel.")
    if response.status_code != 200:
        raise HTTPException(400, _supabase_error(response, "Nao foi possivel alterar o e-mail."))
    return {"updated": True, "message": "Confira o novo e-mail para confirmar a alteracao."}


@router.post("/mfa/enroll")
async def mfa_enroll(request: Request, user: dict = Depends(authenticated_user)):
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id"):
        raise HTTPException(401, "Login necessario.")
    try:
        response = await _supabase_request("POST", "/auth/v1/factors", token=access_token, json={"factor_type": "totp", "friendly_name": "Agente de Candidaturas"})
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de autenticacao indisponivel.")
    if response.status_code not in {200, 201}:
        raise HTTPException(400, _supabase_error(response, "Nao foi possivel iniciar o 2FA."))
    factor = response.json()
    return {"id": factor.get("id"), "type": factor.get("type"), "qr_code": factor.get("totp", {}).get("qr_code"), "secret": factor.get("totp", {}).get("secret"), "uri": factor.get("totp", {}).get("uri")}


@router.post("/mfa/verify")
async def mfa_verify(payload: MfaCodeRequest, request: Request, user: dict = Depends(authenticated_user)):
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id"):
        raise HTTPException(401, "Login necessario.")
    try:
        response = await _supabase_request("POST", f"/auth/v1/factors/{payload.factor_id}/verify", token=access_token, json={"challenge_id": payload.challenge_id, "code": payload.code})
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de autenticacao indisponivel.")
    if response.status_code not in {200, 201}:
        raise HTTPException(400, _supabase_error(response, "Codigo 2FA invalido."))
    return {"verified": True, "message": "Autenticador ativado com sucesso."}


@router.post("/mfa/challenge")
async def mfa_challenge(payload: dict, request: Request, user: dict = Depends(authenticated_user)):
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id"):
        raise HTTPException(401, "Login necessario.")
    try:
        response = await _supabase_request("POST", f"/auth/v1/factors/{payload.get('factor_id')}/challenge", token=access_token, json={})
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de autenticacao indisponivel.")
    if response.status_code not in {200, 201}:
        raise HTTPException(400, _supabase_error(response, "Nao foi possivel iniciar a verificacao 2FA."))
    return response.json()


@router.get("/mfa/status")
async def mfa_status(request: Request, user: dict = Depends(authenticated_user)):
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id"):
        raise HTTPException(401, "Login necessario.")
    factors = user.get("factors") if isinstance(user, dict) else []
    if not isinstance(factors, list):
        factors = []
    return {
        "factors": [
            {
                "id": factor.get("id"),
                "type": factor.get("factor_type") or factor.get("type") or "totp",
                "status": factor.get("status"),
                "friendly_name": factor.get("friendly_name"),
            }
            for factor in factors
            if isinstance(factor, dict)
        ],
        "enabled": any(
            isinstance(factor, dict)
            and (factor.get("factor_type") or factor.get("type")) == "totp"
            and factor.get("status") == "verified"
            for factor in factors
        ),
    }


@router.delete("/mfa/{factor_id}")
async def mfa_unenroll(factor_id: str, request: Request, user: dict = Depends(authenticated_user)):
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id") or not factor_id.strip():
        raise HTTPException(401, "Login necessario.")
    try:
        response = await _supabase_request("DELETE", f"/auth/v1/factors/{factor_id.strip()}", token=access_token)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Servico de autenticacao indisponivel.") from exc
    if response.status_code not in {200, 204}:
        raise HTTPException(400, _supabase_error(response, "Nao foi possivel remover o autenticador."))
    return {"removed": True}


@router.post("/mfa/complete")
async def mfa_complete_login(payload: MfaLoginCodeRequest, request: Request):
    pending_access = request.cookies.get(MFA_PENDING_ACCESS_COOKIE_NAME)
    pending_factor = request.cookies.get(MFA_PENDING_FACTOR_COOKIE_NAME)
    pending_challenge = request.cookies.get(MFA_PENDING_CHALLENGE_COOKIE_NAME)
    if not pending_access or not pending_factor or not pending_challenge:
        raise HTTPException(401, "A verificacao 2FA expirou. Entre novamente.")
    if payload.factor_id != pending_factor or payload.challenge_id != pending_challenge:
        raise HTTPException(400, "Desafio 2FA invalido.")
    _enforce_rate_limit(request, "mfa", pending_factor)
    try:
        response = await _supabase_request(
            "POST",
            f"/auth/v1/factors/{pending_factor}/verify",
            token=pending_access,
            json={"challenge_id": pending_challenge, "code": payload.code.strip()},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Servico de autenticacao indisponivel.") from exc
    if response.status_code not in {200, 201}:
        raise HTTPException(401, "Codigo 2FA invalido.")
    try:
        session = response.json()
    except ValueError as exc:
        raise HTTPException(503, "Resposta invalida do servico de autenticacao.") from exc
    if not session.get("access_token"):
        raise HTTPException(503, "O provedor nao retornou uma sessao 2FA valida.")
    result = JSONResponse({"authenticated": True, "mfa_verified": True})
    _set_session_cookies(result, session)
    _clear_mfa_pending_cookies(result)
    return result


@router.get("/me")
async def current_user(request: Request):
    if not AUTH_REQUIRED:
        return {"authenticated": False, "local_mode": True}
    if not _configuration_ready():
        raise HTTPException(503, "Autenticacao nao configurada.")

    user, renewed_session = await _resolve_session(request)
    if user is None:
        response = JSONResponse({"detail": "Login necessario."}, status_code=401)
        _clear_session_cookies(response)
        return response
    if not _email_is_verified(user):
        response = JSONResponse(
            {"detail": _email_confirmation_error().detail, "code": "email_not_verified"},
            status_code=403,
            headers={"X-Auth-Reason": "email_not_verified"},
        )
        _clear_session_cookies(response)
        return response

    response = JSONResponse(
        {
            "authenticated": True,
            "user": {"id": user["id"], "email": user.get("email")},
        }
    )
    if renewed_session:
        _set_session_cookies(response, renewed_session)
    return response


@router.post("/logout")
async def logout(request: Request):
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    pending_access = request.cookies.get(MFA_PENDING_ACCESS_COOKIE_NAME)
    if access_token and _configuration_ready():
        try:
            await _supabase_request("POST", "/auth/v1/logout?scope=global", token=access_token)
        except httpx.HTTPError:
            logger.warning("Falha ao revogar sessão no provedor; cookies serão limpos.")
    if pending_access and _configuration_ready():
        try:
            await _supabase_request("POST", "/auth/v1/logout?scope=global", token=pending_access)
        except httpx.HTTPError:
            logger.warning("Falha ao revogar desafio MFA pendente; cookies serão limpos.")
    response = Response(status_code=204)
    _clear_session_cookies(response)
    _clear_mfa_pending_cookies(response)
    return response


class AuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {
        "/",
        "/dashboard",
        "/health",
        "/auth/login",
        "/auth/signup",
        "/auth/session",
        "/auth/forgot-password",
        "/auth/resend-confirmation",
        "/auth/me",
        "/auth/logout",
        "/auth/mfa/complete",
        "/webhooks/mercadopago",
        "/auth/verification-required",
        "/ajuda",
        # Documentos legais precisam ser legíveis antes do cadastro e do
        # consentimento; não podem cair no bloqueio de sessão.
        "/termos",
        "/termos/",
        "/privacidade",
        "/privacidade/",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    async def dispatch(self, request: Request, call_next):
        # Static assets are required by public and authenticated HTML pages.
        # They must remain readable without a session so the browser can load
        # the page's JavaScript/CSS enhancements after authentication is
        # enforced for the application routes.
        if not AUTH_REQUIRED or request.url.path in self.PUBLIC_PATHS or request.url.path.startswith("/static/"):
            return await call_next(request)

        if not _configuration_ready():
            return JSONResponse(
                {"detail": "Autenticacao nao configurada."},
                status_code=503,
            )

        user, renewed_session = await _resolve_session(request)
        if user is None:
            response = JSONResponse({"detail": "Login necessario."}, status_code=401)
            _clear_session_cookies(response)
            return response

        if not _email_is_verified(user):
            wants_html = request.method in {"GET", "HEAD"} and "text/html" in request.headers.get("accept", "")
            if wants_html:
                response = RedirectResponse("/auth/verification-required", status_code=303)
            else:
                response = JSONResponse(
                    {"detail": _email_confirmation_error().detail, "code": "email_not_verified"},
                    status_code=403,
                    headers={"X-Auth-Reason": "email_not_verified"},
                )
            _clear_session_cookies(response)
            return response

        request.state.user = user
        response = await call_next(request)
        if renewed_session:
            _set_session_cookies(response, renewed_session)
        return response
