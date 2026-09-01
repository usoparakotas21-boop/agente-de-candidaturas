import os

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
ACCESS_COOKIE_NAME = "agente_access_token"
REFRESH_COOKIE_NAME = "agente_refresh_token"

router = APIRouter(prefix="/auth", tags=["autenticacao"])


class LoginRequest(BaseModel):
    email: str
    password: str


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
async def logout():
    response = Response(status_code=204)
    _clear_session_cookies(response)
    return response


class AuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {
        "/",
        "/dashboard",
        "/auth/login",
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
