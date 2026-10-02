# 붕어빵 설치 파일 만들기 (+ 선택: 이 PC에 바로 설치)
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 -Install
#
# 순서: PyInstaller(onedir) → 불필요한 파일 정리 → payload 복사 → Inno Setup → (설치·실행)
# 준비물: 프로젝트 .venv (Python 3.14), Inno Setup 6, packaging\MicrosoftEdgeWebview2Setup.exe
# 주의: 이 파일은 UTF-8 BOM 으로 저장해야 한다. BOM 이 없으면 Windows PowerShell 5.1 이
#       한글을 깨뜨려 구문 오류가 난다.
#
# GitHub Actions(.github/workflows/release.yml)는 SignPath 서명을 사이에 끼우려고 두 번에 나눠 부른다:
#   -Stage exe        → [1/5]~[2/5] 만 (dist\붕어빵 을 만든다. 여기서 EXE 를 서명)
#   -Stage installer  → [3/5]~[4/5] 만 (서명된 dist\붕어빵 으로 설치 파일을 만든다)
param([switch]$Install, [ValidateSet("all", "exe", "installer")][string]$Stage = "all")

$ErrorActionPreference = "Stop"
$packaging = $PSScriptRoot
$proj = Split-Path $packaging -Parent
$payload = Join-Path $packaging "payload"
# 이 PC 는 저장소 .venv, CI 는 setup-python 이 깐 python
$py = if (Test-Path (Join-Path $proj ".venv\Scripts\python.exe")) { Join-Path $proj ".venv\Scripts\python.exe" } else { "python" }
$signTool = Join-Path $packaging "sign_tools.ps1"
$canSign = [bool](Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq "CN=붕어빵 (jykim5215), O=jykim5215" -and $_.NotAfter -gt (Get-Date) -and $_.HasPrivateKey })

Set-Location $proj
if ($Stage -ne "installer") {
"[1/5] PyInstaller"
& $py -m PyInstaller bungeoppang.spec --noconfirm | Select-Object -Last 3
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

# 사설 코드 서명 (이 PC 에 인증서가 있을 때만. 만들기: sign_tools.ps1 -New).
# CI 에는 인증서가 없으므로 건너뛰고, 대신 SignPath 가 공인 인증서로 서명한다.
if ($canSign) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $signTool -Sign (Join-Path $proj "dist\붕어빵\붕어빵.exe")
  if ($LASTEXITCODE -ne 0) { throw "EXE 서명 실패" }
} else { "사설 서명 인증서 없음 — 서명 없이 만듭니다" }
}
if ($Stage -eq "exe") { "완료 (dist\붕어빵)"; return }

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
if ($canSign) {
  # Inno 가 $f 를 서명할 파일 경로(따옴표 포함)로, $q 를 따옴표로 바꿔 부른다
  & $iscc "/DAppVersion=$version" "/DSign" "/Sbpsign=powershell.exe -NoProfile -ExecutionPolicy Bypass -File `$q$signTool`$q -Sign `$f" "bungeoppang.iss" /Q
} else {
  & $iscc "/DAppVersion=$version" "bungeoppang.iss" /Q
}
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
