# 모델 준비 구조와 FLUX.2 확장 검토 — 2026-10-06

모델 준비를 프롬프트 작성과 이미지 생성 영역으로 나누고 이미지 파일은 계열 → 버전 순서로 탐색한다. 실제 모델 선택은 생성 설정에서만 저장하며 파일 준비는 생성값을 변경하지 않는다. 중복 프롬프트 제목과 불필요한 안내를 제거했다. 현재 동작은 [SPEC](../SPEC.md) §4·§9·§13, 모델 정의와 로딩 경계는 [TECH](../TECH.md) §12·§13에 둔다.

SDXL을 선택 목록·파일 준비·다운로드·추론에서 제거했다. 남아 있는 SDXL 생성 기록을 보존하기 위해 기록 복원에만 이전 이름·기본값을 허용한다. 기존 이미지 열람·Fork·현재 모델로 재생성과, 지원 종료된 모델의 설정 저장·재시도 거부를 검증한다. Anima의 분리 로딩·모델 종류 검사·로딩 오류·취소/OOM·버전 전환 캐시는 유지한다. 새 의존성이나 범용 플러그인은 추가하지 않았다.

FLUX.2 klein의 증류된 4B는 [공식 모델 카드](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) 기준 Apache 2.0, 4단계·guidance 1.0으로 대화형 반복 생성에 적합한 후보이다. 고정된 ComfyUI revision `f1072eb0350638a3390ddb6afbcaa8c6b237c6fd`에 `Flux2` 모델, `KleinTokenizer`·Qwen3 4B 인코더, FLUX2 VAE 지원이 이미 있다. [ComfyUI 공식 가이드](https://docs.comfy.org/tutorials/flux/flux-2-klein)의 FP8 diffusion·Qwen3 4B·flux2 VAE 세 파일을 모델 준비에 등록하고 자연어 작성 지침, 128채널/16배 latent와 해상도별 Flux2Scheduler에 대응하는 sigma 경로를 연결하면 텍스트 기반 생성에 기존 worker를 재사용할 수 있다. 엔진을 교체할 필요는 없으나 파일 목록 추가만으로 추론이 완성되지는 않는다.

- Python 전체 284개와 프론트엔드 전체 115개 통과. Ruff, TypeScript와 Vite 배포 빌드 통과. 모델 준비와 생성 선택의 분리, 선택된 버전의 필요 파일, SDXL 지원 제거와 기존 기록 보존, Anima 로딩 오류·버전 전환·취소/OOM을 GPU·네트워크 없이 검증했다.
- 기존 Anima Turbo의 실제 512×512 GPU 생성·PNG 검증은 성공했다.
- 현재 GPU는 RTX 3060 12GB다. FLUX 파일 다운로드·실제 추론·프롬프트 LLM과의 VRAM 병용·portable 패키징은 아직 검증하지 않았다. 공식 원본 기준 약 13GB 안내와 FP8 측정치는 정밀도·실행 환경이 다르므로 FP8·오프로딩을 기준으로 현재 앱에서 측정해야 한다. 참고 이미지 기반 편집은 현재 프롬프트 수정 후 새 생성 흐름과 별도 작업이다.
