import asyncio
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
        
    email = "contato@candidaturacerta.com.br"
    password = "Admin@Certa2026!#"
    
    print(f"Tentando registrar administrador: {email}")
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{supabase_url}/auth/v1/signup",
            headers={"apikey": anon_key},
            json={"email": email, "password": password}
        )
        
        if res.status_code in (200, 201):
            print("========================================")
            print("SUCESSO: Administrador criado no Supabase!")
            print(f"E-mail: {email}")
            print(f"Senha: {password}")
            print("========================================")
            print("Dica: Você já pode fazer login na página /admin/login com estas credenciais.")
        elif "already registered" in res.text.lower():
            print("O usuário já existe no sistema. Tente redefinir a senha se não lembrar.")
        else:
            print(f"Falha ao criar o administrador. Código: {res.status_code}")
            print(res.text)

if __name__ == "__main__":
    asyncio.run(create_admin())