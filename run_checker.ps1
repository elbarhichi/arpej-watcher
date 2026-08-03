param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$CheckerPath = Join-Path $ProjectDirectory "arpej_checker.py"
$Arguments = @()
if ($Force) {
    $Arguments += "--force"
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $CheckerPath @Arguments
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $CheckerPath @Arguments
}
elseif (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
    & wsl.exe --cd $ProjectDirectory python3 ./arpej_checker.py @Arguments
}
else {
    throw "Python 3 et WSL sont introuvables. Installez Python puis relancez ce script."
}

exit $LASTEXITCODE
