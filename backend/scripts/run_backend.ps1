<#
.SYNOPSIS
    Avvia il backend CryptoSentinel con Uvicorn.

.PARAMETER Dev
    Abilita --reload di Uvicorn (solo sviluppo locale, non usare in produzione).

.EXAMPLE
    .\backend\scripts\run_backend.ps1
    .\backend\scripts\run_backend.ps1 -Dev
#>
param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"

# Radice del progetto = due livelli sopra backend/scripts/
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $BackendDir

# Attiva il virtualenv se presente
$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    . $VenvActivate
} else {
    Write-Warning "Virtualenv non trovato in $BackendDir\.venv -- uso il Python di sistema."
}

# Imposta PYTHONPATH cosi' Python trova il package backend
$env:PYTHONPATH = $ProjectRoot

# Legge host e porta dalle Settings (instance.yaml + env) senza duplicare valori
$HostPort = python -c "from backend.app.core.config import get_settings; s=get_settings(); print(s.api_host, s.api_port)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Impossibile leggere la configurazione."
    exit 1
}
$Parts   = $HostPort.Trim().Split(' ')
$ApiHost = $Parts[0]
$ApiPort = $Parts[1]

function Stop-ExistingBackendOnPort {
    param(
        [Parameter(Mandatory=$true)]
        [int]$Port
    )

    $listeners = netstat -ano 2>$null |
        Select-String ":$Port\s" |
        Select-String "LISTENING"
    if (-not $listeners) {
        return
    }

    foreach ($line in $listeners) {
        $parts = ($line -replace '\s+', ' ').Trim().Split(' ')
        $processId = [int]$parts[-1]
        if ($processId -le 0 -or $processId -eq $PID) {
            continue
        }
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Porta $Port gia' occupata da PID $processId ($($proc.ProcessName)): terminazione prima del riavvio..."
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 250
        $stillListening = netstat -ano 2>$null |
            Select-String ":$Port\s" |
            Select-String "LISTENING"
        if (-not $stillListening) {
            return
        }
    }

    throw "La porta $Port risulta ancora occupata dopo il tentativo di stop."
}

$DevLabel = if ($Dev) { ' [DEV - reload attivo]' } else { '' }
Write-Host "Avvio backend su $ApiHost`:$ApiPort$DevLabel"
Stop-ExistingBackendOnPort -Port ([int]$ApiPort)

$UvicornArgs = @(
    "-m", "uvicorn",
    "backend.app.main:app",
    "--host", $ApiHost,
    "--port", $ApiPort
)
if ($Dev) {
    $UvicornArgs += "--reload"
}

Set-Location $ProjectRoot

# Su Windows, Ctrl+C in terminali embedded non viene sempre propagato al
# processo figlio. Registriamo un handler esplicito che termina Python.
$global:BackendProc = $null
[Console]::TreatControlCAsInput = $false

try {
    $global:BackendProc = Start-Process -FilePath python -ArgumentList $UvicornArgs `
        -NoNewWindow -PassThru
    $global:BackendProc.WaitForExit()
} finally {
    if ($global:BackendProc -and -not $global:BackendProc.HasExited) {
        Write-Host "`nInterruzione backend (PID $($global:BackendProc.Id))..."
        $global:BackendProc.Kill($true)   # $true = includi processi figli (reload workers)
    }
}
