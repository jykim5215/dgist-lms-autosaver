# DGIST LMS AutoSaver 설치 + 바로가기 생성 (시작하기.bat이 호출)
$ErrorActionPreference = "Stop"
$proj = $PSScriptRoot

Write-Host ""
Write-Host "=== DGIST LMS AutoSaver 최초 설치 ===" -ForegroundColor Cyan
Write-Host ""

# 1. Python 확인
try {
    $pyVersion = python --version 2>&1
    Write-Host "[1/4] Python 확인: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "[필요] Python이 설치되어 있지 않습니다." -ForegroundColor Red
    Write-Host "  https://www.python.org/downloads/ 에서 Python 3.11 이상을 설치하세요."
    Write-Host "  설치 화면에서 'Add Python to PATH'를 꼭 체크한 뒤 다시 실행해 주세요."
    exit 1
}

# 2. 패키지 설치
Write-Host "[2/4] 필요한 패키지 설치 중... (1~2분)"
python -m pip install --quiet -r "$proj\requirements.txt"
if ($LASTEXITCODE -ne 0) { Write-Host "[오류] 패키지 설치 실패" -ForegroundColor Red; exit 1 }

# 3. Playwright 브라우저 (LMS 자동 로그인용)
Write-Host "[3/4] 브라우저 구성요소 설치 중... (1~2분)"
python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Write-Host "[오류] 브라우저 설치 실패" -ForegroundColor Red; exit 1 }

# 4. 바탕화면 바로가기 생성 (이 PC의 경로로)
Write-Host "[4/4] 바탕화면 바로가기 생성 중..."
$pythonDir = Split-Path (Get-Command python).Source
$pythonw = Join-Path $pythonDir "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = (Get-Command python).Source }  # pythonw 없으면 python 사용
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut((Join-Path $desktop "DGIST LMS AutoSaver.lnk"))
$sc.TargetPath = $pythonw
$sc.Arguments = '"' + (Join-Path $proj 'app.py') + '"'
$sc.WorkingDirectory = $proj
$sc.IconLocation = (Join-Path $proj 'web\app.ico') + ',0'
$sc.Description = 'DGIST LMS AutoSaver'
$sc.Save()

Write-Host ""
Write-Host "설치 완료! 앱을 실행합니다..." -ForegroundColor Green
exit 0
