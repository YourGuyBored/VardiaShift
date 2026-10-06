; Shiftora Windows installer (Inno Setup 6).
;
; Built by the release workflow after PyInstaller finishes:
;   iscc installer/windows/Shiftora.iss
;
; Override the version from the command line / CI:
;   iscc /DAppVersion=1.2.3 installer/windows/Shiftora.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{4F7C85F0-F360-4CC0-B2AB-8C58085718B8}}
AppName=Shiftora
AppVersion={#AppVersion}
AppPublisher=Shiftora Contributors
DefaultDirName={autopf}\Shiftora
DefaultGroupName=Shiftora
OutputDir=..\..\dist
OutputBaseFilename=Shiftora-Setup-Windows-x64
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=Shiftora
UninstallDisplayIcon={app}\Shiftora.exe

[Files]
Source: "..\..\dist\Shiftora\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\Shiftora"; Filename: "{app}\Shiftora.exe"
Name: "{autodesktop}\Shiftora"; Filename: "{app}\Shiftora.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\Shiftora.exe"; Description: "Launch Shiftora"; Flags: nowait postinstall skipifsilent
