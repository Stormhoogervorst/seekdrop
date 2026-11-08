; Inno Setup script. CI passes /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{AFE9CD32-27AE-44FE-8A3C-548DA2EC0AF1}
AppName=SeekDrop
AppVersion={#AppVersion}
AppPublisher=SeekDrop
DefaultDirName={autopf}\SeekDrop
DefaultGroupName=SeekDrop
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SeekDrop-{#AppVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\SeekDrop.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start SeekDrop when I log in"; Flags: unchecked

[Files]
Source: "..\dist\SeekDrop\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\SeekDrop"; Filename: "{app}\SeekDrop.exe"
Name: "{autodesktop}\SeekDrop"; Filename: "{app}\SeekDrop.exe"; Tasks: desktopicon
Name: "{userstartup}\SeekDrop"; Filename: "{app}\SeekDrop.exe"; Tasks: startup

[Run]
Filename: "{app}\SeekDrop.exe"; Description: "Open SeekDrop"; Flags: nowait postinstall skipifsilent
