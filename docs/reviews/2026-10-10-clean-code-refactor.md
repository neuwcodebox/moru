# SOLID·클린 코드 리팩토링 — 2026-10-10

도메인·애플리케이션·SQLite·프롬프트 제공자·이미지 worker·인증·React의 책임 경계를
검토했다. 기존 엔진 port와 불변 기록 구조를 유지하고, 책임이 섞인 부분만 작게 분리했다.
제품 동작·DB 스키마·의존성은 변경하지 않았다. 현재 구조는 [TECH.md](../TECH.md)에 반영했다.

- `useGeneration`으로 App의 생성 접수·진행 조회·취소 상태를 분리했다. 대화 조회 실패 후에도
  접수된 작업을 계속 관찰하고, 완료 후 대화 갱신에 성공해야 입력을 다시 활성화한다.
- `images/files.py`로 PNG 검증과 저장 폴더 내부의 이미지 읽기를 옮겼다. 파일 형식·크기·손상과
  폴더 밖 경로의 오류 코드를 유지하고 기존 기록 보존·불완전 파일 정리를 검증했다.
- Application의 최근 대화 이력 구성을 `_prompt_history`로 분리했다. 재시도의 원래 기준,
  선택 버전·요청 수 제한·이력 비활성화·이후 행 및 다른 세션 제외 동작을 보존했다.
- 태그 검색 기본값을 빠뜨린 기존 bootstrap 테스트를 현재 명세에 맞게 갱신했다.

검증: `uv run pytest` 606개, 프론트엔드 `npm test` 179개, `npm run check`, `npm run build`,
`uv run ruff check src tests scripts app.py`, `git diff --check`가 통과했다. Python 검증에는
기존 임시 폴더 권한 충돌을 피하는 별도 pytest 임시·캐시 경로를 사용했다.
추가한 생성 관찰 테스트는 가상 타이머와 bridge 응답을 사용한다. 실제 GPU·모델 추론과
네이티브 WebView smoke는 이번 변경에서 실행하지 않았다.
