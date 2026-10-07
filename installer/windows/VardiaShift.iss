; VardiaShift Windows installer (Inno Setup 6).
;
; Built by the release workflow after PyInstaller finishes:
;   iscc installer/windows/VardiaShift.iss
;
; Override the version from the command line / CI:
;   iscc /DAppVersion=1.2.3 installer/windows/VardiaShift.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{4F7C85F0-F360-4CC0-B2AB-8C58085718B8}}
AppName=VardiaShift
AppVersion={#AppVersion}
AppPublisher=VardiaShift Contributors
DefaultDirName={autopf}\VardiaShift
DefaultGroupName=VardiaShift
OutputDir=..\..\dist
OutputBaseFilename=VardiaShift-Setup-Windows-x64
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=VardiaShift
UninstallDisplayIcon={app}\VardiaShift.exe

[Files]
Source: "..\..\dist\VardiaShift\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\VardiaShift"; Filename: "{app}\VardiaShift.exe"
Name: "{autodesktop}\VardiaShift"; Filename: "{app}\VardiaShift.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\VardiaShift.exe"; Description: "Launch VardiaShift"; Flags: nowait postinstall skipifsilent
