# Publicacao no Render

O sistema usa o Render como aplicacao web e o Supabase como PostgreSQL e autenticacao.
Nenhum segredo deve ser salvo no Git.

## 1. Criar o servico

No Render, crie um Blueprint a partir deste repositorio GitHub. O arquivo
`render.yaml` define o build, o comando de inicializacao e a verificacao de saude.

## 2. Definir os segredos no Render

Configure no servico:

- `DATABASE_URL`: conexao PostgreSQL do Supabase.
- `SUPABASE_URL`: Project URL do Supabase.
- `SUPABASE_PUBLISHABLE_KEY`: chave publicavel do Supabase.
- `APP_BASE_URL`: URL HTTPS final do servico Render, sem barra no final.

O Blueprint fixa `AUTH_REQUIRED=true` e `COOKIE_SECURE=true`.

## 3. Configurar URLs no Supabase

Em Authentication > URL Configuration:

- Site URL: o mesmo valor de `APP_BASE_URL`.
- Redirect URL: `APP_BASE_URL` seguido de `/dashboard`.

Nao adicione enderecos `localhost` ou `127.0.0.1` na configuracao de producao.

## 4. Validar

Depois do deploy, confirme:

- `/health` responde com `{"status":"healthy"}`.
- `/dashboard` abre a tela de login.
- um novo usuario recebe o e-mail de confirmacao.
- o link do e-mail retorna para `/dashboard` no dominio Render.
- usuarios diferentes nao visualizam dados uns dos outros.

## 5. Gmail opcional

Ao ativar a integracao Gmail, configure no Render as variaveis listadas em
`.env.example` e cadastre `APP_BASE_URL/auth/gmail/callback` como redirect URI no
Google Cloud Console.
