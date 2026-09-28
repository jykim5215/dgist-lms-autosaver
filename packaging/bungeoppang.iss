; 붕어빵 - DGIST LMS AutoSaver
; Inno Setup 설치 스크립트
;
; 이 설치 프로그램이 해결하는 것:
;  - zip 배포 시 모든 파일에 붙던 MOTW(차단 표시) → 설치된 파일에는 붙지 않음
;  - WebView2 런타임 미설치 환경 → 부트스트래퍼 자동 실행
;  - .NET Framework 4.7.2 미만 → 설치 전에 명확한 안내로 중단

#define AppName "붕어빵"
; 버전은 build_installer.ps1 이 VERSION 파일에서 읽어 /DAppVersion 으로 넘긴다
#ifndef AppVersion
  #define AppVersion "1.11.0"
#endif
#define AppPublisher "jykim5215"
#define AppURL "https://github.com/jykim5215/dgist-lms-autosaver"
#define AppExe "붕어빵.exe"

[Setup]
AppId={{8F3A6C21-4D9B-4E77-9C1A-5B2E7F0A9D64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} - DGIST LMS AutoSaver

; 관리자 권한 없이 사용자 폴더에 설치 → 공용/제한 PC에서도 UAC 없이 설치됨
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

; x64 전용 빌드 (arm64에서는 에뮬레이션으로 동작)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=out
OutputBaseFilename=bungeoppang-{#AppVersion}-win-x64-setup
SetupIconFile=payload\_internal\web\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 실행 중이면 닫도록 유도 (재부팅 요구 없이)
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Windows 시작 시 자동 실행"; GroupDescription: "추가 옵션:"; Flags: unchecked

[Files]
Source: "payload\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "payload\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; WebView2 런타임이 없는 PC에서만 실행됨
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\web\app.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\web\app.ico"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: startupicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "WebView2 런타임을 설치하는 중입니다..."; Check: NeedsWebView2; Flags: waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
; 앱 안 '지금 업데이트' 는 /SILENT /RELAUNCH=1 로 부른다. 조용히 설치한 뒤 앱을 다시 켠다 (updater.py)
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Flags: nowait runasoriginaluser; Check: ShouldRelaunch

[UninstallRun]
; 삭제할 때는 설치와 달리 켜져 있는 앱을 닫아 주지 않는다. 창을 닫아도 알림 영역에서 돌고 있으면
; 쓰이는 파일 48개를 못 지우고 '삭제 완료' 라고 끝나 반쯤 남은 폴더가 된다(2026-09-28 재현).
; 앱과 뒤에서 도는 작업(같은 이름의 exe)을 먼저 닫는다.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ""{#AppExe}"""; Flags: runhidden waituntilterminated; RunOnceId: "CloseBungeoppang"

[UninstallDelete]
; 앱이 설치 폴더 안에 만든 런타임 파일 정리 (사용자 문서는 건드리지 않음)
Type: filesandordirs; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}"

[Code]
const
  WV2_HKLM = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WV2_HKCU = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  NET472_RELEASE = 461808;

function WebView2Installed: Boolean;
var
  V: String;
begin
  Result := False;
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, WV2_HKLM, 'pv', V) then
    if (V <> '') and (V <> '0.0.0.0') then Result := True;
  if not Result then
    if RegQueryStringValue(HKEY_CURRENT_USER, WV2_HKCU, 'pv', V) then
      if (V <> '') and (V <> '0.0.0.0') then Result := True;
end;

function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:relaunch|0}') = '1');
end;

function NeedsWebView2: Boolean;
begin
  Result := not WebView2Installed;
end;

function DotNetOK: Boolean;
var
  Rel: Cardinal;
begin
  Result := False;
  if RegQueryDWordValue(HKEY_LOCAL_MACHINE,
       'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full', 'Release', Rel) then
    Result := Rel >= NET472_RELEASE;
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not DotNetOK then
  begin
    MsgBox('붕어빵을 실행하려면 .NET Framework 4.7.2 이상이 필요합니다.' + #13#10#13#10 +
           'Windows Update를 먼저 실행하거나 아래 주소에서 설치한 뒤 다시 시도해 주세요.' + #13#10 +
           'https://dotnet.microsoft.com/download/dotnet-framework',
           mbCriticalError, MB_OK);
    Result := False;
  end;
end;
