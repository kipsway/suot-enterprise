; ОхранаТруда Про — Inno Setup-скрипт установщика.
; Компиляция: ISCC installer\suot_neo.iss  (Inno Setup 6+)
; Перед компиляцией: python scripts\build_exe.py

#define AppName "ОхранаТруда Про"
#define AppVersion "2.2.2"
#define AppExe "SUOT_Neo.exe"
#define InstallerGuid "{7E1B6C2A-52F4-4A57-9D8E-2F3C4A5B6C7D}"

[Setup]
AppId={{#InstallerGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher="ОхранаТруда Про"
DefaultDirName={code:GetDefaultDir}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=SUOT_Neo_setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=yes
AppMutex=SUOT_Neo_SingleInstance_v1
UsePreviousAppDir=yes
DisableDirPage=no

[Files]
Source: "..\dist\SUOT_Neo\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Code]
const
  UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';

{ Находит каталог ранее установленной версии (тот же каталог SUOT_Neo) в }
{ любой ветке реестра — HKLM/HKCU, чтобы не ставить «вторую версию». }
function FindInRoot(Root: Integer): string;
var
  Names: TArrayOfString;
  i: Integer;
  sub, loc: string;
begin
  Result := '';
  if not RegGetSubkeyNames(Root, UninstKey, Names) then
    Exit;
  for i := 0 to GetArrayLength(Names) - 1 do
  begin
    sub := UninstKey + '\' + Names[i];
    loc := '';
    if RegQueryStringValue(Root, sub, 'InstallLocation', loc) and (loc <> '') then
    begin
      loc := RemoveQuotes(loc);
      if DirExists(loc) and (Uppercase(ExtractFileName(loc)) = 'SUOT_NEO') then
      begin
        Result := loc;
        Exit;
      end;
    end;
  end;
end;

function UnderSystemDir(s: string): Boolean;
var
  pf: string;
begin
  Result := False;
  pf := Lowercase(ExpandConstant('{autopf}'));
  if (pf <> '') and (Pos(pf, Lowercase(s)) = 1) then
    Result := True;
end;

{ Каталог установки: переиспользуем прошлый (переустановка = обновление). }
function GetDefaultDir(Param: string): string;
var
  d: string;
begin
  Result := ExpandConstant('{userpf}\SUOT_Neo');
  d := FindInRoot(HKCU);
  if d = '' then
    d := FindInRoot(HKLM);
  if d = '' then
    d := FindInRoot(HKLM32);
  if (d <> '') and DirExists(d) then
  begin
    { Системную папку (Program Files) переиспользуем только с правами администратора. }
    if IsAdminInstallMode or not UnderSystemDir(d) then
      Result := d;
  end;
end;

{ Убираем «дублирующую» запись в «Установка и удаление программ», если }
{ прошлая установка жила в том же каталоге, но под другим AppId. }
procedure CleanupStaleEntries(Root: Integer);
var
  Names: TArrayOfString;
  i: Integer;
  sub, loc: string;
begin
  if not RegGetSubkeyNames(Root, UninstKey, Names) then
    Exit;
  for i := 0 to GetArrayLength(Names) - 1 do
  begin
    if Names[i] = '{#InstallerGuid}_is1' then
      Continue;
    sub := UninstKey + '\' + Names[i];
    loc := '';
    if RegQueryStringValue(Root, sub, 'InstallLocation', loc) and (loc <> '') then
    begin
      loc := RemoveQuotes(loc);
      if (loc <> '') and DirExists(loc) and
         (Uppercase(ExtractFileName(loc)) = 'SUOT_NEO') and
         (CompareText(loc, ExpandConstant('{app}')) = 0) then
        RegDeleteKeyIncludingSubkeys(Root, sub);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CleanupStaleEntries(HKCU);
    CleanupStaleEntries(HKLM);
    CleanupStaleEntries(HKLM32);
  end;
end;