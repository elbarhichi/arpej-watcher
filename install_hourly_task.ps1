$ErrorActionPreference = "Stop"

$TaskName = "ARPEJ - Verification des disponibilites"
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunnerPath = Join-Path $ProjectDirectory "run_checker.ps1"

if (-not (Test-Path $RunnerPath)) {
    throw "Script de lancement introuvable : $RunnerPath"
}

$ActionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerPath`""
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ActionArguments
$Triggers = @()
foreach ($Hour in 8..18) {
    $Triggers += New-ScheduledTaskTrigger -Daily -At ("{0:D2}:00" -f $Hour)
}
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Triggers `
    -Settings $Settings `
    -Description "Verifie les disponibilites ARPEJ chaque heure de 08h00 a 18h00." `
    -Force | Out-Null

Write-Host "Tache installee : $TaskName"
Write-Host "Controles quotidiens programmes chaque heure de 08h00 a 18h00 inclus."
