#define MyAppName "Spotify Alarm"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Vasilis"
#define MyAppExeName "SpotifyAlarm.exe"
#define MyIcon "icon.ico"

[Setup]
AppId={{3B3A9C9E-1A6E-4D3F-AB3B-AB5A2C1C1D9B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={pf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=SpotifyAlarmSetup
OutputDir=output
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest              ; per-user install is fine
SetupIconFile={#MyIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start {#MyAppName} when I sign in"; GroupDescription: "Autostart:"; Flags: checkedonce

[Registry]
; Autostart if user checked the task
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  CredPage: TWizardPage;
  EdClientID, EdClientSecret, EdDefaultURI: TEdit;

function IsBlank(s: string): boolean;
begin
  Result := Trim(s) = '';
end;

procedure InitializeWizard;
var
  LabelCID, LabelCS, LabelURI: TLabel;
begin
  CredPage := CreateCustomPage(wpSelectTasks, 'Spotify API Credentials',
    'Enter your Spotify app credentials and the default playlist/album/track URI.');

  LabelCID := TLabel.Create(WizardForm);
  LabelCID.Parent := CredPage.Surface;
  LabelCID.Caption := 'Client ID:';
  LabelCID.Left := ScaleX(0);
  LabelCID.Top := ScaleY(8);

  EdClientID := TEdit.Create(WizardForm);
  EdClientID.Parent := CredPage.Surface;
  EdClientID.Left := ScaleX(0);
  EdClientID.Top := ScaleY(24);
  EdClientID.Width := ScaleX(420);

  LabelCS := TLabel.Create(WizardForm);
  LabelCS.Parent := CredPage.Surface;
  LabelCS.Caption := 'Client Secret:';
  LabelCS.Left := ScaleX(0);
  LabelCS.Top := ScaleY(64);

  EdClientSecret := TEdit.Create(WizardForm);
  EdClientSecret.Parent := CredPage.Surface;
  EdClientSecret.Left := ScaleX(0);
  EdClientSecret.Top := ScaleY(80);
  EdClientSecret.Width := ScaleX(420);
  EdClientSecret.PasswordChar := '*';

  LabelURI := TLabel.Create(WizardForm);
  LabelURI.Parent := CredPage.Surface;
  LabelURI.Caption := 'Default Spotify URI (optional):';
  LabelURI.Left := ScaleX(0);
  LabelURI.Top := ScaleY(120);

  EdDefaultURI := TEdit.Create(WizardForm);
  EdDefaultURI.Parent := CredPage.Surface;
  EdDefaultURI.Left := ScaleX(0);
  EdDefaultURI.Top := ScaleY(136);
  EdDefaultURI.Width := ScaleX(420);
  EdDefaultURI.Text := 'spotify:playlist:3QHGPR9pobkC6PfBcQt2pr';  // your example
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = CredPage.ID) then
  begin
    if IsBlank(EdClientID.Text) then
    begin
      MsgBox('Client ID is required.', mbError, MB_OK);
      Result := False; Exit;
    end;
    if IsBlank(EdClientSecret.Text) then
    begin
      MsgBox('Client Secret is required.', mbError, MB_OK);
      Result := False; Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir, ConfigPath, Json: string;
begin
  if CurStep = ssInstall then
  begin
    { Write %APPDATA%\SpotifyAlarm\config.json }
    ConfigDir := ExpandConstant('{userappdata}\SpotifyAlarm');
    ConfigPath := ConfigDir + '\config.json';
    if not DirExists(ConfigDir) then
      ForceDirectories(ConfigDir);

    Json :=
      '{' + #13#10 +
      '  "client_id": "' + StringChange(EdClientID.Text, '"', '\"') + '",' + #13#10 +
      '  "client_secret": "' + StringChange(EdClientSecret.Text, '"', '\"') + '",' + #13#10 +
      '  "default_uri": "' + StringChange(EdDefaultURI.Text, '"', '\"') + '"' + #13#10 +
      '}';

    SaveStringToFile(ConfigPath, Json, False);
  end;
end;
