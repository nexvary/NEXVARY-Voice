#define MyAppName "NEXVARY Voice Studio"
#define MyAppVersion "0.4.1"
#define MyAppPublisher "NEXVARY"
#define MyAppExeName "NEXVARY-Voice.exe"
[Setup]
AppId={{3E673D7C-2B04-4DB0-91F8-59E893A94919}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\NEXVARY Voice
DefaultGroupName=NEXVARY Voice
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\..\dist\installers
OutputBaseFilename=NEXVARY-Voice-Setup-v{#MyAppVersion}
SetupIconFile=..\..\build\assets\nexvary-voice.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
CloseApplications=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
[Files]
Source: "..\..\dist\NEXVARY-Voice\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\NEXVARY Voice"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\NEXVARY Voice"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Start NEXVARY Voice"; Flags: nowait postinstall skipifsilent
