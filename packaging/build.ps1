<#
gamma — derleme betiği
  1) Bağımlılıkları kurar (isteğe bağlı)
  2) PyInstaller ile build\dist\gamma\ klasörünü üretir
  3) VLC'yi (libvlc + eklentiler) uygulamanın içine gömer -> kullanıcı ayrıca VLC kurmaz
  4) Taşınabilir zip ve Inno Setup ile kurulum dosyası üretir

Kullanım (proje kökünden):
  powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-InstallDeps] [-NoVlc] [-VlcDir "C:\Program Files\VideoLAN\VLC"] [-SkipInstaller]
#>
param(
    [switch]$InstallDeps,
    [switch]$NoVlc,
    [string]$VlcDir = "C:\Program Files\VideoLAN\VLC",
    [switch]$SkipInstaller,
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

if ($InstallDeps) {
    Step "Bağımlılıklar kuruluyor"
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r requirements.txt pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install başarısız" }
}

Step "Sürüm bilgisi üretiliyor"
$Version = (& $Python packaging\make_meta.py).Trim()
if ($LASTEXITCODE -ne 0) { throw "make_meta.py başarısız" }
Write-Host "Sürüm: $Version"

Step "PyInstaller"
$Dist = Join-Path $Root "build\dist"
& $Python -m PyInstaller packaging\gamma.spec --noconfirm --clean --distpath $Dist --workpath (Join-Path $Root "build\work")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız" }
$App = Join-Path $Dist "gamma"

if (-not $NoVlc) {
    Step "VLC gömülüyor ($VlcDir)"
    if (-not (Test-Path (Join-Path $VlcDir "libvlc.dll"))) {
        throw "VLC bulunamadı: $VlcDir  (64-bit VLC kurun veya -VlcDir verin, ya da -NoVlc kullanın)"
    }
    $Target = Join-Path $App "vlc"
    New-Item -ItemType Directory -Force $Target | Out-Null
    Copy-Item (Join-Path $VlcDir "libvlc.dll"), (Join-Path $VlcDir "libvlccore.dll") $Target -Force
    # VLC'nin kendi arayüzü, betik dili ve uzaktan kontrol eklentileri gerekmiyor
    $Skip = @("gui", "lua", "control", "services_discovery", "visualization")
    Get-ChildItem (Join-Path $VlcDir "plugins") -Directory | Where-Object { $Skip -notcontains $_.Name } | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $Target "plugins\$($_.Name)") -Recurse -Force
    }
    foreach ($f in @("COPYING.txt", "AUTHORS.txt")) {
        $src = Join-Path $VlcDir $f
        if (Test-Path $src) { Copy-Item $src (Join-Path $Target "VLC-$f") -Force }
    }
}

Copy-Item LICENSE (Join-Path $App "LICENSE.txt") -Force

Step "STEP / IGES motoru (isteğe bağlı bileşen: build\dist\gamma\step)"
# gmsh = OpenCASCADE CAD çekirdeği, tek DLL. Kurulumda "STEP / IGES desteği" seçilirse kurulur.
$GmshInfo = & $Python -c "import gmsh; print(gmsh.__file__); print(gmsh.libpath)"
if ($LASTEXITCODE -ne 0 -or -not $GmshInfo) {
    Write-Warning "gmsh bulunamadı; STEP desteği pakete girmedi. Kurmak için:  $Python -m pip install gmsh"
} else {
    $StepDir = Join-Path $App "step"
    New-Item -ItemType Directory -Force $StepDir | Out-Null
    Copy-Item $GmshInfo[0], $GmshInfo[1] $StepDir -Force
    Write-Host ("  " + ((Get-ChildItem $StepDir | Measure-Object Length -Sum).Sum / 1MB).ToString("0") + " MB")
}

Step "Gezgin 3D küçük resim sağlayıcısı (GammaThumbs.dll)"
# .NET Framework 4 her Windows 10/11'de var; ayrıca SDK gerekmez
$Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$ThumbOut = "/out:" + (Join-Path $App "GammaThumbs.dll")
& $Csc /nologo /target:library /optimize+ /r:System.Drawing.dll $ThumbOut packaging\thumbnail\GammaThumbs.cs
if ($LASTEXITCODE -ne 0) { throw "GammaThumbs.dll derlenemedi" }

Step "Taşınabilir zip"
$Out = Join-Path $Root "build\installer"
New-Item -ItemType Directory -Force $Out | Out-Null
$Zip = Join-Path $Out "gamma-portable-$Version.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path $App -DestinationPath $Zip -CompressionLevel Optimal
Write-Host $Zip

if (-not $SkipInstaller) {
    Step "Inno Setup ile kurulum dosyası"
    $Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $Iscc) {
        foreach ($c in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                         "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
            if (Test-Path $c) { $Iscc = $c; break }
        }
    }
    if (-not $Iscc) {
        Write-Warning "Inno Setup 6 bulunamadı; kurulum dosyası atlandı. Kurmak için:  winget install JRSoftware.InnoSetup"
    } else {
        & $Iscc packaging\installer.iss
        if ($LASTEXITCODE -ne 0) { throw "ISCC başarısız" }
    }
}

Step "Bitti"
Get-ChildItem $Out | Format-Table Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
