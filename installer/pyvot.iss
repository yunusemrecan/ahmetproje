; Inno Setup betiği: Pyvot-Setup.exe üretir.
; Derleme: iscc /DAppVersion=0.1.0 installer\pyvot.iss
; Girdi: dist\Pyvot (PyInstaller çıktısı, içinde uv.exe ile)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8E4C2F57-3B1A-4C9E-9D2B-6A7F0E5B1C43}
AppName=Pyvot
AppVersion={#AppVersion}
AppVerName=Pyvot {#AppVersion}
AppPublisher=Pyvot
DefaultDirName={autopf}\Pyvot
DefaultGroupName=Pyvot
DisableProgramGroupPage=yes
; Yönetici izni gerekmez; kullanıcı isterse tüm kullanıcılar için kurabilir.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=Pyvot-Setup-{#AppVersion}
SetupIconFile=pyvot.ico
UninstallDisplayIcon={app}\Pyvot.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Pyvot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Pyvot"; Filename: "{app}\Pyvot.exe"
Name: "{autodesktop}\Pyvot"; Filename: "{app}\Pyvot.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Pyvot.exe"; Description: "{cm:LaunchProgram,Pyvot}"; Flags: nowait postinstall skipifsilent
