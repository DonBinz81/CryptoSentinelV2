param(
    [int]$Port = 5176
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Get-DashboardPortProcess {
    param([int]$Port)

    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            Get-Process -Id $_ -ErrorAction SilentlyContinue
        }
}

function Get-TailscaleIp {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -like "100.*" -and $_.InterfaceAlias -like "*Tailscale*" } |
        Select-Object -ExpandProperty IPAddress -First 1
}

try {
    Set-Location $RepoRoot
    Write-Host "CryptoSentinel dashboard start" -ForegroundColor Cyan
    Write-Host "Repository: $RepoRoot"
    Write-Host "Port: $Port"

    $running = @(Get-DashboardPortProcess -Port $Port)
    if ($running.Count -gt 0) {
        Write-Host "Dashboard port $Port is already in use. Use scripts\restart_dashboard.ps1 to restart it." -ForegroundColor Yellow
        $running | Select-Object Id, ProcessName, Path | Format-Table -AutoSize
        Read-Host "Press Enter to close this window"
        exit 1
    }

    $tailscaleIp = Get-TailscaleIp
    Write-Host "Starting dashboard on all interfaces (0.0.0.0:$Port)" -ForegroundColor Green
    Write-Host "Local URL: http://127.0.0.1:$Port"
    if ($tailscaleIp) {
        Write-Host "Tailscale URL: http://$tailscaleIp`:$Port" -ForegroundColor Green
    }
    & npm.cmd run dashboard:dev
}
catch {
    Write-Host "Dashboard start failed: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Press Enter to close this window"
    exit 1
}
finally {
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        Read-Host "Dashboard process exited. Press Enter to close this window"
    }
}
