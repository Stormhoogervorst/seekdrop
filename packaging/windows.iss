; Inno Setup script. CI passes /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{AFE9CD32-27AE-44FE-8A3C-548DA2EC0AF1}
AppName=SeekSync
AppVersion={#AppVersion}
AppPublisher=SeekSync
DefaultDirName={autopf}\SeekSync
DefaultGroupName=SeekSync
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SeekSync-{#AppVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\SeekSync.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start SeekSync when I log in"; Flags: unchecked

[InstallDelete]
; the app was called SeekDrop before: remove its program file and shortcuts when updating over it
Type: files; Name: "{app}\SeekDrop.exe"
Type: files; Name: "{group}\SeekDrop.lnk"
Type: files; Name: "{autodesktop}\SeekDrop.lnk"
Type: files; Name: "{userstartup}\SeekDrop.lnk"

[Files]
Source: "..\dist\SeekSync\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\SeekSync"; Filename: "{app}\SeekSync.exe"
Name: "{autodesktop}\SeekSync"; Filename: "{app}\SeekSync.exe"; Tasks: desktopicon
Name: "{userstartup}\SeekSync"; Filename: "{app}\SeekSync.exe"; Tasks: startup

[Run]
Filename: "{app}\SeekSync.exe"; Description: "Open SeekSync"; Flags: nowait postinstall skipifsilent
