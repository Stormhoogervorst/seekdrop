; Inno Setup script. CI passes /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{1E7D6CF7-2399-422C-BAA0-73A5A475D319}
AppName=Cratewatch
AppVersion={#AppVersion}
AppPublisher=Cratewatch
DefaultDirName={autopf}\Cratewatch
DefaultGroupName=Cratewatch
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Cratewatch-{#AppVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Cratewatch.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Cratewatch when I log in"; Flags: unchecked

[Files]
Source: "..\dist\Cratewatch\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Cratewatch"; Filename: "{app}\Cratewatch.exe"
Name: "{autodesktop}\Cratewatch"; Filename: "{app}\Cratewatch.exe"; Tasks: desktopicon
Name: "{userstartup}\Cratewatch"; Filename: "{app}\Cratewatch.exe"; Tasks: startup

[Run]
Filename: "{app}\Cratewatch.exe"; Description: "Open Cratewatch"; Flags: nowait postinstall skipifsilent
