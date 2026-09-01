$ErrorActionPreference = "Stop"

function Read-SecretText {
    param([Parameter(Mandatory = $true)][string]$Prompt)

    $secureValue = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Set-UserEnvironmentVariable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    Set-Item -Path "Env:$Name" -Value $Value
}

Write-Host ""
Write-Host "Configuracao segura do Supabase"
Write-Host "Os valores sensiveis nao serao exibidos."
Write-Host ""

$supabaseUrlInput = (Read-Host "Project URL ou Data API URL").Trim()
try {
    $parsedSupabaseUrl = [Uri]$supabaseUrlInput
}
catch {
    throw "URL invalida. Copie novamente o campo Project URL ou Data API URL."
}
if (
    $parsedSupabaseUrl.Scheme -ne "https" -or
    -not $parsedSupabaseUrl.Host.EndsWith(".supabase.co")
) {
    throw "URL invalida. Ela deve usar HTTPS e terminar em .supabase.co."
}
$allowedPaths = @("/", "/rest/v1", "/rest/v1/")
if ($parsedSupabaseUrl.AbsolutePath -notin $allowedPaths) {
    throw "URL invalida. Use a Project URL ou Data API URL, nao o endereco do dashboard."
}
$supabaseUrl = "https://$($parsedSupabaseUrl.Host)"

$publishableKey = Read-SecretText "Publishable key"
if ([string]::IsNullOrWhiteSpace($publishableKey)) {
    throw "Publishable key nao pode ficar vazia."
}

Write-Host ""
Write-Host "No Supabase, abra Connect > Session pooler."
Write-Host "Copie a connection string e substitua [YOUR-PASSWORD] pela senha do banco."
$databaseUrl = Read-SecretText "DATABASE_URL completa"
if ($databaseUrl -notmatch '^postgres(ql)?://') {
    throw "DATABASE_URL invalida. Ela deve comecar com postgres:// ou postgresql://."
}
if ($databaseUrl.Contains("[YOUR-PASSWORD]")) {
    throw "Substitua [YOUR-PASSWORD] pela senha real do banco antes de continuar."
}

Set-UserEnvironmentVariable "SUPABASE_URL" $supabaseUrl
Set-UserEnvironmentVariable "SUPABASE_PUBLISHABLE_KEY" $publishableKey
Set-UserEnvironmentVariable "DATABASE_URL" $databaseUrl
Set-UserEnvironmentVariable "AUTH_REQUIRED" "true"
Set-UserEnvironmentVariable "COOKIE_SECURE" "false"

Write-Host ""
Write-Host "Configuracao salva no usuario do Windows."
Write-Host "AUTH_REQUIRED=true"
Write-Host "COOKIE_SECURE=false (correto para teste local em HTTP)"
Write-Host "Nenhuma chave ou senha foi exibida."
