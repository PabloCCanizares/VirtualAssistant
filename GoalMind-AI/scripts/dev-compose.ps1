param(
    [switch]$NoBuild,
    [switch]$Logs,
    [int]$TimeoutSeconds = 90,
    [string]$HealthUrl = "http://127.0.0.1:5000/"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$DevComposeFile = Join-Path $ProjectRoot "docker-compose.dev.yml"

if (-not (Test-Path $ComposeFile)) {
    throw "No se encontro docker-compose.yml en $ProjectRoot"
}
if (-not (Test-Path $DevComposeFile)) {
    throw "No se encontro docker-compose.dev.yml en $ProjectRoot"
}

function Invoke-DockerCompose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker compose -f $ComposeFile -f $DevComposeFile @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose fallo con codigo $LASTEXITCODE"
    }
}

Write-Host "Proyecto: $ProjectRoot"
Write-Host "Modo:     desarrollo con codigo montado en vivo"

$upArgs = @("up", "-d", "--force-recreate", "--remove-orphans")
if (-not $NoBuild) {
    $upArgs += "--build"
}

Invoke-DockerCompose @upArgs

Write-Host "Esperando respuesta en $HealthUrl ..."
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$lastError = $null

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            Write-Host "Aplicacion dev disponible: $HealthUrl"
            if ($Logs) {
                Invoke-DockerCompose logs --tail 80 app
            }
            exit 0
        }
    }
    catch {
        $lastError = $_.Exception.Message
    }
    Start-Sleep -Seconds 2
}

Write-Warning "La aplicacion no respondio antes de $TimeoutSeconds segundos."
if ($lastError) {
    Write-Warning $lastError
}

Invoke-DockerCompose ps
Invoke-DockerCompose logs --tail 120 app
exit 1
