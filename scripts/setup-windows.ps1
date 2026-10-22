$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 이상을 python.org에서 설치하세요 (Tcl/Tk 포함).' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '의존성 설치 실패' }
& .\.venv\Scripts\python.exe -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw '프로그램 설치 실패' }
& .\.venv\Scripts\python.exe -m kakao_filter --doctor
if ($LASTEXITCODE -ne 0) {
    throw 'Tesseract와 한국어/영어 언어 데이터를 설치한 뒤 다시 실행하세요. README.md 참고.'
}
Write-Host '설치 완료. .\.venv\Scripts\python.exe -m kakao_filter 명령으로 실행하세요.'
