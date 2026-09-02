import os
import logging
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware


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
APP_BASE_URL = _app_base_url()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["autenticacao"])


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(LoginRequest):
    name: str = ""


class EmailRequest(BaseModel):
    email: str


class SessionRequest(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int = 3600


class PasswordUpdateRequest(BaseModel):
    password: str


class EmailUpdateRequest(BaseModel):
    email: str


class MfaCodeRequest(BaseModel):
    factor_id: str
    challenge_id: str
    code: str


def _validated_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(422, "Informe um e-mail valido.")
    return normalized


def _validated_password(password: str) -> str:
    if len(password) < 8:
        raise HTTPException(422, "A senha deve ter pelo menos 8 caracteres.")
    return password


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
async def login(payload: LoginRequest):
    try:
        response = await _supabase_request(
            "POST",
            "/auth/v1/token?grant_type=password",
            json={"email": payload.email, "password": payload.password},
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servico de autenticacao indisponivel.")

    if response.status_code != 200:
        raise HTTPException(401, "E-mail ou senha invalidos.")

    session = response.json()
    result = JSONResponse(
        {
            "authenticated": True,
            "user": {
                "id": session["user"]["id"],
                "email": session["user"].get("email"),
            },
        }
    )
    _set_session_cookies(result, session)
    return result


@router.post("/signup")
async def signup(payload: SignupRequest):
    email = _validated_email(payload.email)
    password = _validated_password(payload.password)
    redirect_to = quote(_auth_redirect_url(), safe="")
    try:
        response = await _supabase_request(
            "POST",
            f"/auth/v1/signup?redirect_to={redirect_to}",
            json={
                "email": email,
                "password": password,
                "data": {"name": payload.name.strip()},
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
    authenticated = bool(session.get("access_token") and session.get("user"))
    result = JSONResponse(
        {
            "created": True,
            "authenticated": authenticated,
            "confirmation_required": not authenticated,
            "message": (
                "Conta criada. Confira seu e-mail para confirmar o cadastro."
                if not authenticated
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
async def forgot_password(payload: EmailRequest):
    email = _validated_email(payload.email)
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
async def resend_confirmation(payload: EmailRequest):
    email = _validated_email(payload.email)
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
    access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token or not user.get("id"):
        raise HTTPException(401, "Login necessario.")
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
    if access_token and _configuration_ready():
        try:
            await _supabase_request("POST", "/auth/v1/logout?scope=global", token=access_token)
        except httpx.HTTPError:
            logger.warning("Falha ao revogar sessão no provedor; cookies serão limpos.")
    response = Response(status_code=204)
    _clear_session_cookies(response)
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
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    async def dispatch(self, request: Request, call_next):
        if not AUTH_REQUIRED or request.url.path in self.PUBLIC_PATHS:
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

        request.state.user = user
        response = await call_next(request)
        if renewed_session:
            _set_session_cookies(response, renewed_session)
        return response
