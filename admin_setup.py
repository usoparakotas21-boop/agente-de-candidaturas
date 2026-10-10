import asyncio
import getpass
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def create_admin():
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    if not supabase_url or not anon_key:
        print("Erro: SUPABASE_URL ou SUPABASE_ANON_KEY não encontradas no .env")
        return

    email = os.getenv("ADMIN_EMAIL", "contato@candidaturacerta.com.br").strip()
    password = getpass.getpass("Senha inicial do administrador (não será exibida): ")
    if not password:
        print("Erro: a senha não pode ser vazia.")
        return

    print(f"Tentando registrar administrador: {email}")
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{supabase_url}/auth/v1/signup",
            headers={"apikey": anon_key},
            json={"email": email, "password": password},
        )

    if res.status_code in (200, 201):
        print("Administrador criado. Confirme o e-mail antes do primeiro login, se solicitado.")
    elif "already registered" in res.text.lower():
        print("O usuário já existe no sistema. Use a recuperação de senha do Supabase.")
    else:
        print(f"Falha ao criar o administrador. Código: {res.status_code}")
        print(res.text)

if __name__ == "__main__":
    asyncio.run(create_admin())