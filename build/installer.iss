; Installateur Inno Setup pour WpImagerDownloader
; Compiler après PyInstaller :  iscc build\installer.iss
; Produit : build\Output\WpImagerDownloader-1.0.11-setup.exe

#define MonNom "WpImagerDownloader"
#define MonNomCourt "WpImagerDownloader"
#ifndef MaVersion
  #define MaVersion "1.0.11"
#endif
#define MonEditeur "Projet personnel"
#define MonExe "WpImagerDownloader.exe"

[Setup]
AppId={{8F3C1A42-6B2E-4D91-9C07-2E5A7D44B118}
AppName={#MonNom}
AppVersion={#MaVersion}
AppPublisher={#MonEditeur}
; Avec PrivilegesRequired=lowest, {autopf} résout vers {userpf} =
; %LOCALAPPDATA%\Programs\{#MonNomCourt} (install user-scope, pas d'UAC).
DefaultDirName={autopf}\{#MonNomCourt}
DefaultGroupName={#MonNom}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename={#MonNomCourt}-{#MaVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; installation par utilisateur : ni UAC ni droits administrateur requis
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MonExe}
SetupIconFile=WpImageDownloader.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; \
    GroupDescription: "Raccourcis :"
Name: "startup"; Description: "Lancer au démarrage de Windows (mise à jour en arrière-plan)"; \
    GroupDescription: "Démarrage :"; Flags: unchecked

[Files]
; le dossier produit par PyInstaller en mode COLLECT
Source: "..\dist\WpImagerDownloader\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MonNom}"; Filename: "{app}\{#MonExe}"
Name: "{group}\Désinstaller {#MonNom}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MonNom}"; Filename: "{app}\{#MonExe}"; Tasks: desktopicon
Name: "{userstartup}\{#MonNom}"; Filename: "{app}\{#MonExe}"; \
    Parameters: "--reduit"; Tasks: startup

[Run]
Filename: "{app}\{#MonExe}"; Description: "Lancer {#MonNom}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; l'entrée de démarrage éventuellement posée par l'application elle-même
Type: files; Name: "{userstartup}\{#MonNom}.lnk"

[Code]
// À la désinstallation, proposer de conserver photos et configuration.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Config: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Config := ExpandConstant('{userappdata}\WpImageDownloader');
    if DirExists(Config) then
    begin
      if MsgBox('Supprimer également vos préférences ?' + #13#10 +
                'Vos photos téléchargées ne seront pas touchées.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(Config, True, True, True);
    end;
  end;
end;
