# PaleoSphere 로컬 데모: sim 서버를 띄우고 Godot 3D 탐험 뷰어를 연다.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1            # 3D 1인칭 탐험
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -View2D    # 2D 관찰 뷰어 (정책·맵 선택, 그래프)
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Godot C:\tools\godot\Godot_v4.7.2-stable_win64.exe
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Smoke     # 창 없이 연결 검사 후 종료
# Godot을 찾지 못하면 브라우저 뷰어(http://127.0.0.1:<port>/)를 연다.
param(
    [string]$Godot = $env:GODOT_BIN,
    [int]$Port = 8790,
    [switch]$View2D,
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$scene = @()
if (-not $View2D) { $scene = @("res://scenes/explore3d.tscn") }

if (-not $Godot) {
    $cmd = Get-Command godot -ErrorAction SilentlyContinue
    if ($cmd) { $Godot = $cmd.Source }
}
if (-not $Godot) {
    # -Smoke는 출력을 받으려고 console 빌드를 쓴다
    $candidate = Get-ChildItem "$env:USERPROFILE\tools\godot\Godot_v4*_win64*.exe" -ErrorAction SilentlyContinue |
        Where-Object { ($_.Name -like "*console*") -eq [bool]$Smoke } | Select-Object -First 1
    if ($candidate) { $Godot = $candidate.FullName }
}

Write-Host "sim 서버 시작: http://127.0.0.1:$Port"
$server = Start-Process -FilePath "uv" -ArgumentList @("run", "--all-extras", "python", "-m", "app", "--port", "$Port") `
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

    if ($Smoke) {
        if (-not $Godot) { throw "Godot을 찾지 못했습니다." }
        $out = & $Godot --headless --path "$root\godot" @scene -- --smoke "--server=ws://127.0.0.1:$Port/ws/sim" 2>&1
        $out | Select-String "SMOKE" | ForEach-Object { Write-Host $_ }
        if (-not ($out -match "SMOKE OK")) { throw "Godot 스모크 실패" }
    } elseif ($Godot) {
        Write-Host "Godot 뷰어 실행: $Godot $scene"
        # GUI 빌드는 즉시 반환하므로 창이 닫힐 때까지 기다린다 (안 그러면 서버가 바로 꺼짐)
        Start-Process -FilePath $Godot -Wait `
            -ArgumentList (@("--path", "`"$root\godot`"") + $scene + @("--", "--server=ws://127.0.0.1:$Port/ws/sim"))
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
