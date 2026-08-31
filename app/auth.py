import os
from fastapi import Request, Depends
from fastapi.routing import APIRouter

# Modo local: autenticação desligada
AUTH_REQUIRED = False

class AuthMiddleware:
    """Middleware dummy que não faz nada em modo local."""
    async def __call__(self, request: Request, call_next):
        return await call_next(request)

async def authenticated_user(request: Request):
    """Retorna um usuário local para testes."""
    return {"id": "local_user", "email": "local@teste.com", "local_mode": True}

router = APIRouter()

@router.get("/me")
async def current_user(request: Request):
    return {"authenticated": True, "local_mode": True, "user": {"id": "local_user", "email": "local@teste.com"}}

@router.post("/login")
async def login(request: Request):
    return {"message": "Login desabilitado em modo local"}

@router.post("/logout")
async def logout(request: Request):
    return {"message": "Logout desabilitado em modo local"}