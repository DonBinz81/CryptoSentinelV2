<#
.SYNOPSIS
    Termina il processo backend CryptoSentinel (uvicorn/Python su porta 8001).
#>

$killed = $false

# Cerca per porta 8001 (modo più affidabile su Windows)
$port = 8001
$lines = netstat -ano 2>$null | Select-String ":$port\s" | Select-String "LISTENING"
foreach ($line in $lines) {
    $parts = ($line -replace '\s+', ' ').Trim().Split(' ')
    $ProcessId = [int]$parts[-1]
    if ($ProcessId -gt 0) {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Terminazione PID $ProcessId ($($proc.ProcessName)) su porta $port..."
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
            $killed = $true
        }
    }
}

if (-not $killed) {
    Write-Host "Nessun processo in ascolto sulla porta $port trovato."
} else {
    Write-Host "Backend terminato."
}
