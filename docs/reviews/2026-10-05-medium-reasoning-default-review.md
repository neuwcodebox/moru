# 추론 수준 기본값을 보통으로 변경

`PromptSettings`의 추론 수준 기본값을 medium으로 변경했다.
컨텍스트 2048·출력 1024·thinking 켜짐은 유지한다. 기본 추론 예산은
최종 프롬프트 예약 후 남은 공간의 75%인 288토큰이다.
저장된 명시적 low/high 설정은 덮어쓰지 않는다.

API와 UI 기본값 검증을 갱신하고, 저장된 low/high 설정의 보존과 재시작 후
low 설정 복원을 검증했다. runtime smoke는 도메인의 기본값을 사용하며
portable smoke의 초기 설정 기대값도 medium으로 맞췄다.
기존 검토 기록에 기록된 당시의 low 검증 결과는 변경하지 않았다.

Python 전체 일반 테스트 186개, 프런트엔드 테스트 57개가 통과했다.
TypeScript 검사·production build·Ruff·diff 공백 검사도 통과했다.
기본값 변경은 모델·GPU 없이 설정 및 전달 경계의 테스트로 검증했다.
