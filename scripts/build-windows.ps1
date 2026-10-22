$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$Python = if (Test-Path '.\.venv\Scripts\python.exe') { '.\.venv\Scripts\python.exe' } else { (Get-Command python).Source }
& $Python -m pip install 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 설치 실패' }
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name KakaoMessageFilter --collect-all mss --collect-all pytesseract run_filter.py
if ($LASTEXITCODE -ne 0) { throw '실행 파일 빌드 실패' }
Write-Host 'dist\KakaoMessageFilter.exe 생성 완료. Tesseract는 별도 설치가 필요합니다.'
