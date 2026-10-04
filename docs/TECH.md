# TECH.md

# 로컬 대화형 이미지 생성기 — 기술 설계서

## 1. 목표

`SPEC.md`를 최소한의 실행 구성으로 구현한다.

최종 사용자는 내부 기술을 알 필요가 없다.

사용자 경험:

```text
Moru.zip 압축 해제
→ Moru.exe 실행
→ 앱 창
→ 자연어 입력
→ 이미지 생성
```

사용자에게 Python, Node.js, ComfyUI, 콘솔, localhost 서버를 노출하지 않는다.

---

## 2. 기술 스택

### 애플리케이션

- Python 3.12
- `uv` — Python 버전, 가상환경, 의존성, lockfile 관리
- pywebview — 데스크톱 WebView shell
- SQLite — 작업/이미지/Fork 이력
- PyInstaller onedir — Windows standalone 패키징

### 프론트엔드

- React
- TypeScript
- Vite

React는 개발 시에만 Node.js를 사용한다.

Release에는 `vite build` 결과물만 포함하며 Node.js 런타임은 포함하지 않는다.

### Prompt LLM

- llama-cpp-python
- CUDA 활성화
- 작은 GGUF Instruct 모델
- 자연어 → 이미지 프롬프트 생성/수정 전용

### 이미지 생성

- PyTorch + CUDA
- ComfyUI core/backend
- Anima Turbo / Anima Aesthetic

ComfyUI의 웹 UI와 노드 편집기는 사용하지 않는다.

검증한 ComfyUI revision을 고정하고 내부 추론 엔진으로만 사용한다.

---

## 3. 개발 환경

Python 환경은 `uv`를 단일 도구로 사용한다.

저장소 예:

```text
app/
├─ pyproject.toml
├─ uv.lock
├─ src/
├─ frontend/
├─ vendor/
│  └─ comfyui/
└─ scripts/
```

기본 명령:

```bash
uv sync
uv run python -m app
uv run pytest
```

개발 의존성도 `pyproject.toml`의 dependency group으로 관리한다.

예:

```toml
[dependency-groups]
dev = [
  "pytest",
  "ruff",
  "pyinstaller",
]
```

원칙:

- `requirements.txt`를 수동 관리하지 않는다.
- Python 패키지 버전은 `uv.lock`으로 고정한다.
- CI와 개발 환경 모두 `uv sync --frozen`을 사용한다.
- PyTorch CUDA wheel 등 별도 index가 필요한 패키지도 `uv` 설정으로 관리한다.

ComfyUI는 일반 pip dependency로 느슨하게 따라가지 않고 검증한 commit/revision을 고정한다.

---

## 4. 최종 런타임 구조

```text
┌──────────────────────────────────┐
│            Moru.exe             │
│                                  │
│  Python Main Process             │
│  ├─ pywebview                    │
│  │   └─ React static UI          │
│  ├─ Application Service          │
│  ├─ SQLite                       │
│  └─ Prompt LLM / CUDA            │
│                                  │
│  Hidden Image Worker             │
│  └─ ComfyUI core + Anima / CUDA  │
└──────────────────────────────────┘
```

이미지 worker는 내부 구현이다.

사용자는 이를 실행하거나 관리하지 않는다.

---

## 5. pywebview + React

### 5.1 Release UI

React를 빌드한다.

```bash
npm run build
```

생성된 정적 파일을 Python package resource로 포함한다.

```text
src/app/web/
├─ index.html
└─ assets/
```

pywebview가 해당 UI를 앱 창으로 연다.

외부 브라우저를 실행하지 않는다.

### 5.2 React ↔ Python

HTTP 서버를 만들지 않는다.

pywebview의 JS bridge를 사용한다.

Python API 예:

```python
class Api:
    def get_project(self, project_id): ...
    def create_project(self): ...
    def submit_request(self, project_id, text, base_image_id=None): ...
    def fork(self, image_id): ...
    def generate_from_prompt(self, image_id, prompt): ...
    def get_settings(self): ...
    def update_settings(self, settings): ...
```

React:

```ts
window.pywebview.api.submit_request(...)
```

모든 실제 상태와 비즈니스 로직은 Python이 관리한다.

React는 표현 계층으로 제한한다.

---

## 6. 비동기 처리

LLM 추론과 이미지 생성은 UI thread에서 실행하지 않는다.

Python main process에서 background executor/task queue를 사용한다.

상태:

```text
queued
prompting
loading_model
generating
completed
failed
cancelled
```

pywebview bridge를 통해 polling하거나 Python → JS event dispatch로 진행 상태를 전달한다.

MVP에서는 단일 generation queue만 허용한다.

동시에 여러 이미지를 생성하지 않는다.

---

## 7. Prompt LLM

### 7.1 역할

Prompt LLM은 Agent가 아니다.

도구 호출, 계획, 일반 채팅을 하지 않는다.

역할:

- 새 이미지 프롬프트 작성
- 기존 이미지 프롬프트 자연어 수정

### 7.2 새 이미지

입력:

```text
SYSTEM
+ 사용자 자연어 요청
```

출력:

```text
완성된 Anima 이미지 생성 프롬프트
```

### 7.3 수정

입력:

```text
SYSTEM
+ 기준 이미지의 실제 프롬프트
+ 사용자 수정 요청
```

출력:

```text
수정된 전체 Anima 이미지 생성 프롬프트
```

전체 대화 로그를 LLM context로 넣지 않는다.

기준 이미지의 실제 프롬프트가 현재 상태의 canonical representation이다.

---

## 8. Prompt LLM 실행 방식

`llama-cpp-python`을 Python에서 직접 사용한다.

예:

```python
from llama_cpp import Llama

llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=2048,
)
```

기본적으로 CUDA GPU를 사용한다.

권장 모델 크기:

- 1B ~ 4B
- GGUF Q4/Q5
- instruction-following이 안정적인 모델

Prompt 작성 성능을 우선하며 고난도 reasoning 성능은 요구하지 않는다.

---

## 9. GPU 메모리 정책

Prompt LLM과 Anima 모두 GPU를 사용한다.

기본 전략:

1. Prompt LLM을 GPU에 로드한다.
2. 프롬프트 생성 후 Anima generation을 실행한다.
3. 실제 VRAM 사용량이 허용하면 둘을 상주시킨다.

VRAM 부족 시 fallback:

- Prompt LLM 객체 unload
- CUDA 메모리 반환 확인
- Anima generation 수행
- 다음 Prompt 요청에서 LLM lazy reload

CPU-only 추론은 기본 경로로 사용하지 않는다.

실제 대상 GPU에서 측정 후 residency 정책을 결정한다.

---

## 10. ComfyUI 사용 원칙

ComfyUI는 사용자 앱이 아니라 내부 inference dependency다.

다음은 사용하지 않는다.

- ComfyUI 웹 화면
- 노드 편집기
- 브라우저 접속
- 사용자가 실행하는 ComfyUI 서버
- 사용자 workflow 파일 편집

사용하는 것:

- Anima model loader
- text encoder / VAE loader
- sampler
- execution backend

검증된 ComfyUI commit을 프로젝트에 고정한다.

업스트림 최신 버전을 자동으로 따라가지 않는다.

---

## 11. 이미지 Worker

ComfyUI inference는 메인 UI process에서 분리한다.

이유:

- GPU OOM/모델 오류가 UI process 전체를 죽이지 않도록 함
- 모델 lifecycle 분리
- ComfyUI global state 격리
- 취소/재시작 단순화

### 11.1 배포 시 실행 방식

별도 사용자가 실행하는 프로그램을 만들지 않는다.

패키징된 `Moru.exe`가 자기 자신을 내부 worker mode로 실행한다.

예:

```text
Moru.exe
Moru.exe --internal-image-worker
```

두 번째 모드는 앱이 자동으로 숨겨서 실행한다.

Windows console 창은 생성하지 않는다.

사용자에게 worker process를 노출하지 않는다.

### 11.2 IPC

stdio 기반 JSON Lines를 사용한다.

HTTP/localhost 서버를 만들지 않는다.

요청:

```json
{
  "id": "job-1",
  "type": "generate",
  "payload": {
    "model": "anima-turbo-v1.1",
    "prompt": "...",
    "width": 1024,
    "height": 1024,
    "steps": 10,
    "cfg": 1.0,
    "seed": 12345,
    "output_path": "..."
  }
}
```

응답:

```json
{
  "id": "job-1",
  "type": "progress",
  "payload": {
    "step": 4,
    "total": 10
  }
}
```

완료:

```json
{
  "id": "job-1",
  "type": "result",
  "payload": {
    "image_path": "...",
    "seed": 12345
  }
}
```

---

## 12. 고정 Anima Workflow

사용자가 workflow를 구성하지 않는다.

앱 내부에 고정된 text-to-image workflow를 코드로 정의한다.

개념:

```text
Prompt
→ Text Encoder
→ Anima Diffusion Model
→ Sampler
→ VAE Decode
→ PNG
```

지원 모델:

- Anima Turbo
- Anima Aesthetic

모델별 sampler/scheduler 기본값은 코드의 preset으로 관리한다.

Sampler/Scheduler는 MVP 설정 UI에 노출하지 않는다.

---

## 13. 모델 파일

예:

```text
models/
├─ anima/
│  ├─ diffusion_models/
│  │  ├─ anima-turbo-v1.1.safetensors
│  │  └─ anima-aesthetic-v1.1.safetensors
│  ├─ text_encoders/
│  │  └─ qwen_3_06b_base.safetensors
│  └─ vae/
│     └─ qwen_image_vae.safetensors
│
└─ prompt/
   └─ prompt-model.gguf
```

모델 위치는 설정 파일로 override 가능하게 한다.

---

## 14. 모델 다운로드

기본 portable ZIP은 모델을 제외할 수 있다.

첫 실행 시 필요한 모델이 없으면 앱 UI 안에서 다운로드한다.

사용자에게 내부 파일명이나 Hugging Face 구조를 노출할 필요는 없다.

모델 manifest 예:

```json
{
  "anima-turbo-v1.1": {
    "url": "...",
    "sha256": "...",
    "size": 4180000000
  }
}
```

다운로드 요구사항:

- 진행률 표시
- `.part` 임시 파일
- 중단/실패 후 기존 정상 파일 보존
- SHA-256 검증
- 완료 후 atomic rename

선택적으로 모델 포함 Full ZIP도 만들 수 있다.

---

## 15. 데이터 저장

SQLite + PNG를 사용한다.

portable 기본값:

```text
Moru/
├─ Moru.exe
├─ runtime/
├─ models/
└─ data/
   ├─ anima.db
   └─ images/
```

사용자가 폴더 전체를 이동해도 동작할 수 있도록 가능한 한 상대 경로를 사용한다.

---

## 16. DB 모델

핵심 테이블:

```text
projects
requests
images
```

`images.parent_image_id`로 Fork tree를 구성한다.

각 이미지에는 최소 다음을 저장한다.

- project ID
- parent image ID
- request ID
- 실제 prompt
- image path
- model
- width
- height
- steps
- cfg
- seed
- created_at

생성된 Image record는 수정하지 않는다.

Fork는 새 Image record를 만든다.

---

## 17. 현재 대화 경로

UI에는 전체 tree를 표시하지 않는다.

현재 active leaf에서 parent를 따라 root까지 올라간 뒤 reverse하여 현재 대화 경로를 계산한다.

분기점에는 sibling child count를 조회해:

```text
‹ 1 / 3 ›
```

형식의 selector를 표시한다.

---

## 18. 자연어 생성 처리

기준 이미지 우선순위:

1. 사용자가 Fork 버튼으로 선택한 이미지
2. 현재 active leaf
3. 없음

기준 이미지 없음:

```text
자연어 요청
→ Prompt LLM create
→ Anima
→ root Image
```

기준 이미지 있음:

```text
기준 Image.prompt
+ 자연어 요청
→ Prompt LLM refine
→ Anima
→ child Image
```

---

## 19. 수동 프롬프트 Fork

이미지의 프롬프트 팝업에서 직접 수정 후 생성할 때:

- Prompt LLM 호출 안 함
- 선택 이미지가 parent
- 편집된 prompt를 그대로 Anima에 전달
- 새 child Image 생성

원본 이미지와 기존 child branch는 보존한다.

---

## 20. 이미지 뷰어

이미지를 클릭하면 React modal/lightbox로 표시한다.

지원:

- fit
- zoom
- pan
- Esc close

Python backend 호출은 필요하지 않다.

---

## 21. 생성 설정

Python이 canonical settings를 관리한다.

```python
@dataclass
class GenerationSettings:
    model_id: str
    width: int
    height: int
    steps: int
    cfg: float
    seed: int | None
```

`seed=None`은 Auto.

기본 Steps는 10, CFG는 1.0이다.

실제 생성 직전에 seed를 확정하고 DB에 실제 값을 저장한다.

---

## 22. 패키징

### 22.1 목표

일반 사용자는 다음만 수행한다.

```text
ZIP 다운로드
→ 압축 해제
→ Moru.exe 더블클릭
```

### 22.2 방식

기본 선택:

- PyInstaller `onedir`
- `windowed/noconsole`
- 결과 폴더 전체를 ZIP으로 배포

`onefile`은 사용하지 않는다.

### 22.3 포함 대상

- Python runtime
- Python dependencies
- pywebview
- React build
- PyTorch/CUDA 관련 DLL
- llama-cpp-python CUDA binary
- pinned ComfyUI core
- application code

사용자가 Python이나 Node.js를 설치할 필요가 없어야 한다.

---

## 23. Release 구조

예:

```text
Moru/
├─ Moru.exe
├─ runtime/
│  └─ ...
├─ models/
├─ data/
└─ licenses/
```

`runtime` 내부 구조는 사용자 API가 아니며 변경 가능하다.

사용자가 직접 실행해야 하는 파일은 `Moru.exe` 하나다.

---

## 24. Portable 요구사항

- 설치 프로그램 없음
- 레지스트리 등록 필수 기능 없음
- 시스템 Python 사용 금지
- 사용자 PATH 변경 금지
- 관리자 권한 불필요
- 앱 폴더 이동 가능
- data/models 폴더를 앱과 함께 이동 가능
- 앱 삭제는 폴더 삭제로 완료

Windows WebView2 Runtime이 없는 환경은 별도 고려한다.

가능하면 설치 여부를 감지하고 명확한 안내를 제공한다.

---

## 25. 프로세스 Lifecycle

앱 시작:

```text
Moru.exe
→ DB open
→ pywebview
→ Prompt LLM lazy
→ Image Worker lazy
```

첫 이미지 생성:

```text
Image Worker start hidden
→ ComfyUI/Anima load
→ generation
```

앱 종료:

```text
generation cancel
→ image worker shutdown
→ DB close
→ main process exit
```

비정상 종료 후 orphan worker가 남지 않도록 parent PID 감시를 구현한다.

---

## 26. 오류 처리

안정적인 내부 error code를 사용한다.

예:

```text
PROMPT_MODEL_NOT_FOUND
PROMPT_LLM_FAILED
IMAGE_MODEL_NOT_FOUND
IMAGE_WORKER_START_FAILED
MODEL_LOAD_FAILED
CUDA_OOM
INVALID_SETTINGS
GENERATION_CANCELLED
GENERATION_FAILED
IMAGE_SAVE_FAILED
DATABASE_FAILED
```

사용자에게는 간결한 한국어 메시지를 표시한다.

상세 traceback은 로그에만 기록한다.

---

## 27. 로그

portable data 폴더:

```text
data/logs/app.log
data/logs/image-worker.log
```

기록:

- 앱 시작/종료
- worker 시작/종료
- 모델 load/unload
- generation ID
- 실행 시간
- 오류 code/traceback

기본 로그에는 전체 사용자 요청이나 전체 실제 prompt를 남기지 않는다.

---

## 28. 테스트

### Unit

- 새 작업 생성
- root/child 생성
- Fork 기준 선택
- root → leaf 경로 계산
- sibling branch 이동
- Prompt create/refine 입력 구성
- generation settings validation
- Auto seed
- DB repository

### Integration

Mock LLM + Mock Image Worker:

1. 첫 요청 → root image
2. 수정 요청 → child image
3. 과거 이미지 Fork → sibling
4. prompt manual Fork
5. branch switch
6. generation failure → tree 유지
7. restart → state 복구

### Runtime Smoke

실제 GPU 환경:

- Prompt LLM CUDA
- Anima Turbo
- Anima Aesthetic
- LLM + Anima 동시 VRAM
- OOM fallback
- worker restart
- packaged portable build 실행

---

## 29. 구현 순서

### Phase 1 — Shell/UI

- `uv` 프로젝트 생성
- pywebview
- React/Vite
- conversation UI
- image lightbox
- settings
- mock generation

### Phase 2 — Persistence

- SQLite
- Project / Request / Image tree
- Fork
- branch selector
- restart recovery

### Phase 3 — Prompt LLM

- llama-cpp-python CUDA
- create/refine system prompt
- GPU residency 측정

### Phase 4 — Image Engine

- pinned ComfyUI core
- hidden image worker
- Anima Turbo
- progress/cancel
- Aesthetic

### Phase 5 — Distribution

- model downloader
- PyInstaller onedir
- no-console worker spawning
- portable ZIP
- clean Windows machine smoke test

---

## 30. 구현 원칙

- `SPEC.md`가 사용자 동작의 최종 기준이다.
- Python 개발 환경은 `uv`로만 관리한다.
- 메인 UI는 대화창 하나로 유지한다.
- Prompt LLM은 Agent로 만들지 않는다.
- 자연어 요청을 보내면 항상 이미지까지 생성한다.
- Prompt LLM은 GPU를 기본으로 사용한다.
- ComfyUI는 내부 inference dependency일 뿐 사용자에게 노출하지 않는다.
- ComfyUI UI/노드 편집기를 앱에 포함하지 않는다.
- 내부 worker는 앱이 자동 시작·종료한다.
- 사용자가 서버/스크립트/콘솔을 실행하게 하지 않는다.
- 이미지 결과는 불변이며 수정은 항상 Fork다.
- release 사용자는 Python/Node/ComfyUI를 설치하지 않는다.
- release는 portable ZIP이며 실행 진입점은 `Moru.exe` 하나다.

## 31. 구현 및 고정 런타임

애플리케이션 패키지는 `src/moru/`이며 UI 리소스는 `src/moru/web/index.html`이다.
React/Vite 빌드에서 JS와 CSS를 HTML에 포함하여 HTTP 서버 없이 로드한다.
개발 시 `uv run --extra inference python -m moru` 또는 `python -m app`을 사용한다.

모델과 GPU가 필요 없는 일반 테스트 환경과 실제 추론 환경을 구분하기 위해
큰 추론 의존성은 `inference` extra로 관리한다. 앱 실행 및 배포 빌드는
`uv sync --frozen --extra inference`로 환경을 준비한다.

ComfyUI core는 `vendor/comfyui-revision.txt`에 기록된
`f1072eb0350638a3390ddb6afbcaa8c6b237c6fd`를 사용한다. 노드나 서버를
로드하지 않고 core의 모델 로딩·샘플링·VAE API를 직접 호출한다.
Qwen Image VAE의 단일 이미지 출력도 시간 축을 포함할 수 있으므로
`[batch, time, height, width, channels]`에서 단일 프레임을 추출한다.

현재 검증한 추론 조합은 PyTorch 2.8 CUDA 12.8 wheel과
llama-cpp-python 0.3.36 CUDA 12.4 Windows wheel이다. llama.cpp CUDA DLL은
패키지에 포함된 PyTorch CUDA 라이브러리를 사용하며 시스템 CUDA Toolkit에
의존하지 않는다. 정확한 패키지와 모델 다운로드 버전은 `uv.lock`과
`src/moru/model-manifest.json`에 고정한다.

Windows worker는 부모 PID 감시와 `KILL_ON_JOB_CLOSE` Job Object를 함께
사용하여 worker가 생성한 하위 프로세스도 종료한다. `windowed` 실행 파일에서는
Python의 stdio 객체가 없으므로 상속받은 Windows pipe handle로 JSON Lines
스트림을 복구한다.

데스크톱 프로세스는 SQLite 복구 전에 `data/.instance.lock`의 OS 파일 잠금을 얻고,
worker와 executor 종료까지 유지한다. 같은 저장 폴더의 두 번째 실행은 기존 요청을
복구 대상으로 변경하지 않고 기존 창 사용을 안내한다. 프로세스가 종료되면 OS가
잠금을 해제하므로 이전 실행의 lock 파일이 남아도 재시작할 수 있다.

GPU 및 실제 WebView2 검증은 `scripts/smoke_*.py`에 분리되어 있으며
일반 `uv run pytest`에서는 실행하지 않는다.

프롬프트 LLM의 thinking은 기본적으로 끈다. 사고 과정은 생성용 프롬프트에서 제외하고
완성된 최종 프롬프트만 Anima에 전달한다. `prompting` 상태는 대화의 생성 placeholder에
표시하며, 토큰 제한 때문에 잘린 응답은 오류로 처리한다.
기본 프롬프트 모델은 HauhauCS Qwen3.5-4B Uncensored Aggressive Q4_K_M이다.
기본 context는 2048, 출력 한도는 1024 tokens로 설정한다.
생성 설정의 고급 영역에서 두 한도와 thinking 사용 여부를
변경할 수 있다. 불변 `PromptSettings`는 이미지 설정과 함께 preferences에 원자적으로
저장되며 작업 접수 시 고정한다. 현재 작업에는 저장 후 변경한 값을 적용하지 않는다.
컨텍스트 또는 모델 경로가 변경되면 다음 LLM 호출에서 모델을 다시 로드한다.
출력 한도 및 thinking 변경은 모델을 재사용한다. GGUF의 chat template에
`enable_thinking`을 명시하여 기존 템플릿의 thinking 분기를 선택한다.
해당 기능이 없는 템플릿에 thinking 끄기를 요청하면 명시적 오류를 반환한다.

LLM 응답은 내부에서 스트리밍으로 소비하며 토큰마다 취소 여부를 확인한다.
취소 시 completion generator를 닫고 이미지 생성으로 넘어가지 않는다.
프로젝트 소유 `PromptProgress` callback은 thinking과 프롬프트를 분리해 전달한다.
Job에 임시 텍스트를 저장하고 기존 polling bridge로 placeholder를 갱신한다.
제어 태그가 토큰 경계에서 나뉘어도 표시하지 않으며, 정상 종료된 전체 응답에서만
이미지 생성용 최종 프롬프트를 추출한다. 임시 텍스트는 DB·로그에 저장하지 않고
성공·실패·취소 후 Job에서도 지운다. 표시용 문자열은 각각 최대 65536자로 제한한다.
이미지 생성 중에는 같은 placeholder에 step/전체 steps와 진행률을 표시한다.

이전 기본 설정 8192/4096/thinking 켜짐은 최초 실행 시 한 번 새 기본값으로 전환한다.
`prompt_defaults_version`을 preferences에 기록하여 이후 사용자가 같은 값을 명시적으로
저장해도 재전환하지 않는다. 그 외의 기존 사용자 설정은 보존한다.

아이콘은 `lucide-react`의 개별 component import를 사용한다. 전송/중지는 하나의 버튼이며,
이미지 뷰어는 Modal의 한 줄 toolbar에 맞춤·확대/축소·닫기를 함께 배치한다.
모델 상태 bridge는 선택된 파일 이름만 전달하여 전체 경로를 UI에 노출하지 않는다.

HTML을 직접 로드한 WebView2에서는 브라우저 Clipboard API를 사용할 수 없으므로
프롬프트 복사는 Python bridge로 전달하여 Windows UI thread의 클립보드 API를 사용한다.
