# 붕어빵 설치 파일 만들기 (+ 선택: 이 PC에 바로 설치)
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 -Install
#
# 순서: PyInstaller(onedir) → 불필요한 파일 정리 → payload 복사 → Inno Setup → (설치·실행)
# 준비물: 프로젝트 .venv (Python 3.14), Inno Setup 6, packaging\MicrosoftEdgeWebview2Setup.exe
# 주의: 이 파일은 UTF-8 BOM 으로 저장해야 한다. BOM 이 없으면 Windows PowerShell 5.1 이
#       한글을 깨뜨려 구문 오류가 난다.
param([switch]$Install)

$ErrorActionPreference = "Stop"
$packaging = $PSScriptRoot
$proj = Split-Path $packaging -Parent
$payload = Join-Path $packaging "payload"

Set-Location $proj
"[1/5] PyInstaller"
& ".\.venv\Scripts\python.exe" -m PyInstaller bungeoppang.spec --noconfirm | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 실패" }

"[2/5] 불필요한 파일 정리"
$internal = Join-Path $proj "dist\붕어빵\_internal"
# 구글 API 설명 파일은 수백 개인데 쓰는 것은 넷뿐이다
Get-ChildItem -Path $internal -Recurse -Directory -Filter "discovery_cache" -ErrorAction SilentlyContinue | ForEach-Object {
  $docs = Join-Path $_.FullName "documents"
  if (Test-Path $docs) {
    Get-ChildItem $docs -File | Where-Object { $_.Name -notmatch '^(calendar\.v3|drive\.v3|drive\.v2|oauth2\.v2)\.json$' } | Remove-Item -Force
  }
}
Get-ChildItem -Path $internal -Recurse -File -Filter "pywebview-android.jar" -ErrorAction SilentlyContinue | Remove-Item -Force
# Playwright 드라이버 중 앱이 안 쓰는 트레이스 뷰어·타입 선언 (~5MB)
foreach ($rel in @("playwright\driver\package\lib\vite", "playwright\driver\package\types")) {
  $p = Join-Path $internal $rel
  if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}
# 주의: pythonnet 의 runtimes\win-arm64 등은 지우면 안 된다 (pywebview 가 깨진다)

"[3/5] payload 복사"
robocopy (Join-Path $proj "dist\붕어빵") $payload /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy 실패 ($LASTEXITCODE)" }

"[4/5] Inno Setup"
$iscc = @(
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
  "C:\Program Files\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "ISCC.exe 를 찾지 못했습니다 (Inno Setup 6 설치 필요)" }
Set-Location $packaging
$version = (Get-Content (Join-Path $proj "VERSION") -Raw).Trim()
"버전: $version"
& $iscc "/DAppVersion=$version" "bungeoppang.iss" /Q
if ($LASTEXITCODE -ne 0) { throw "ISCC 실패" }
$setup = Get-ChildItem (Join-Path $packaging "out") -Filter "*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
"설치 파일: $($setup.FullName) ($([math]::Round($setup.Length / 1MB, 1)) MB)"

if (-not $Install) { "완료 (설치는 -Install 로)"; return }

"[5/5] 이 PC 에 설치"
Get-Process -Name "붕어빵" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$p = Start-Process -FilePath $setup.FullName -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /TASKS=desktopicon" -Wait -PassThru
"설치 종료코드: $($p.ExitCode)"
Start-Process -FilePath "$env:LOCALAPPDATA\Programs\붕어빵\붕어빵.exe"
"완료"
