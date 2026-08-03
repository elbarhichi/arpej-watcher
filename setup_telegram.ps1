$ErrorActionPreference = "Stop"

$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL est introuvable sur cette machine."
}

& wsl.exe --cd $ProjectDirectory python3 ./setup_telegram.py
exit $LASTEXITCODE
