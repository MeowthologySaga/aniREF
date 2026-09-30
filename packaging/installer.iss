; Inno Setup 6.3+ script for the aniREF per-user installer.
;
; Built by packaging\build.ps1, which passes the version and paths:
;   ISCC.exe /DAppVersion=0.1.0 /DAppVersionNumeric=0.1.0.0 /DAppSource=...\dist\aniREF ^
;            /DOutDir=...\dist /DOutName=aniREF-0.1.0-setup packaging\installer.iss
;
; No administrator rights: everything goes into the user's own folders, so an
; animator can install it on a locked-down studio PC. Nothing is written outside
; the install folder except the Start menu shortcut, the optional desktop icon
; and the .aniref file association under HKCU.

#define AppName "aniREF"
#define AppPublisher "aniREF"
#define ExeName "aniREF.exe"

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppVersionNumeric
  #define AppVersionNumeric "0.0.0.0"
#endif
#ifndef AppSource
  #define AppSource "..\dist\aniREF"
#endif
#ifndef OutDir
  #define OutDir "..\dist"
#endif
#ifndef OutName
  #define OutName "aniREF-" + AppVersion + "-setup"
#endif

[Setup]
; Never change AppId: it is how Windows and future installers recognise this app.
AppId={{8F0B2E1C-3A54-4C1E-9A77-1F6C5E4D2B90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersionNumeric}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; Per-user install: {autopf} becomes {localappdata}\Programs, no UAC prompt.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename={#OutName}
SetupIconFile=aniref.ico
UninstallDisplayIcon={app}\{#ExeName}
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Tells Windows to refresh the shell after .aniref is registered (and unregistered).
ChangesAssociations=yes
; Upgrades: ask the Restart Manager to close a running aniREF instead of failing on locked DLLs.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
; GPL-3.0 (the bundled FFmpeg contains x264/x265). build.ps1 defines WithLicense
; once a LICENSE file exists at the repo root and the build copied it in.
#ifdef WithLicense
LicenseFile={#AppSource}\LICENSE.txt
#endif

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
en.AssociateFiles=Open .aniref project files with aniREF
en.ProjectFileType=aniREF project
ko.AssociateFiles=.aniref 프로젝트 파일을 aniREF로 열기
ko.ProjectFileType=aniREF 프로젝트

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "{cm:AssociateFiles}"

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Registry]
; HKA with PrivilegesRequired=lowest is HKCU, so this needs no admin and only
; affects the person who installed it.
Root: HKA; Subkey: "Software\Classes\.aniref"; ValueType: string; ValueName: ""; ValueData: "aniREF.Project"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.aniref\OpenWithProgids"; ValueType: string; ValueName: "aniREF.Project"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\aniREF.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectFileType}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\aniREF.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#ExeName},0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\aniREF.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#ExeName}"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\{#ExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
