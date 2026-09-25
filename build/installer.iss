; Installateur Inno Setup pour Glaneur
; Compiler après PyInstaller :  iscc build\installer.iss
; Produit : build\Output\Glaneur-1.1.0-setup.exe

#define MonNom "Glaneur"
#define MonNomCourt "Glaneur"
#ifndef MaVersion
  #define MaVersion "1.1.0"
#endif
#define MonEditeur "Projet personnel"
#define MonExe "Glaneur.exe"

[Setup]
; AppId propre à Glaneur — GUID différent de celui de l'ancien
; WpImagerDownloader (8F3C1A42-…) pour permettre les deux d'être
; installés côte à côte pendant la transition.
AppId={{D4C5047C-DE6D-43CE-96E0-EA544236FD7B}
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
SetupIconFile=Glaneur.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; \
    GroupDescription: "Raccourcis :"
Name: "startup"; Description: "Lancer au démarrage de Windows (mise à jour en arrière-plan)"; \
    GroupDescription: "Démarrage :"; Flags: unchecked

[Files]
; le dossier produit par PyInstaller en mode COLLECT
Source: "..\dist\Glaneur\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MonNom}"; Filename: "{app}\{#MonExe}"
Name: "{group}\Désinstaller {#MonNom}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MonNom}"; Filename: "{app}\{#MonExe}"; Tasks: desktopicon
Name: "{userstartup}\{#MonNom}"; Filename: "{app}\{#MonExe}"; \
    Parameters: "--reduit"; Tasks: startup

[Run]
; `nowait` seul : garantit que l'app est relancée en fin d'install même
; en mode /VERYSILENT (postinstall + skipifsilent étaient tous deux
; bloquants dans ce cas, ce qui empêchait l'auto-update de finaliser).
Filename: "{app}\{#MonExe}"; Parameters: "--reduit"; \
    Description: "Lancer {#MonNom}"; Flags: nowait

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
    Config := ExpandConstant('{userappdata}\Glaneur');
    if DirExists(Config) then
    begin
      if MsgBox('Supprimer également vos préférences ?' + #13#10 +
                'Vos photos téléchargées ne seront pas touchées.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(Config, True, True, True);
    end;
  end;
end;
