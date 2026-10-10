# PaleoSphere 로컬 데모: sim 서버를 띄우고 Godot 뷰어를 연다.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Godot C:\tools\godot\Godot_v4.7.2-stable_win64.exe
# Godot을 찾지 못하면 브라우저 뷰어(http://127.0.0.1:<port>/)를 연다.
param(
    [string]$Godot = $env:GODOT_BIN,
    [int]$Port = 8790
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $Godot) {
    $cmd = Get-Command godot -ErrorAction SilentlyContinue
    if ($cmd) { $Godot = $cmd.Source }
}
if (-not $Godot) {
    $candidate = Get-ChildItem "$env:USERPROFILE\tools\godot\Godot_v4*_win64.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "*console*" } | Select-Object -First 1
    if ($candidate) { $Godot = $candidate.FullName }
}

Write-Host "sim 서버 시작: http://127.0.0.1:$Port"
$server = Start-Process -FilePath "uv" -ArgumentList @("run", "python", "-m", "app", "--port", "$Port") `
    -WorkingDirectory $root -PassThru -WindowStyle Minimized

try {
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 1 | Out-Null
            $ready = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw "서버가 시작되지 않았습니다." }

    if ($Godot) {
        Write-Host "Godot 뷰어 실행: $Godot"
        & $Godot --path "$root\godot" -- "--server=ws://127.0.0.1:$Port/ws/sim"
    } else {
        Write-Host "Godot을 찾지 못해 브라우저 뷰어를 엽니다. 종료하려면 Ctrl+C."
        Start-Process "http://127.0.0.1:$Port/"
        Wait-Process -Id $server.Id
    }
} finally {
    if (-not $server.HasExited) {
        # uv가 띄운 python 자식 프로세스까지 정리
        taskkill /PID $server.Id /T /F | Out-Null
    }
}
