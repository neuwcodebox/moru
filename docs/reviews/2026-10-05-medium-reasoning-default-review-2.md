# 패키지 UI 검사의 추론 기본값 확인 수정

실제 기본값은 medium인데 내부 UI smoke 코드에 low 기대값이 남아 있었다.
UI 선택값을 API에서 받은 추론 설정과 비교하도록 수정했다.
외부 portable smoke의 medium 기본값 검사는 유지한다.

Python 일반 테스트 186개와 Ruff 검사가 통과했다.
패키지의 앱 실행 검증은 사용자 요청에 따라 생략했다.
