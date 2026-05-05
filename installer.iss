; installer.iss — Inno Setup script for Sentinel
; =============================================================================
; Build with:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; Output:      installer_output\SentinelInstaller_v1.0.0.exe

#define AppName        "Sentinel"
#define AppVersion     "1.0.0"
#define AppPublisher   "its-me-prabin"
#define AppURL         "https://prabinsaru.com.np"
#define AppSupportURL  "https://prabinsaru.com.np/contact"
#define AppExeName     "Sentinel.exe"

[Setup]
; Unique application ID (generated GUID — never reuse across different apps)
AppId={{137FF0DF-FC02-4259-9B30-307520BC052C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppSupportURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Output installer file
OutputDir=installer_output
OutputBaseFilename=SentinelInstaller_v{#AppVersion}
; Icon shown in Add/Remove Programs
SetupIconFile=assets\sentinel_icon.ico
; Compress the installer (LZMA gives best compression)
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Require Windows 10 or later
MinVersion=10.0
; Show license page
LicenseFile=LICENSE.txt
; Request admin privileges for install to Program Files
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Optional Desktop shortcut checkbox shown during install
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The main executable — built by PyInstaller
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Bundle the default config.yaml (copied to AppData on first run by the app)
Source: "config.yaml"; DestDir: "{app}"; Flags: ignoreversion

; App icon (needed for shortcuts)
Source: "assets\sentinel_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
  IconFilename: "{app}\sentinel_icon.ico"
; Start Menu uninstall shortcut
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
; Optional Desktop shortcut (only if user checked the box)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
  IconFilename: "{app}\sentinel_icon.ico"; Tasks: desktopicon

[Run]
; Offer to launch Sentinel immediately after install finishes
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up AppData folder on uninstall (optional — remove these lines
; if you want to preserve the user's config and logs across reinstalls)
; Type: filesandordirs; Name: "{userappdata}\Sentinel"
