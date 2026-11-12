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
; Yalnızca çalışan .exe'ler kapatılsın. GammaThumbs.dll Gezgin'in içinde yüklü olduğundan varsayılan filtre
; (*.exe,*.dll,*.chm) Gezgin'i kapatmayı öneriyordu; kapatınca masaüstü ve görev çubuğu gidiyor.
; Kilitli DLL'i [Code] içinde kenara alıyoruz (MoveAsideThumbDll).
CloseApplicationsFilter=*.exe
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
turkish.Desc=Video, müzik, görsel ve 3D modelleri açan evrensel medya oynatıcı
english.Desc=Universal media player for video, music, images and 3D models
turkish.StepGroup=Ek bileşenler:
english.StepGroup=Optional components:
turkish.TaskStep=STEP / IGES desteği: CAD dosyalarını aç (yaklaşık 85 MB)
english.TaskStep=STEP / IGES support: open CAD files (about 85 MB)
turkish.AssocNeedsStep=STEP / IGES desteği ile
english.AssocNeedsStep=with STEP / IGES support
turkish.AssocTitle=Dosya türleri
english.AssocTitle=File types
turkish.AssocDesc=gamma hangi dosya türlerini açsın? İstemediklerinin tikini kaldır.
english.AssocDesc=Which file types should gamma open? Untick the ones you don't want.
turkish.AssocAll=Tümünü seç
english.AssocAll=Select all
turkish.AssocNone=Hiçbirini seçme
english.AssocNone=Select none
turkish.AssocVideo=Videolar
english.AssocVideo=Videos
turkish.AssocAudio=Müzik
english.AssocAudio=Music
turkish.AssocImage=Görseller
english.AssocImage=Images
turkish.AssocModel=3D modeller
english.AssocModel=3D models
turkish.RunDefaults=Varsayılan uygulama ayarını aç (seçtiğin türler için "Varsayılan olarak ayarla"ya bas)
english.RunDefaults=Open default app settings (press "Set default" for the selected types)

[Tasks]
; Dosya türü seçimi ayrı sayfada (aşağıdaki [Code]); her uzantı tek tek seçilebilir
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "{cm:TaskContext}"; GroupDescription: "{cm:ShellGroup}"
Name: "step"; Description: "{cm:TaskStep}"; GroupDescription: "{cm:StepGroup}"

[Files]
Source: "..\build\dist\gamma\*"; DestDir: "{app}"; Excludes: "\step\*"; Flags: ignoreversion recursesubdirs createallsubdirs
; İsteğe bağlı STEP / IGES motoru
Source: "..\build\dist\gamma\step\*"; DestDir: "{app}\step"; Tasks: step; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[InstallDelete]
; Güncellemede STEP desteğinden vazgeçildiyse eski motoru kaldır
Type: filesandordirs; Name: "{app}\step"; Tasks: not step

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
Root: HKA; Subkey: "Software\Classes\gamma.model"; ValueType: string; ValueData: "3D model (gamma)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\gamma.model\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\gamma.model\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""

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

; Gezgin'de STL / OBJ küçük resimleri (GammaThumbs.dll, .NET COM sunucusu; regasm gerekmez)
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}"; ValueType: string; ValueData: "gamma 3D thumbnail provider"; Flags: uninsdeletekey
; Yalıtılmış önizleme işlemi kullanıcı başına COM kayıtlarını görmüyor; Microsoft'un 3MF sağlayıcısı gibi Gezgin içinde çalışır
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}"; ValueType: dword; ValueName: "DisableProcessIsolation"; ValueData: 1
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}\InprocServer32"; ValueType: string; ValueData: "mscoree.dll"
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Both"
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}\InprocServer32"; ValueType: string; ValueName: "Class"; ValueData: "GammaThumbs.Provider"
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}\InprocServer32"; ValueType: string; ValueName: "Assembly"; ValueData: "GammaThumbs, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}\InprocServer32"; ValueType: string; ValueName: "RuntimeVersion"; ValueData: "v4.0.30319"
Root: HKA; Subkey: "Software\Classes\CLSID\{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}\InprocServer32"; ValueType: string; ValueName: "CodeBase"; ValueData: "file:///{app}\GammaThumbs.dll"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.stl\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueData: "{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.obj\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueData: "{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.glb\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueData: "{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ply\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueData: "{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.off\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueData: "{{7d1c6a52-3f4e-4b8e-9a51-6b0f2a9c4e31}"; Flags: uninsdeletekey
; .gltf: harici .bin / doku dosyaları yan klasörden okunsun diye dosya yoluyla çalışan ikinci sınıf
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}"; ValueType: string; ValueData: "gamma glTF thumbnail provider"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}"; ValueType: dword; ValueName: "DisableProcessIsolation"; ValueData: 1
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}\InprocServer32"; ValueType: string; ValueData: "mscoree.dll"
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Both"
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}\InprocServer32"; ValueType: string; ValueName: "Class"; ValueData: "GammaThumbs.FileProvider"
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}\InprocServer32"; ValueType: string; ValueName: "Assembly"; ValueData: "GammaThumbs, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null"
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}\InprocServer32"; ValueType: string; ValueName: "RuntimeVersion"; ValueData: "v4.0.30319"
Root: HKA; Subkey: "Software\Classes\CLSID\{{437a1563-8258-4e3c-80de-511965bd614c}\InprocServer32"; ValueType: string; ValueName: "CodeBase"; ValueData: "file:///{app}\GammaThumbs.dll"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.gltf\ShellEx\{{e357fccd-a995-4576-b01f-234630154e96}"; ValueType: string; ValueData: "{{437a1563-8258-4e3c-80de-511965bd614c}"; Flags: uninsdeletekey

; Uzantı başına "Birlikte aç" kayıtları (make_meta.py üretir)
#include "extensions_registry.iss"

[Run]
; Windows, programın kendini sessizce varsayılan yapmasına izin vermez. Seçilen türler gamma'nın
; "Varsayılan uygulamalar" sayfasına yazılır; bu sayfadaki tek bir "Varsayılan olarak ayarla" düğmesi hepsini uygular.
Filename: "ms-settings:defaultapps?registeredAppUser=gamma"; Description: "{cm:RunDefaults}"; Flags: shellexec nowait postinstall skipifsilent; Check: AnyAssoc and not IsAdminInstallMode
Filename: "ms-settings:defaultapps?registeredAppMachine=gamma"; Description: "{cm:RunDefaults}"; Flags: shellexec nowait postinstall skipifsilent; Check: AnyAssoc and IsAdminInstallMode
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// ---------------------------------------------------------------- Gezgin'in kilitlediği küçük resim DLL'i
// GammaThumbs.dll Gezgin'in içinde çalışır (DisableProcessIsolation), bu yüzden üstüne yazılamaz ve silinemez.
// Ama Windows kullanımdaki bir dosyanın ADININ değiştirilmesine izin verir: eskisini "GammaThumbs.dll.N.old"
// yapıp yenisini yazıyoruz. Gezgin eskisini bellekte kullanmaya devam eder; yeniden başlayınca yenisini yükler.
// Eski kopyalar bir sonraki kurulumda / kaldırmada (artık kilitli değilse) silinir.
procedure DeleteOldThumbDlls;
var
  FR: TFindRec;
  Dir: String;
begin
  Dir := ExpandConstant('{app}\');
  if FindFirst(Dir + 'GammaThumbs.dll.*.old', FR) then
  try
    repeat
      DeleteFile(Dir + FR.Name);   // hâlâ kilitliyse sessizce kalır
    until not FindNext(FR);
  finally
    FindClose(FR);
  end;
end;

procedure MoveAsideThumbDll;
var
  Src, Dst: String;
  i: Integer;
begin
  Src := ExpandConstant('{app}\GammaThumbs.dll');
  DeleteOldThumbDlls;
  if FileExists(Src) and not DeleteFile(Src) then
  begin
    i := 1;
    repeat
      Dst := Src + '.' + IntToStr(i) + '.old';
      i := i + 1;
    until not FileExists(Dst);
    if not RenameFile(Src, Dst) then
      Log('GammaThumbs.dll kenara alınamadı: ' + Src);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    MoveAsideThumbDll;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    DeleteOldThumbDlls;
end;

// ---------------------------------------------------------------- Dosya türleri sayfası
// Gruplar (Video / Müzik / Görsel / 3D) ve altında tek tek uzantılar; hepsi tikli gelir.
// Güncelleme kurulumunda önceki seçim hatırlanır (yalnızca kaldırılan tikler saklanır,
// böylece sonraki sürümlerde eklenen yeni türler tikli gelir).
var
  AssocPage: TWizardPage;
  AssocList: TNewCheckListBox;
  AssocExts: TStringList;   // AssocList ile aynı sırada; grup satırları için ''

#include "extensions_code.iss"

function AssocSel(Ext: String): Boolean;
var
  i: Integer;
begin
  Result := False;
  if AssocList = nil then Exit;
  i := AssocExts.IndexOf(Ext);
  if i >= 0 then Result := AssocList.Checked[i];
end;

function AnyAssoc: Boolean;
var
  i: Integer;
begin
  Result := False;
  if AssocList = nil then Exit;
  for i := 0 to AssocExts.Count - 1 do
    if (AssocExts[i] <> '') and AssocList.Checked[i] then
    begin
      Result := True;
      Exit;
    end;
end;

procedure SetAllAssoc(V: Boolean);
var
  i: Integer;
begin
  for i := 0 to AssocList.Items.Count - 1 do
    AssocList.Checked[i] := V;
end;

procedure AssocAllClick(Sender: TObject);
begin
  SetAllAssoc(True);
end;

procedure AssocNoneClick(Sender: TObject);
begin
  SetAllAssoc(False);
end;

procedure InitializeWizard;
var
  Off: String;
  i: Integer;
  BAll, BNone: TNewButton;
begin
  AssocExts := TStringList.Create;
  AssocPage := CreateCustomPage(wpSelectDir, CustomMessage('AssocTitle'), CustomMessage('AssocDesc'));

  BAll := TNewButton.Create(AssocPage);
  BAll.Parent := AssocPage.Surface;
  BAll.Caption := CustomMessage('AssocAll');
  BAll.Width := ScaleX(120);
  BAll.Height := ScaleY(23);
  BAll.Left := 0;
  BAll.Top := AssocPage.SurfaceHeight - BAll.Height;
  BAll.OnClick := @AssocAllClick;

  BNone := TNewButton.Create(AssocPage);
  BNone.Parent := AssocPage.Surface;
  BNone.Caption := CustomMessage('AssocNone');
  BNone.Width := ScaleX(120);
  BNone.Height := ScaleY(23);
  BNone.Left := BAll.Left + BAll.Width + ScaleX(8);
  BNone.Top := BAll.Top;
  BNone.OnClick := @AssocNoneClick;

  AssocList := TNewCheckListBox.Create(AssocPage);
  AssocList.Parent := AssocPage.Surface;
  AssocList.Left := 0;
  AssocList.Top := 0;
  AssocList.Width := AssocPage.SurfaceWidth;
  AssocList.Height := BAll.Top - ScaleY(8);
  AddAssocItems(AssocList, AssocExts);

  Off := ',' + GetPreviousData('AssocOff', '') + ',';
  if Off <> ',,' then
    for i := 0 to AssocExts.Count - 1 do
      if (AssocExts[i] <> '') and (Pos(',' + AssocExts[i] + ',', Off) > 0) then
        AssocList.Checked[i] := False;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
var
  i: Integer;
  Off: String;
begin
  Off := '';
  for i := 0 to AssocExts.Count - 1 do
    if (AssocExts[i] <> '') and not AssocList.Checked[i] then
    begin
      if Off <> '' then Off := Off + ',';
      Off := Off + AssocExts[i];
    end;
  SetPreviousData(PreviousDataKey, 'AssocOff', Off);
end;
