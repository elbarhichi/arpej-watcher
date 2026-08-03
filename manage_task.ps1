param(
    [ValidateSet("status", "pause", "resume", "run")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$TaskName = "ARPEJ - Verification des disponibilites"

switch ($Action) {
    "pause" {
        Disable-ScheduledTask -TaskName $TaskName | Out-Null
        Write-Host "Surveillance ARPEJ mise en pause."
    }
    "resume" {
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        Write-Host "Surveillance ARPEJ reactivee."
    }
    "run" {
        $ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
        $RunnerPath = Join-Path $ProjectDirectory "run_checker.ps1"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RunnerPath -Force
        if (-not $?) {
            throw "Le controle ARPEJ manuel a echoue."
        }
        Write-Host "Controle ARPEJ manuel termine."
    }
    "status" {
        $Task = Get-ScheduledTask -TaskName $TaskName
        $Info = Get-ScheduledTaskInfo -TaskName $TaskName
        $Task | Format-List TaskName, State
        $Info | Format-List NextRunTime, LastRunTime, LastTaskResult
    }
}
