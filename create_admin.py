import os
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    from dotenv import load_dotenv
    load_dotenv(".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("No Supabase credentials found")
    exit(1)

supabase = create_client(url, key)

try:
    res = supabase.auth.sign_up({
        "email": "contato@candidaturacerta.com.br",
        "password": "Querubim@131",
    })
    print("User created successfully!")
    print(res)
except Exception as e:
    print(f"Error creating user: {e}")
