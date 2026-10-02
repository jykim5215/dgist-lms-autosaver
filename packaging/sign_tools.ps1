# 붕어빵 코드 서명 도구 (사설 인증서)
#
#   # 1) 인증서 만들기 (한 번만. 개인 키는 이 PC 사용자 인증서 저장소에만, 내보낼 수 없게 만든다)
#   powershell -ExecutionPolicy Bypass -File packaging\sign_tools.ps1 -New
#   # 2) 이 PC 가 그 인증서를 믿게 하기 (사용자가 직접. Windows 확인 창이 뜬다)
#   powershell -ExecutionPolicy Bypass -File packaging\sign_tools.ps1 -Trust
#   # 3) 서명 (build_installer.ps1 이 알아서 부른다)
#   powershell -ExecutionPolicy Bypass -File packaging\sign_tools.ps1 -Sign <파일> [<파일> ...]
#
# 왜: 2026-10-02 Windows Defender 가 서명·버전 정보가 없는 붕어빵.exe 를 'Trojan:Win32/Bearfoos.A!ml'
#     (기계학습 추정 오탐)으로 지웠다. 사설 서명은 '누가 만든 파일이 바뀌지 않았다'를 이 PC 에 알려 줄 뿐이고,
#     다른 PC 의 SmartScreen·Defender 평판은 공인 인증서(Azure Trusted Signing 등)가 있어야 쌓인다.
# 주의: 이 파일은 UTF-8 BOM 으로 저장한다 (PowerShell 5.1 한글).
param(
  [switch]$New,
  [switch]$Trust,
  [switch]$Sign,
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$Files
)

$ErrorActionPreference = "Stop"
$Subject = "CN=붕어빵 (jykim5215), O=jykim5215"
$CerPath = Join-Path $PSScriptRoot "bungeoppang-codesign.cer"
$TimeStamp = "http://timestamp.digicert.com"

function Get-SigningCert {
  Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq $Subject -and $_.NotAfter -gt (Get-Date) -and $_.HasPrivateKey } |
    Sort-Object NotAfter -Descending | Select-Object -First 1
}

if ($New) {
  $cert = Get-SigningCert
  if ($cert) {
    "이미 있음: $($cert.Thumbprint) (만료 $($cert.NotAfter.ToString('yyyy-MM-dd')))"
  } else {
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
      -CertStoreLocation Cert:\CurrentUser\My -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 `
      -KeyExportPolicy NonExportable -NotAfter (Get-Date).AddYears(5)
    "만듦: $($cert.Thumbprint) (만료 $($cert.NotAfter.ToString('yyyy-MM-dd')))"
  }
  # 공개 부분(.cer)만 꺼내 둔다. 다른 PC 에서 믿게 하려면 이 파일을 쓴다. 개인 키는 들어 있지 않다.
  Export-Certificate -Cert $cert -FilePath $CerPath -Type CERT | Out-Null
  "공개 인증서: $CerPath"
}

if ($Trust) {
  if (-not (Test-Path $CerPath)) { throw "먼저 -New 로 인증서를 만드세요" }
  # 사설 인증서라 '신뢰할 수 있는 루트'(서명 체인) + '신뢰할 수 있는 게시자'(경고 없이 실행) 둘 다 필요하다.
  # CurrentUser 루트에 넣을 때 Windows 가 확인 창을 띄운다 — 지문을 확인하고 '예'.
  Import-Certificate -FilePath $CerPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
  Import-Certificate -FilePath $CerPath -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
  "이 PC(현재 사용자)가 붕어빵 서명을 믿습니다"
}

if ($Sign) {
  $cert = Get-SigningCert
  if (-not $cert) { "서명 인증서 없음 — 서명 건너뜀 (sign_tools.ps1 -New)"; return }
  foreach ($f in $Files) {
    $r = $null
    # 타임스탬프 서버가 잠깐 안 될 때가 있어 몇 번 다시 한다. 끝내 안 되면 타임스탬프 없이라도 서명
    # (그 경우 인증서가 만료되면 서명도 무효가 된다).
    for ($i = 1; $i -le 3 -and -not ($r -and $r.Status -eq "Valid"); $i++) {
      try { $r = Set-AuthenticodeSignature -FilePath $f -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $TimeStamp }
      catch { Start-Sleep -Seconds 2 }
    }
    if (-not $r -or ($r.Status -ne "Valid" -and $r.Status -ne "UnknownError")) {
      $r = Set-AuthenticodeSignature -FilePath $f -Certificate $cert -HashAlgorithm SHA256
    }
    # 루트를 아직 안 믿는 PC 에서는 'UnknownError'(체인 못 믿음)로 나오지만 서명 자체는 들어갔다
    "서명: $(Split-Path $f -Leaf) → $($r.Status)"
    if ($r.Status -ne "Valid" -and $r.Status -ne "UnknownError") { throw "서명 실패: $f ($($r.StatusMessage))" }
  }
}
