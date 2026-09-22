param(
    [string]$BaseUrl = "https://candidaturacerta.com.br"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

function Invoke-PublicProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateSet("GET", "POST")][string]$Method = "GET",
        [string]$Body = ""
    )

    $url = "$BaseUrl$Path"
    $request = @{
        UseBasicParsing = $true
        MaximumRedirection = 0
        Uri = $url
        ErrorAction = "Stop"
        Method = $Method
    }
    if ($Method -eq "POST") {
        $request.Body = $Body
        $request.ContentType = "application/json"
    }
    try {
        $response = Invoke-WebRequest @request
        return [pscustomobject]@{
            path = $Path
            status = [int]$response.StatusCode
            content_type = [string]$response.Headers["Content-Type"]
            cache_control = [string]$response.Headers["Cache-Control"]
            hsts = [string]$response.Headers["Strict-Transport-Security"]
            csp = [string]$response.Headers["Content-Security-Policy"]
            body = [string]$response.Content
        }
    } catch {
        $response = $_.Exception.Response
        if (-not $response) {
            return [pscustomobject]@{
                path = $Path; status = 0; content_type = ""; cache_control = ""; hsts = ""; csp = ""; body = ""
            }
        }
        $body = ""
        try {
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
            $body = $reader.ReadToEnd()
            $reader.Dispose()
        } catch { }
        return [pscustomobject]@{
            path = $Path
            status = [int]$response.StatusCode
            content_type = [string]$response.Headers["Content-Type"]
            cache_control = [string]$response.Headers["Cache-Control"]
            hsts = [string]$response.Headers["Strict-Transport-Security"]
            csp = [string]$response.Headers["Content-Security-Policy"]
            body = $body
        }
    }
}

function Add-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Evidence
    )
    $script:checks += [pscustomobject]@{
        check = $Name
        result = if ($Passed) { "OK" } else { "FALHA" }
        evidence = $Evidence
    }
}

$checks = @()
$health = Invoke-PublicProbe "/health"
$landing = Invoke-PublicProbe "/"
$robots = Invoke-PublicProbe "/robots.txt"
$terms = Invoke-PublicProbe "/termos"
$privacy = Invoke-PublicProbe "/privacidade"
$protected = Invoke-PublicProbe "/perfil"
$webhook = Invoke-PublicProbe "/webhooks/mercadopago" "POST" "{}"
$zip = Invoke-PublicProbe "/static/candidatura-certa-autopreenchimento.zip?v=11"

Add-Check "health" ($health.status -eq 200 -and $health.body -match '"status"\s*:\s*"ok"') "HTTP $($health.status); banco saudavel"
Add-Check "landing" ($landing.status -eq 200 -and $landing.body -match "Candidatura Certa") "HTTP $($landing.status); marca presente"
Add-Check "robots" ($robots.status -eq 200 -and $robots.body -match "User-agent: \*" -and $robots.body -match "Disallow: /api/") "HTTP $($robots.status); politica publica presente"
Add-Check "termos" ($terms.status -eq 200 -and $terms.body -match "Termos de Uso") "HTTP $($terms.status)"
Add-Check "privacidade" ($privacy.status -eq 200 -and $privacy.body -match "Privacidade") "HTTP $($privacy.status)"
Add-Check "protected_headers" ($protected.status -eq 401 -and $protected.cache_control -match "no-store" -and $protected.hsts -match "max-age" -and $protected.csp) "HTTP $($protected.status); resposta protegida sem cache"
Add-Check "webhook_fail_closed" ($webhook.status -eq 401) "HTTP $($webhook.status); assinatura ausente rejeitada"
Add-Check "copilot_zip" ($zip.status -eq 200 -and $zip.content_type -match "application/zip") "HTTP $($zip.status); ZIP disponivel"

$checks | Format-Table -AutoSize
$failed = @($checks | Where-Object { $_.result -ne "OK" })
if ($failed.Count -gt 0) {
    Write-Error "$($failed.Count) verificacao(oes) publica(s) falharam."
    exit 1
}

Write-Output "Todas as verificacoes publicas passaram. Nenhum segredo foi usado."
