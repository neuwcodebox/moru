# 구현 검토 기록 — 2026-10-04

`SPEC.md`의 완료 기준 13개를 구현과 테스트에 대조했다. 기능은 모두 구현되어 있다.
생성·Fork·저장·복원·모델 관리의 경계와 오류 경로를 검토하면서 아래 결함을 수정했다.
검증 범위는 현재 Windows PC, 선택한 HauhauCS Qwen3.5 GGUF, Anima Turbo/Aesthetic다.

| 완료 기준 | 구현 및 검증 근거 |
| --- | --- |
| 1. 첫 요청으로 이미지 생성 | `Application.submit_request`, `LlamaPrompts.create`, `ImageWorker`; conversation 테스트와 GPU smoke |
| 2. 직전 프롬프트를 기준으로 자연어 수정 | `Application._prepare_prompt`, `LlamaPrompts.refine`; canonical prompt 입력 테스트와 실제 LLM create/refine 검증 |
| 3. 요청과 이미지를 대화에 표시 | `Conversation`; Enter 전송·결과 표시 UI 테스트, portable smoke의 입력창 전송과 실제 이미지 표시 확인 |
| 4. 전체 화면 이미지 보기 | `Lightbox`; 확대·화면 맞춤·드래그·Esc 테스트 |
| 5. 이미지별 프롬프트 확인 | `Api.get_image_details`, `PromptDialog`; 기본 대화에서 프롬프트·메타데이터를 숨기는 테스트 |
| 6. 수동 프롬프트 Fork | `Application.generate_from_prompt`; LLM 우회·부모 관계·원본 불변 테스트와 UI 전송 테스트 |
| 7. 과거 이미지에서 자연어 Fork | `Application.fork`, 요청의 `base_image_id`; 선택한 프롬프트로 refine하는 테스트 |
| 8. 기존 가지 보존 | 불변 Image 기록, SQLite update 방지 trigger; sibling 보존·DB 실패 rollback 테스트 |
| 9. sibling branch 전환 | `Repository.select_branch`, `BranchSelector`; 경로·최신 자손 선택과 UI 테스트 |
| 10. 생성 설정 | `GenerationSettings`, `PromptSettings`, `SettingsDialog`; 검증·63-bit seed·작업 접수 시 설정 고정·설정 복원 테스트 |
| 11. 로컬 영구 저장 | SQLite transaction, PNG 검증, 원자적 이미지 저장; 손상 PNG·저장 실패·기존 파일 보존 테스트 |
| 12. 재시작 후 작업과 branch 복원 | current project/active leaf/Fork preferences; 복원·중단 요청 재시도 테스트 |
| 13. Windows portable | 고정된 core/runtime와 PyInstaller onedir 빌드; 개발 Python/Node/CUDA Toolkit을 PATH에서 제외한 실행 파일 smoke 및 ZIP 검사 |

수정한 결함:

- thinking 중 취소가 완료까지 지연됨: 내부 스트림을 토큰마다 확인하고 취소 시 generator를 닫는다. UI에는 최종 프롬프트만 전달한다.
- 고정 seed 생성에서 불필요한 난수 소스 의존: Auto일 때만 seed를 결정한다.
- 새 이미지 ID가 기존 파일명과 겹칠 때 원본을 덮어쓰거나 실패 정리 중 삭제할 수 있음: 기존 경로를 먼저 검사하고 추론을 시작하지 않는다.
- 종료된 worker 재시작 시 이전 pipe와 Windows Job 핸들이 남음: 재시작 전에 자원을 회수한다.
- 상태 콜백 예외와 취소가 겹친 경우 worker·출력 파일 정리가 불완전함: 예외 분류와 종료 경로를 통합한다.
- 같은 데이터 폴더의 두 번째 앱이 진행 중인 요청을 중단된 요청으로 변경함: SQLite 복구 전 OS 파일 잠금을 얻고 shutdown까지 유지한다.
- 재시도 접수 후 이전 실패 메시지가 남음: 모든 요청 시작 경로에서 대화 상태를 갱신한다.
- 수동 생성 접수 후 대화 갱신만 실패하면 팝업이 남아 중복 제출을 유도함: 접수된 job을 계속 관찰하고 갱신 오류를 별도로 표시한다.

리팩토링 범위:

- `Application`의 프롬프트 준비와 이미지 생성·검증을 짧은 함수로 분리했다. 작업 접수·취소·저장 흐름은 기존 service에 유지했다.
- 데스크톱 진입점은 worker 분기와 실행 잠금을 담당하고, 창과 엔진의 수명은 `_run_desktop`에서 관리한다.
- `Conversation`은 대화·branch·상태 표시를 담당한다. API 호출과 작업 상태 관리는 `App`에 남겼다.
- `GenerationProgress`로 중복된 진행·취소 표시를 모았다. 모델 이름은 작은 공유 상수로 분리해 팝업 간 의존을 제거했다.
- 기존 prompt/image port를 유지하고 취소 신호를 명시적으로 전달했다. 새 의존성, 범용 repository 계층, DI 컨테이너, 플러그인 구조는 추가하지 않았다.

자동 검증: Python 118개, UI 18개 테스트와 Ruff, TypeScript, Vite build가 통과했다.
실제 CUDA LLM의 프롬프트 생성·수정·thinking 중 취소·취소 후 재사용도 확인했다.
최신 실행 파일 smoke에서 고급 설정 저장·클립보드와 실제 입력창 → 1024×1024 이미지
대화창 표시 흐름이 통과했다. 기본 thinking/8192 context/4096 출력 한도를 사용했고,
저장된 프롬프트에 사고 과정이 없으며 종료 후 worker와 LLM이 정리됨을 확인했다.
GPU/WebView 검증은 opt-in smoke로 분리되어 일반 unit suite에서 실행되지 않는다.

추가 검증이 필요한 환경은 별도 Windows PC/다른 GPU·드라이버 조합, 임의의 다른 GGUF,
대규모 이력의 장기간 메모리 사용이다. 현재 UI는 선택 경로의 이미지를 모두 렌더링하며,
세션에서 읽은 이미지의 base64를 캐시하므로 이력이 매우 클 때의 메모리 상한은 보장하지 않는다.
