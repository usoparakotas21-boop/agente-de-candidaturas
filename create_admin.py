import asyncio
import os
from dotenv import load_dotenv
import httpx

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()

async def create_admin():
    if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
        print("Erro: Credenciais do Supabase nao configuradas no .env")
        return
        
    email = "contato@candidaturacerta.com.br"
    password = "Admin@2026Certa!#"
    
    headers = {"apikey": SUPABASE_PUBLISHABLE_KEY}
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers=headers,
            json={"email": email, "password": password}
        )
        if res.status_code in {200, 201}:
            print(f"Sucesso! Admin criado.\nE-mail: {email}\nSenha: {password}")
            
            # Auto-confirm the email if we have SUPABASE_SERVICE_ROLE_KEY
            service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if service_key:
                # Update user to confirmed
                # In Supabase REST API, admin updates require service_role key
                admin_headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
                user_id = res.json().get("id") or res.json().get("user", {}).get("id")
                if user_id:
                    await client.put(
                        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                        headers=admin_headers,
                        json={"email_confirm": True}
                    )
                    print("E-mail confirmado automaticamente via Service Role.")
        else:
            print(f"Falha ao criar admin: {res.text}")

if __name__ == '__main__':
    asyncio.run(create_admin())