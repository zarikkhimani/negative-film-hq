param([switch]$Experimental)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$compilerPath = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compilerPath)) { throw 'The Windows .NET Framework C# compiler is missing.' }
$outputDir = Join-Path $projectDir 'bin'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$tiffLibrary = Join-Path $projectDir 'vendor\libtiff\lib\netstandard2.0\BitMiracle.LibTiff.NET.dll'
if (-not (Test-Path -LiteralPath $tiffLibrary)) { throw 'The project-local LibTiff.NET dependency is missing.' }
$outputName = if ($Experimental) { 'FilmDesk.HeadlessTest.exe' } else { 'FilmDesk.exe' }
& $compilerPath /nologo /target:winexe /platform:x86 /optimize+ /warn:4 /out:"$outputDir\$outputName" /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:"$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\netstandard.dll" /r:"$tiffLibrary" "$projectDir\ScanDesk.cs" "$projectDir\Twain.cs" "$projectDir\FilmForm.cs" "$projectDir\FilmPreset.cs" "$projectDir\Tiff48.cs" "$projectDir\Tests.cs" "$projectDir\Headless.cs"
if ($LASTEXITCODE -ne 0) { throw 'ScanDesk compilation failed.' }
Copy-Item -LiteralPath (Join-Path $projectDir 'ScanDesk.exe.config') -Destination (Join-Path $outputDir "$outputName.config") -Force
$installedTiff = Join-Path $outputDir 'BitMiracle.LibTiff.NET.dll'
if (-not (Test-Path -LiteralPath $installedTiff) -or (Get-FileHash -LiteralPath $installedTiff).Hash -ne (Get-FileHash -LiteralPath $tiffLibrary).Hash) {
    Copy-Item -LiteralPath $tiffLibrary -Destination $outputDir -Force
}
Write-Output "Built $outputDir\$outputName"
