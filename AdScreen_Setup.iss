; ============================================================
;  AdScreen Converter — Inno Setup Script
;  Produces a single-file Windows installer .exe
; ============================================================

[Setup]
AppName=AdScreen Converter
AppVersion=1.0.0
AppPublisher=Primedia
AppPublisherURL=https://www.primediamalls.co.za
DefaultDirName={autopf}\AdScreen Converter
DefaultGroupName=AdScreen Converter
OutputDir=dist
OutputBaseFilename=AdScreen_Converter_Windows_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AdScreen Converter.exe
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\AdScreen Converter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AdScreen Converter";    Filename: "{app}\AdScreen Converter.exe"
Name: "{group}\Uninstall AdScreen";    Filename: "{uninstallexe}"
Name: "{commondesktop}\AdScreen Converter"; Filename: "{app}\AdScreen Converter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AdScreen Converter.exe"; Description: "Launch AdScreen Converter"; Flags: nowait postinstall skipifsilent
