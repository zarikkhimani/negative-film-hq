$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build.ps1')
$appPath = Join-Path $PSScriptRoot 'bin\FilmDesk.exe'
foreach ($diagnostic in @('--self-test', '--probe')) {
    $diagnosticProcess = Start-Process -FilePath $appPath -ArgumentList $diagnostic -WindowStyle Hidden -Wait -PassThru
    $reportName = if ($diagnostic -eq '--probe') { 'scanner-probe.txt' } else { 'self-test.txt' }
    Get-Content -LiteralPath (Join-Path $PSScriptRoot "test-output\$reportName")
    if ($diagnosticProcess.ExitCode -ne 0) { throw "$diagnostic failed with exit code $($diagnosticProcess.ExitCode)." }
}
