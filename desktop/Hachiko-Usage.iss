; Inno Setup script for the Hachiko-Usage desktop pet.
; One-press install: every pre-install wizard page is disabled, so launching
; the setup immediately installs to %localappdata% and offers to let him out.
#define AppName "Hachiko-Usage"
#define AppVersion "1.1.0"
#define AppExe "Hachiko-Usage.exe"

[Setup]
AppId={{4E7A1C09-52D8-4F36-A1B9-8D0C6F23E571}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=hoya
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=Hachiko-Usage-Setup
SetupIconFile=hojek.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\Hachiko-Usage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Let {#AppName} out now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/im {#AppExe} /f"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillHachikoUsage"
