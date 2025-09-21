; =========================================================
; Spotify Alarm – Windows installer with credentials prompt
; =========================================================

#define MyAppName "Spotify Alarm"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Vasilis"
#define MyAppExeName "SpotifyAlarm.exe"
#define MyIcon "icon.ico"   ; optional: remove if you don't have an icon

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
PrivilegesRequired=lowest
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
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  CredPage: TWizardPage;
  EdClientID, EdClientSecret, EdDefaultURI: TEdit;
  Instructions: TNewMemo;

function IsBlank(s: string): Boolean;
begin
  Result := Trim(s) = '';
end;

procedure InitializeWizard;
var
  LabelCID, LabelCS, LabelURI: TLabel;
begin
  CredPage := CreateCustomPage(
    wpSelectTasks,
    'Spotify API Credentials',
    'Provide your Spotify app credentials and optional default playlist URI.'
  );

  { --- Instructions box --------------------------------------------------- }
  Instructions := TNewMemo.Create(WizardForm);
  Instructions.Parent := CredPage.Surface;
  Instructions.Left := ScaleX(0);
  Instructions.Top := ScaleY(0);
  Instructions.Width := ScaleX(420);
  Instructions.Height := ScaleY(120);
  Instructions.ReadOnly := True;
  Instructions.ScrollBars := ssVertical;
  Instructions.WordWrap := True;
  Instructions.Lines.Text :=
    'You need a Spotify Developer app to get a Client ID and Client Secret:' + #13#10#13#10 +
    '1. Go to https://developer.spotify.com/dashboard and log in with your Spotify account.' + #13#10 +
    '2. Click **Create App**.' + #13#10 +
    '3. Give it a name (e.g. Spotify Alarm) and description.' + #13#10 +
    '4. In "Redirect URIs" add this exactly: http://127.0.0.1:8080/callback' + #13#10 +
    '5. Save and then click **Settings** to reveal your **Client ID** and **Client Secret**.' + #13#10 +
    '6. Copy those values into the fields below.' + #13#10 +
    'The Default Spotify URI is optional (e.g. spotify:playlist:37i9dQZF1DXcBWIGoYBM5M).';

  { --- Client ID field ---------------------------------------------------- }
  LabelCID := TLabel.Create(WizardForm);
  LabelCID.Parent := CredPage.Surface;
  LabelCID.Caption := 'Client ID:';
  LabelCID.Top := Instructions.Top + Instructions.Height + ScaleY(8);

  EdClientID := TEdit.Create(WizardForm);
  EdClientID.Parent := CredPage.Surface;
  EdClientID.Top := LabelCID.Top + ScaleY(16);
  EdClientID.Width := ScaleX(420);

  { --- Client Secret field ------------------------------------------------ }
  LabelCS := TLabel.Create(WizardForm);
  LabelCS.Parent := CredPage.Surface;
  LabelCS.Caption := 'Client Secret:';
  LabelCS.Top := EdClientID.Top + ScaleY(36);

  EdClientSecret := TEdit.Create(WizardForm);
  EdClientSecret.Parent := CredPage.Surface;
  EdClientSecret.Top := LabelCS.Top + ScaleY(16);
  EdClientSecret.Width := ScaleX(420);
  EdClientSecret.PasswordChar := '*';

  { --- Default URI field (optional) --------------------------------------- }
  LabelURI := TLabel.Create(WizardForm);
  LabelURI.Parent := CredPage.Surface;
  LabelURI.Caption := 'Default Spotify URI (optional):';
  LabelURI.Top := EdClientSecret.Top + ScaleY(36);

  EdDefaultURI := TEdit.Create(WizardForm);
  EdDefaultURI.Parent := CredPage.Surface;
  EdDefaultURI.Top := LabelURI.Top + ScaleY(16);
  EdDefaultURI.Width := ScaleX(420);
  EdDefaultURI.Text := '';
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
