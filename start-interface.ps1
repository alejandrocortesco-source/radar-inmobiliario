$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$dataPath = Join-Path $projectRoot 'data'
$baseUrl = 'http://127.0.0.1:8000'

function Test-Interface {
    try {
        $health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2
        return $health.status -eq 'ok'
    } catch {
        return $false
    }
}

if (Test-Interface) {
    Write-Output "La interfaz ya responde en $baseUrl"
    exit 0
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'No se encontró .venv. Instala las dependencias siguiendo el README.'
}
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
$serverProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m', 'metro', 'serve' `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $dataPath 'interface.stdout.log') `
    -RedirectStandardError (Join-Path $dataPath 'interface.stderr.log')
$serverProcess.Id | Set-Content -LiteralPath (Join-Path $dataPath 'interface.pid')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if (Test-Interface) {
        Write-Output "Interfaz iniciada: $baseUrl (PID $($serverProcess.Id))"
        exit 0
    }
    if ($serverProcess.HasExited) {
        throw "El servidor terminó. Revisa $dataPath\interface.stderr.log"
    }
    Start-Sleep -Milliseconds 500
}
throw "El servidor no respondió a tiempo. Revisa $dataPath\interface.stderr.log"
