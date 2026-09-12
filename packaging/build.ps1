$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Packaging = Join-Path $Root "packaging"
$Dist = Join-Path $Root "dist"
$Python = (Get-Command python).Source

Write-Host "==> Generating application icon"
& $Python (Join-Path $Packaging "generate_icon.py") | Out-Host

Write-Host "==> Installing PyInstaller"
& $Python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib | Out-Host

Write-Host "==> Building QuantTerminal.exe (this can take several minutes)"
$Spec = Join-Path $Packaging "quant_terminal.spec"
& $Python -m PyInstaller --noconfirm --clean $Spec | Out-Host

$AppDir = Join-Path $Dist "QuantTerminal"
if (-not (Test-Path (Join-Path $AppDir "QuantTerminal.exe"))) {
    throw "Build failed: QuantTerminal.exe was not created."
}

Copy-Item (Join-Path $Packaging "install.ps1") (Join-Path $AppDir "install.ps1") -Force
Copy-Item (Join-Path $Packaging "Install.bat") (Join-Path $AppDir "Install.bat") -Force

$Iscc = @(
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Iscc) {
    Write-Host "==> Installing Inno Setup compiler"
    $InnoExe = Join-Path $env:TEMP "innosetup-6.7.3.exe"
    $Urls = @(
        "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe",
        "https://jrsoftware.org/download.php/is.exe"
    )
    $ok = $false
    foreach ($url in $Urls) {
        try {
            Invoke-WebRequest -Uri $url -OutFile $InnoExe -UseBasicParsing
            $ok = $true
            break
        } catch {
            Write-Host "Download failed from $url"
        }
    }
    if (-not $ok) { throw "Could not download Inno Setup." }
    $InnoDir = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6"
    Start-Process -FilePath $InnoExe -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/SP-","/DIR=`"$InnoDir`"" -Wait
    $Iscc = Join-Path $InnoDir "ISCC.exe"
}

if (-not (Test-Path $Iscc)) {
    throw "ISCC.exe not found after Inno Setup install."
}

Write-Host "==> Compiling Windows installer"
& $Iscc (Join-Path $Packaging "installer.iss") | Out-Host

$Setup = Join-Path $Dist "QuantTerminalSetup.exe"
if (-not (Test-Path $Setup)) {
    throw "Installer was not created."
}

Write-Host ""
Write-Host "DONE"
Write-Host "Installer: $Setup"
Write-Host "Portable folder: $AppDir"
Write-Host "Send QuantTerminalSetup.exe to another PC and run it."
