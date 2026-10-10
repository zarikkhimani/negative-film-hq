param([switch]$SwinIR)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$photoRoot = Split-Path -Parent $projectRoot
$python = Join-Path $photoRoot 'FreeCCR\.venv\Scripts\python.exe'
$testRoot = Join-Path $projectRoot 'test-output'
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$runDirectory = Join-Path $testRoot ('pytest-' + [Guid]::NewGuid().ToString('N'))
& $python -m pytest (Join-Path $projectRoot 'tests') -q --basetemp $runDirectory
if ($LASTEXITCODE -ne 0) { throw 'NegativeLab file/precision tests failed.' }
& $python (Join-Path $projectRoot 'smoke_test.py')
if ($LASTEXITCODE -ne 0) { throw 'NegativeLab GUI/converter smoke test failed.' }
if ($SwinIR) {
    & $python (Join-Path $projectRoot 'swinir_smoke_test.py')
    if ($LASTEXITCODE -ne 0) { throw 'NegativeLab SwinIR GPU smoke test failed.' }
}
