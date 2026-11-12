; gamma — Inno Setup 6 kurulum betiği
; Doğrudan değil, packaging\build.ps1 üzerinden derleyin (önce PyInstaller çıktısı ve extensions.iss gerekir).

#include "version.iss"
#define AppName "gamma"
#define AppExe "gamma.exe"

[Setup]
AppId={{6F1C2B8E-4A7D-4E2B-9C61-0A9D3E5B7C21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Yiğit Özsoy
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\build\installer
OutputBaseFilename=gamma-setup-{#AppVersion}
SetupIconFile=..\gammaplayer\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
turkish.ShellGroup=Windows entegrasyonu:
english.ShellGroup=Windows integration:
turkish.TaskContext=Sağ tık menüsüne "Open with gamma player" ekle (medya dosyaları ve klasörler)
english.TaskContext=Add "Open with gamma player" to the right-click menu (media files and folders)
turkish.OpenWith=Open with gamma player
english.OpenWith=Open with gamma player
turkish.Desc=Video, müzik ve görselleri açan evrensel medya oynatıcı
english.Desc=Universal media player for video, music and images

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "{cm:TaskContext}"; GroupDescription: "{cm:ShellGroup}"

[Files]
Source: "..\build\dist\gamma\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Uygulama kaydı ("Birlikte aç" listesi ve Varsayılan uygulamalar ayarı)
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\gamma"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\gamma\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"
Root: HKA; Subkey: "Software\gamma\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{cm:Desc}"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "gamma"; ValueData: "Software\gamma\Capabilities"; Flags: uninsdeletevalue

; ProgID'ler
Root: HKA; Subkey: "Software\Classes\gamma.video"; ValueType: string; ValueData: "Video (gamma)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\gamma.video\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\gamma.video\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\gamma.audio"; ValueType: string; ValueData: "Ses (gamma)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\gamma.audio\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\gamma.audio\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\gamma.image"; ValueType: string; ValueData: "Görsel (gamma)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\gamma.image\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\gamma.image\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""

; Sağ tık menüsü (isteğe bağlı görev)
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\GammaPlayer"; ValueType: string; ValueData: "{cm:OpenWith}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\GammaPlayer"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\video\shell\GammaPlayer\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\GammaPlayer"; ValueType: string; ValueData: "{cm:OpenWith}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\GammaPlayer"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\audio\shell\GammaPlayer\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\image\shell\GammaPlayer"; ValueType: string; ValueData: "{cm:OpenWith}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\image\shell\GammaPlayer"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\image\shell\GammaPlayer\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\GammaPlayer"; ValueType: string; ValueData: "{cm:OpenWith}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Directory\shell\GammaPlayer"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe}"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\GammaPlayer\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu

; Uzantı başına "Birlikte aç" kayıtları (make_meta.py üretir)
#include "extensions_registry.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
