; Inno Setup script. CI passes /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{AFE9CD32-27AE-44FE-8A3C-548DA2EC0AF1}
AppName=Nicotine+ Sync
AppVersion={#AppVersion}
AppPublisher=Nicotine+ Sync
DefaultDirName={autopf}\NicotineSync
DefaultGroupName=Nicotine+ Sync
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NicotineSync-{#AppVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\NicotineSync.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Nicotine+ Sync when I log in"; Flags: unchecked

[Files]
Source: "..\dist\NicotineSync\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Nicotine+ Sync"; Filename: "{app}\NicotineSync.exe"
Name: "{autodesktop}\Nicotine+ Sync"; Filename: "{app}\NicotineSync.exe"; Tasks: desktopicon
Name: "{userstartup}\Nicotine+ Sync"; Filename: "{app}\NicotineSync.exe"; Tasks: startup

[Run]
Filename: "{app}\NicotineSync.exe"; Description: "Open Nicotine+ Sync"; Flags: nowait postinstall skipifsilent
