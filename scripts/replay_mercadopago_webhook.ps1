param(
    [string]$PaymentId
)

$ErrorActionPreference = 'Stop'

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDirectory 'replay_mercadopago_webhook.py'
$projectRoot = Split-Path -Parent $scriptDirectory
$pythonArguments = @()
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonOnPath = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$pyLauncher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$codexPython = if ($env:USERPROFILE) {
    Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
} else {
    $null
}

if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
    $pythonExecutable = $projectPython
} elseif ($pythonOnPath) {
    $pythonExecutable = $pythonOnPath.Source
} elseif ($pyLauncher) {
    $pythonExecutable = $pyLauncher.Source
    $pythonArguments = @('-3')
} elseif ($codexPython -and (Test-Path -LiteralPath $codexPython -PathType Leaf)) {
    $pythonExecutable = $codexPython
} else {
    throw 'Python 3 nao foi encontrado; nenhum webhook foi enviado.'
}

if (-not (Test-Path -LiteralPath $pythonScript -PathType Leaf)) {
    throw 'O verificador de webhook nao foi encontrado; nenhum webhook foi enviado.'
}

$paymentId = if ([string]::IsNullOrWhiteSpace($PaymentId)) {
    Read-Host 'ID do pagamento ja aprovado no Mercado Pago'
} else {
    $PaymentId
}
if ([string]::IsNullOrWhiteSpace($paymentId)) {
    throw 'O ID ficou vazio; nenhum webhook foi enviado.'
}

$secureSecret = Read-Host 'NOVO segredo do webhook salvo no Render (entrada oculta)' -AsSecureString
if ($secureSecret.Length -eq 0) {
    throw 'O segredo ficou vazio; nenhum webhook foi enviado.'
}

$secretPointer = [IntPtr]::Zero
$secretValue = $null
$previousUrl = $env:MERCADOPAGO_WEBHOOK_URL
$previousSecret = $env:MERCADOPAGO_WEBHOOK_SECRET
$previousPaymentId = $env:MERCADOPAGO_PAYMENT_ID
try {
    $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
    $secretValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
    $env:MERCADOPAGO_WEBHOOK_URL = 'https://candidaturacerta.com.br/webhooks/mercadopago'
    $env:MERCADOPAGO_WEBHOOK_SECRET = $secretValue
    $env:MERCADOPAGO_PAYMENT_ID = $paymentId.Trim()

    & $pythonExecutable @pythonArguments $pythonScript
    if ($LASTEXITCODE -ne 0) {
        throw 'Replay nao confirmou assinatura e idempotencia. Veja o resumo acima; nenhum corpo integral foi exibido.'
    }
}
finally {
    if ($secretPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
    }
    $secretValue = $null
    if ($null -eq $previousUrl) { Remove-Item Env:MERCADOPAGO_WEBHOOK_URL -ErrorAction SilentlyContinue } else { $env:MERCADOPAGO_WEBHOOK_URL = $previousUrl }
    if ($null -eq $previousSecret) { Remove-Item Env:MERCADOPAGO_WEBHOOK_SECRET -ErrorAction SilentlyContinue } else { $env:MERCADOPAGO_WEBHOOK_SECRET = $previousSecret }
    if ($null -eq $previousPaymentId) { Remove-Item Env:MERCADOPAGO_PAYMENT_ID -ErrorAction SilentlyContinue } else { $env:MERCADOPAGO_PAYMENT_ID = $previousPaymentId }
}
