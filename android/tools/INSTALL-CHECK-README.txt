카카오 메시지 필터 — Windows USB 설치 진단

용도
‘앱이 설치되지 않았습니다’라는 화면 대신 실제 INSTALL_FAILED 오류를 확인합니다.
같이 들어 있는 APK는 현재 0.1.3 버전입니다. 이 도구는 설치 오류 확인용입니다.
이 도구는 APK 체크섬을 검증하고 USB로 연결된 휴대폰에 설치를 시도합니다.
설치가 성공하면 휴대폰에 카카오 메시지 필터가 설치됩니다.

준비
1. Windows PC에 ZIP을 받아 ‘모두 압축 풀기’로 풉니다.
2. Python 3.11 이상과 Python Launcher가 필요합니다.
   앞서 PC 필터를 Python으로 설치했다면 그 Python을 사용할 수 있습니다.
3. 휴대폰 설정 → 휴대전화 정보 → 소프트웨어 정보 → 빌드번호를 7번 눌러
   개발자 옵션을 활성화하고, 개발자 옵션에서 USB 디버깅을 직접 켭니다.
4. 데이터 전송이 가능한 USB 케이블로 휴대폰 1대만 연결합니다.
5. install-check.cmd를 실행하고 휴대폰에 나오는 USB 디버깅 허용 창을 승인합니다.

결과
폴더의 INSTALL_RESULT.txt에 Result / Failure 오류가 기록됩니다.
Result가 SUCCESS라면 실제 설치가 성공한 것입니다.
실패하면 INSTALL_FAILED_... 또는 INSTALL_PARSE_FAILED_...가 들어 있는 줄을 알려주세요.
도구는 기기 모델, Android/SDK 버전, 이 APK 설치 결과만 기록합니다.
대화·계정·사진·전체 logcat은 수집하지 않고 결과를 자동으로 전송하지 않습니다.

참고
Google platform-tools를 공식 dl.google.com에서 다운로드하고 공식 SDK 메타데이터의
체크섬으로 검사합니다. 인터넷 연결이 필요합니다.
기기가 보이지 않으면 케이블, USB 디버깅 승인, Samsung USB 드라이버를 확인하세요.
제조사 드라이버 안내: https://developer.samsung.com/android-usb-driver
도구는 휴대폰 보안 설정이나 패키지 검증 설정을 바꾸지 않으며 앱을 삭제하지 않습니다.
진단 후 USB 디버깅 사용 여부는 휴대폰 설정에서 직접 관리할 수 있습니다.
