; ОхранаТруда Про — Inno Setup-скрипт установщика.
; Компиляция: ISCC installer\suot_neo.iss  (Inno Setup 6+)
; Перед компиляцией: python scripts\build_exe.py

#define AppName "ОхранаТруда Про"
#define AppVersion "2.2.1"
#define AppExe "SUOT_Neo.exe"

[Setup]
AppId={{7E1B6C2A-52F4-4A57-9D8E-2F3C4A5B6C7D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher="ОхранаТруда Про"
DefaultDirName={userpf}\SUOT_Neo
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
DisableDirPage=no

[Files]
Source: "..\dist\SUOT_Neo\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\backups"
