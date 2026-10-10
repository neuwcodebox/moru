# TECH.md

# 로컬 대화형 이미지 생성기 — 기술 설계서

## 1. 목표

`SPEC.md`를 최소한의 실행 구성으로 구현한다.

최종 사용자는 내부 기술을 알 필요가 없다.

사용자 경험:

```text
Moru.7z 압축 해제
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
- 선택적 ChatGPT: SIWC OAuth + Responses API, PyJWT[crypto] 서명 검증, Windows DPAPI 토큰 저장

### 이미지 생성

- PyTorch + CUDA
- ComfyUI core/backend
- Anima Turbo / Anima Aesthetic / FLUX.2 klein 4B

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
│  └─ Prompt provider              │
│      ├─ Local LLM / CUDA         │
│      └─ ChatGPT / HTTPS          │
│                                  │
│  Hidden Image Worker             │
│  └─ ComfyUI core / CUDA          │
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

메인 UI는 외부 브라우저를 실행하지 않는다. ChatGPT OAuth 로그인은 시스템 브라우저를 사용한다.

### 5.2 React ↔ Python

메인 UI용 HTTP 서버를 만들지 않는다. ChatGPT 로그인 동안만 `127.0.0.1`의 임시 OAuth 콜백 리스너를 사용한다.

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
loading_prompt_model
thinking
searching_tags
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

아래 상세 지침·실행 방식은 로컬 LLM을 설명한다. ChatGPT는 동일한 create/refine 역할을
수행하며 계정·HTTP 구현은 [ChatGPT 프롬프트 제공자](#chatgpt-프롬프트-제공자)에 별도로 설명한다.

### 7.1 역할

로컬 LLM은 이미지 프롬프트와 검색어를 작성한다. 단보루 조회·결과 정리·재시도는
애플리케이션이 수행하며, 검색어 작성과 최종 프롬프트 작성은 각각 한 번 호출한다.

역할:

- Anima용 검색어 일괄 작성
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

최근 성공한 요청 n개와 각 행의 선택된 결과 프롬프트를 user/assistant 쌍으로 전달한다. 기본 n=4이며 고급 설정에서 0~20개로 변경한다. 현재 기준 행 이후의 대화와 다른 세션은 제외한다. 기준 프롬프트와 이번 요청을 마지막 user 메시지에 명시한다.

GGUF 채팅 템플릿을 렌더링한 뒤 tokenizer로 입력 토큰 수를 계산한다. context_size - max_tokens를 초과하면 오래된 완전한 user/assistant 쌍부터 제거한다. 현재 기준과 새 요청까지 초과하면 PROMPT_CONTEXT_TOO_LONG 오류를 반환한다. 현재 입력을 조용히 자르거나 다른 모델을 사용하지 않는다.

로컬 LLM의 시스템 지침은 이미지 생성 모델용 영어 positive prompt 작성으로 표현한다. 모델 이름을 지침에 넣지 않는다. 관련 booru 태그와 관계·위치의 자연어 묘사를 혼합하고, 소문자/공백 태그 및 요청된 아티스트의 @ 접두사를 사용한다. Aesthetic 설정일 때 score_* 제외 지침을 추가한다. 비라틴 문자로 작성된 최종 응답은 오류로 처리해 이미지 모델에 넘기지 않는다. 참고: https://huggingface.co/circlestone-labs/Anima#prompting

기준 이미지의 실제 프롬프트가 현재 상태의 canonical representation이다.

### 7.4 로컬 태그 검색

`prompts/tag_search.py`가 쿼리 지침·형식 검증·선택적 조회·참고 자료 구성을 담당한다.
`LlamaPrompts`는 모델 적재·재사용과 두 작성 단계를 연결하며, `prompts/completion.py`는
추론 종료·한 문단 종료·스트림 읽기를 담당한다. 검색어 작성과 최종 작성은 같은 적재 모델을 사용한다.
`PromptSettings.tag_search_enabled`가 꺼져 있으면 검색·참고 자료 예약 없이 최종 작성만 수행한다.
검색 단계는 짧은 전용 system과 현재 프롬프트·최신 요청·보존한 이력을 사용하며,
전체 작성 지침이나 정적 태그표를 넣지 않는다. 영어 검색 개념을 쉼표로 구분한 한 줄로 받고,
정규화·중복 제거 후 최대 5개만 검색한다. 조회할 개념이 없으면 `none`을 반환한다.
검색과 최종 작성은 같은 추론 함수·사용자 설정을 사용한다. 출력·thinking 예산과 sampling,
추론 종료 제어·한 문단 종료·영어 응답 검증을 공유하며 별도 JSON 문법이나 검색 전용 한도는 없다.
추론 종료 시 공통 `Final answer:` 안내를 사용하고, 응답에서 안내와 사고 과정을 제거한다.

`TagSearch`는 `ports.TagSearcher`의 `search_tags` 계약으로 검색어마다 최대 8개 후보 이름을 받는다.
외부 조회·후보 검증과 진행·소스 전달을 분리하며, 조회 불가는 반환 자료의 타입 대신 명시적으로 판정한다.
`get_tag_info`와 `get_related_tags`는 호출하지 않는다. 두 제공자는 desktop 조립 단계에서
같은 카탈로그·HTTP 캐시·속도 제한을 공유하며, 조회 기한과 429 재시도는
[단보루 HTTP 정책](#chatgpt-프롬프트-제공자)을 따른다.

최종 작성 입력에는 정적 지침과 검색어별 후보 목록을 넣는다. 참고 자료는 최대 256토큰을
예약하고 실제 채팅 템플릿의 tokenizer로 전체 입력·출력 예약 공간 안에 들어오는 후보만 추가한다.
개념별로 후보를 하나씩 배정하고 중복 태그는 한 번만 전달한다. 예약 때문에 이력이 넘치면
오래된 완전한 턴부터 제외하며 두 단계에 같은 이력을 전달한다. 현재 프롬프트·최신 요청은 보존한다.
최종 작성의 출력·thinking 설정은 바꾸지 않는다.

쿼리 형식 오류·빈 응답·비영어 응답·출력 초과는 코드만 로그에 남기고 최종 작성을 계속한다.
조회 불가는 소스에 기록하고 이후 조회를 멈추며 확보한 후보는 활용한다. 추론 엔진 오류와
취소는 전파한다. 검색용 원문과 사고 과정은 progress·소스·로그에 전달하지 않는다.
검색어 개수·찾은 태그 수·추가 입력 토큰 수만 진단 로그에 기록한다.
`on_ready`는 첫 추론 직전에 한 번 알리고 `on_stage`와 `on_source`로 기존 진행 표시·소스 저장을 사용한다.
FLUX.2는 검색 단계 없이 기존 자연어 프롬프트를 작성한다.

---

## 8. Prompt LLM 실행 방식

`llama-cpp-python`을 Python에서 직접 사용한다.

예:

```python
from llama_cpp import Llama

llm = Llama(
    model_path=model_path,
    n_gpu_layers=-1,
    n_ctx=4096,
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

로컬 Prompt LLM과 이미지 모델은 GPU를 사용한다. ChatGPT 프롬프트 작성은 GPU 예산을 예약하지 않는다.

`Application`은 두 엔진의 좁은 메모리 계약으로 추론 단계 전 VRAM을 확보한다.
CUDA 측정과 ComfyUI 모델 해제는 이미지 worker 안에서 수행하며 main에 PyTorch를 로드하지 않는다.

1. Prompt LLM의 파일·컨텍스트가 이미 적재된 상태와 같으면 추가 로딩 예산은 0이다.
   새 로딩에는 GGUF 크기의 110%, 컨텍스트 토큰당 256KiB, 여유 1GiB를 예약한다.
   worker는 필요할 때 이미지 가중치를 GPU에서 내리고 PyTorch allocator cache를 반환한다.
2. 이미지 생성 전 선택한 세 파일 크기의 110%와 1024²당 2GiB 작업 공간(최소 1GiB),
   여유 1GiB를 합산한다. 측정한 free VRAM과 worker가 반환 가능한 allocated VRAM을
   합쳐도 이 예산에 못 미치면 Prompt LLM을 먼저 unload한다. 충분하면 상주 상태를 유지한다.
3. 실제 `CUDA_OOM`이면 Prompt LLM을 unload하고 동일 프롬프트·설정·seed로 한 번 재시도한다.
   다음 자연어 요청에서 LLM을 lazy reload한다. 반복 실패는 명시적 오류로 처리한다.

예산은 공존을 위한 보수적 추정이며 정확한 최고 사용량이나 메모리 상한이 아니다.
현재 이미지 예산은 인코더 입력 길이와 CFG에 따른 추가 작업량을 반영하지 않는다.
ComfyUI는 생성 단계별 이미지 가중치의 GPU/CPU 이동을 계속 관리한다.
사전 판단의 요구량·가용량·해제 여부는 진단 로그에 기록한다.
완료된 이미지의 저장 후 사용하지 않는 CUDA allocator cache를 반환하고 모델 객체는 유지한다.
CPU-only 추론이나 모델·해상도·컨텍스트의 자동 변경은 하지 않는다.

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

`reserve_memory(required_bytes)` 요청은 프롬프트 로딩 공간을 확보하고,
`memory_budget(settings, paths)` 요청은 `release_prompt` boolean을 반환한다.
두 요청은 생성 요청과 같은 ID 검증·취소·worker 실패 경로를 사용한다.

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

## 12. 계열별 고정 생성 경로

사용자가 workflow를 구성하지 않는다.

앱 내부에 지원 계열의 text-to-image 경로를 코드로 정의한다.

개념:

```text
Prompt
→ Text Encoder
→ Diffusion Model
→ Sampler
→ VAE Decode
→ PNG
```

지원 모델:

- Anima Turbo
- Anima Aesthetic
- FLUX.2 klein 4B (증류 버전, FP8)

`models.py`의 작은 정의 목록이 ID, 계열/버전/표시 이름, 필요 asset과 런타임 역할,
Steps/CFG 및 sampler/scheduler 기본값, 자연어 작성 여부와 프롬프트 보충 지침을 관리한다.
파일 경로 해석·준비 검사·설정 검증·추론과 bridge 카탈로그는 이 정의를 사용한다.
다운로드 URL·크기·해시는 기존 manifest에 유지한다. 기존 Anima ID·경로 키·저장 schema는 유지한다.

Anima는 diffusion/encoder/VAE를 분리 로드한다. 로드된 모델의 계열과 필수 구성요소를
확인하고 맞지 않으면 `MODEL_LOAD_FAILED`를 반환한다. 자동 대체는 없다.
로드 캐시는 계열과 경로를 함께 비교하며 전환 시 이전 모델을 unload한다.
FLUX.2도 분리 로드하며 encoder에 `CLIPType.FLUX2`를 지정한다. diffusion은 `model_base.Flux2`,
VAE는 128채널/16배 구조인지 확인한다. Euler, Steps 4, CFG 1을 기본으로 하고 positive를
영점화한 negative와 128채널/16배 latent를 사용한다. `images/schedule.py`는 고정 revision의
`Flux2Scheduler`와 같은 해상도·Steps별 sigma를 계산해 core sampler에 전달한다.
ComfyUI 노드·서버는 로드하지 않는다. 진행·취소·OOM 처리·원자적 PNG 저장은 두 계열이
기존 경로를 공유하며 사용자 Steps·CFG·Seed는 그대로 전달한다.

프롬프트 LLM의 `512 + 128` 출력 예약과 이미지 인코더의 토큰 길이는 별도 단위다.
현재 고정 ComfyUI의 Anima는 Qwen3와 T5 토큰을 함께 사용하고 adapter 결과를 최소 512까지
패딩한다. FLUX klein은 Qwen3 채팅 템플릿을 사용하고 입력을 최소 512까지 패딩한다.
두 경로 모두 512 초과를 자동으로 자르지 않는다. BFL의 [공식 Qwen3Embedder](https://github.com/black-forest-labs/flux2/blob/main/src/flux2/text_encoder.py)는
템플릿을 포함한 입력을 512로 패딩·절단하므로 현재 core 동작과 다르다.
Moru는 생성·수동 입력에 실제 인코더 토큰 수 검사나 입력 길이 정책을 적용하지 않는다.
로더는 diffusion 계열과 FLUX VAE 구조를 확인하지만 encoder 계열은 별도로 검증하지 않는다.

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
├─ flux2/
│  ├─ diffusion_models/
│  │  └─ flux-2-klein-4b-fp8.safetensors
│  ├─ text_encoders/
│  │  └─ qwen_3_4b_fp4_flux2.safetensors
│  └─ vae/
│     └─ flux2-vae.safetensors
└─ prompt/
   └─ prompt-model.gguf
```

모델 위치는 설정 파일로 override 가능하게 한다.
`ModelPaths.image_payload`는 선택한 정의의 런타임 역할만 해석한다. 파일이 없거나 비어 있으면
준비 실패로 처리한다.
FLUX 전용 encoder/VAE는 `flux2_text_encoder`·`flux2_vae` asset 키로 분리하고 Anima 키는
유지한다. 모델 URL·크기·SHA-256을 고정하고 원본 라이선스와 출처를 `vendor/licenses`에 둔다.
FLUX 문장 이해 모델은 Comfy-Org의 FP4 파일을 기본으로 다운로드한다. 기본 경로에서는
FP4 파일을 먼저 탐색하고 기존 FP16 파일도 허용한다. 명시적으로 선택한 경로가 우선하며
자동으로 덮어쓰거나 기존 파일을 삭제하지 않는다. 양자화 처리는 고정 ComfyUI core가 담당한다.

`bootstrap.image_models`로 표시 이름·계열·버전·필요 asset ID·기본값을 React에 전달한다.
`ImageModelSelect`는 계열/버전 표시만 공유한다. 생성 설정은 App의 Settings를 저장하고,
모델 준비는 `initialModelId`로 초기화한 로컬 `viewedModelId`로 표시할 파일만 바꾼다.
이미지 파일 탐색에는 Settings나 저장 callback을 전달하지 않으며 파일 준비로 `update_settings`를 호출하지 않는다.
프롬프트 작성 방식의 탐색 상태는 별도로 유지한다. GPT 모델 준비는
`configure_prompt_writer` callback으로 반영하고 활성 제공자는 변경하지 않는다.
파일 준비는 기존 path/download bridge로 즉시 반영한다. 탐색 중 다른 asset의 진행/실패
다운로드를 유지한다. 한국어 메뉴와 팝업 이름은 `모델 준비`, 영어는 `Model setup`이다.
App의 시작 검사도 카탈로그의 선택 모델과 prompt asset만 요구한다.
이미지 상세의 모델명은 현재 UI 선택이 아니라 저장된 record ID로 Python에서 결정한다.
`RETIRED_MODELS`에는 기존 SDXL 기록을 읽기 위한 이름·기본값만 유지한다. Repository는
`GenerationSettings(..., allow_retired=True)`로 불변 기록을 복원한다. 일반 설정 생성·저장,
재시도·파일 준비·다운로드·추론에는 해당 ID를 허용하지 않는다. 기존 경로 설정의 SDXL
항목은 읽을 때 제외하며 모델 파일이나 생성 기록은 삭제하지 않는다.

---

## 14. 모델 다운로드

기본 portable 7z는 모델을 제외할 수 있다.

첫 실행 시 필요한 모델이 없으면 앱 UI 안에서 다운로드한다.

기본 흐름은 모델 역할과 준비 상태를 안내한다. 수동 다운로드가 필요한 사용자는
모델 준비의 접힌 안내에서 정확한 원본 파일 이름과 Hugging Face 파일 페이지를 확인한다.
`ModelDownloads.status`가 manifest의 고정 revision URL에서 `/resolve/`를 `/blob/`으로
바꾼 파일 페이지 URL과 원본 파일 이름을 `manual_download`로 제공한다.
React에 모델 URL 목록을 따로 두지 않는다. 다운로드 실패 시 안내를 펼치고,
`target="_blank"` 링크는 pywebview의 기본 외부 브라우저 열기 동작을 사용한다.
받은 파일은 기존 `select_local_model` 흐름으로 연결한다.

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

선택적으로 모델 포함 Full 7z도 만들 수 있다.

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

다시 생성과 수동 수정은 새 Image record와 Request를 만들되 Request.turn_id로 원래 대화 행에 연결한다. turns(id, project_id, selected_image_id)는 행 순서와 선택된 버전을 저장한다. 이미지의 parent_image_id는 실제 생성 기준을 보존하는 lineage이며 대화 표시 순서를 결정하지 않는다.

DB 생성 코드에는 requests.turn_id와 turns를 포함한 최신 스키마만 정의한다.
버전 검사와 마이그레이션은 수행하지 않는다. 지원하지 않는 스키마는 DATABASE_FAILED로 표시한다.
기록을 자동 변환하거나 삭제하지 않는다. 중단된 pending 요청의 실패 복구는 유지한다.

---

## 17. 대화 행과 이미지 버전

Repository.conversation은 세션의 행을 생성 순서대로 반환하며 각 행은 원래 요청, 선택된 이미지, 전체 버전 목록으로 구성된다. UI에는 선택된 버전 하나만 표시한다.

select_version은 그 행의 selected_image_id와 프로젝트의 active_leaf_id를 함께 저장한다. 다른 대화 행이나 이미지 기록은 변경하지 않는다. 다음 자연어 수정의 기준은 active_leaf_id이다.

## 18. 자연어 생성과 세션 분기

기준 이미지가 없으면 create, 있으면 refine을 호출한다. 최근 요청/선택된 프롬프트의 맥락은 현재 기준 행까지만 포함한다. 작업 도중 설정 변경은 해당 작업에 적용하지 않는다.

fork는 선택 행까지 요청과 이미지 record를 새 ID로 복사하고 current_project를 새 세션으로 바꾸는 하나의 SQLite transaction이다. 앞선 행의 이미지 버전과 선택 상태는 보존하며 목표 행에는 선택한 이미지만 복사한다. immutable PNG 파일은 공유한다. 복사 실패는 전체 transaction을 rollback한다.

## 19. 다시 생성과 직접 프롬프트 수정

regenerate는 현재 선택 이미지의 prompt를 generate_from_prompt에 전달한다. 두 경로 모두 LLM을 거치지 않고 현재 이미지 설정을 사용하며 원래 turn_id에 새 버전을 추가한다. Seed Auto는 새 seed를 결정한다. 완료 시 새 버전을 선택한다.

Job.turn_id와 unfinished_requests.turn_id를 bridge로 전달하여 placeholder와 실패/재시도를 원래 행에서 렌더링한다. 새 자연어 요청만 새 행으로 표시한다.

---

## 20. 이미지 뷰어

이미지를 클릭하면 React modal/lightbox로 표시한다.

지원:

- fit
- zoom
- pan
- Esc close
- 상하 방향키로 대화 이미지 탐색, 좌우 방향키로 재생성 버전 선택

뷰어 표시·확대·이동과 대화 행 탐색은 Python backend를 호출하지 않는다.
버전 선택은 대화 화면과 같은 `select_version` API로 저장한다.

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

Turbo 기본값은 Steps 10, CFG 1.0이고 Aesthetic 기본값은 Steps 40, CFG 4.5이다.
Python의 MODEL_DEFAULTS를 bootstrap에서 UI에 전달한다. 모델 전환 시 권장값을 표시하고
저장하며, 명시적으로 입력한 Steps와 CFG는 실제 추론과 이력에 그대로 사용한다.

실제 생성 직전에 seed를 확정하고 DB에 실제 값을 저장한다.

---

## 22. 패키징

### 22.1 목표

일반 사용자는 다음만 수행한다.

```text
7z 다운로드
→ 압축 해제
→ Moru.exe 더블클릭
```

### 22.2 방식

기본 선택:

- PyInstaller `onedir`
- `windowed/noconsole`
- 결과 폴더 전체를 7z로 배포

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
→ ComfyUI/선택 이미지 모델 load
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

ChatGPT 작성에는 요청 ID와 라운드·인증 시도 번호를 붙여 요청, 응답, 도구 결과,
최종 프롬프트 검증을 연결한다. 응답 상태·이벤트 종류별 횟수·출력 항목 구조·텍스트 길이·
토큰 사용량·소요 시간을 기록해 빈 응답과 추론 전용 응답, 도구 호출, 스트림 중단을 구분한다.
완료 응답의 output 개수와 실제 사용할 출력·output_item.done의 구조를 별도로 기록한다. 도구 로그는 이름·결과 수·
오류 코드만 기록하고, API의 문자열 메타데이터는 허용된 값만 남긴다.

로그에는 사용자 요청·프롬프트·도구 검색어와 결과 원문·사고 과정·암호화된 추론 내용·
인증 토큰을 남기지 않는다.

---

## 28. 테스트

### Unit

- 새 작업 생성
- root/child 생성
- 선택한 이미지까지 세션 복사
- root → leaf 경로 계산
- 이미지 버전 선택 및 다음 수정 기준
- Prompt create/refine 입력 구성
- generation settings validation
- Auto seed
- DB repository

### Integration

Mock LLM + Mock Image Worker:

1. 첫 요청 → root image
2. 수정 요청 → child image
3. 과거 이미지 분기 → 독립 세션 복사
4. 직접 프롬프트 생성 → 같은 행의 새 버전
5. 버전 선택 → 다음 수정 기준 변경
6. generation failure → tree 유지
7. restart → state 복구

### Runtime Smoke

실제 GPU 환경:

- Prompt LLM CUDA
- Anima Turbo
- Anima Aesthetic
- FLUX.2 klein 4B
- LLM + 이미지 모델 동시 VRAM
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
- 이미지 버전 선택기
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
- portable 7z
- clean Windows machine smoke test

---

## 30. 구현 원칙

- `SPEC.md`가 사용자 동작의 최종 기준이다.
- Python 개발 환경은 `uv`로만 관리한다.
- 메인 UI는 대화창 하나로 유지한다.
- Prompt LLM은 Agent로 만들지 않는다.
- 자연어 요청을 보내면 항상 이미지까지 생성한다.
- 로컬 Prompt LLM은 GPU를 기본으로 사용하며 ChatGPT 프롬프트 작성은 로컬 추론 자원을 사용하지 않는다.
- ComfyUI는 내부 inference dependency일 뿐 사용자에게 노출하지 않는다.
- ComfyUI UI/노드 편집기를 앱에 포함하지 않는다.
- 내부 worker는 앱이 자동 시작·종료한다.
- 사용자가 서버/스크립트/콘솔을 실행하게 하지 않는다.
- 이미지 결과는 불변이며 재생성은 같은 행의 새 버전, 분기는 독립 세션 복사다.
- release 사용자는 Python/Node/ComfyUI를 설치하지 않는다.
- release는 portable 7z이며 실행 진입점은 `Moru.exe` 하나다.

## 31. 구현 및 고정 런타임

구현은 역할별 패키지로 구성한다. 도메인·유스케이스·공통 인터페이스와 실행 진입점은
루트에 두고, 제공자와 외부 엔진의 구현은 아래 폴더에서 관리한다.

```text
src/moru/
├── chatgpt/      # 인증·자격 증명·HTTP·Responses 작성·스트림·도구 실행
├── danbooru/     # 태그 조회·HTTP 캐시·기한·재시도
├── prompts/      # 로컬 LLM·지침·공통 텍스트·제공자 라우팅
├── images/       # ComfyUI 엔진·워커·IPC 클라이언트·샘플링 일정
├── domain.py
├── ports.py
├── service.py
├── repository.py
├── desktop.py
├── api.py
└── …

frontend/src/
├── features/
│   ├── chatgpt/       # Account·PromptOptions·사용 가능 조건
│   ├── models/        # 모델 준비·이미지 모델 선택
│   ├── settings/      # 생성 설정·공통 및 로컬 프롬프트 옵션
│   └── conversation/  # 대화·진행·이미지·프롬프트·소스 보기
├── components/        # 공통 Modal·CopyButton·PromptText
├── App.tsx
├── api.ts
├── i18n.ts
└── …
```

UI 컴포넌트 테스트는 해당 기능 폴더에 함께 둔다. 패키지 초기화 파일은 엔진이나
통신을 실행하지 않으며, `desktop.py`에서 실제 구현을 조합해 기존 인터페이스로 전달한다.
`cancellation.py`의 공통 취소 검사는 태그 HTTP 계층이 프롬프트 텍스트 처리에 의존하지 않게 한다.

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

프롬프트 LLM의 thinking은 기본적으로 켠다. 사고 과정은 생성용 프롬프트에서 제외하고
완성된 최종 프롬프트만 선택한 이미지 모델에 전달한다. `prompting` 상태는 생성 placeholder에
표시하며, 토큰 제한 때문에 잘린 응답은 오류로 처리한다.
프롬프트 검증·완료 오류는 `PROMPT_EMPTY_RESPONSE`, `PROMPT_INVALID_RESPONSE`,
`PROMPT_NON_ENGLISH_RESPONSE`, `PROMPT_OUTPUT_TOO_LONG`, `PROMPT_RESPONSE_INTERRUPTED`로
구분한다. 원인 코드는 요청에 저장해 bridge와 한국어·영어 오류 번역에 전달한다.
분류되지 않은 추론 예외는 `PROMPT_LLM_FAILED`로 처리한다. 응답 원문과 사고 내용은
오류 메시지나 로그에 추가하지 않는다.
기본 프롬프트 모델은 HauhauCS Qwen3.5-4B Uncensored Aggressive Q4_K_M이다.
기본 context는 4096, 출력 한도는 2048 tokens로 설정한다.
프롬프트 작성 지침은 CUDA 추론 코드와 분리한 `prompts/instructions.py`에서 관리한다.
해석·보강(`ENHANCE`) 규칙과 Anima의 출력·구성·검토 규칙을 함께 전달한다.
FLUX는 같은 해석·보강 규칙에 자연어 문장 작성 지침을 붙인다. 모델 정의의 `natural_prompt`로
생성·수정 지침을 선택하며 FLUX에는 Anima 태그 참고표를 전달하지 않는다.
생성·수정 예시와 정적 `TAG_REFERENCE`는 같은 모듈에 둔다.
제공된 CSV의 빈도와 의미를 검토해 선택한 어휘이며 실행 중 CSV를 읽거나
분류·검색 모델을 추가하지 않는다.
`prompt_messages`는 이 지침을 system으로 전달하고 실제 user/assistant 이력만
대화 턴으로 추가한다. 예시는 이력으로 세지 않으며 현재 상태와 최신 요청을 유지한다.
모델명은 지침에 넣지 않고 모델 정의의 `prompt_suffix`로 Aesthetic의 점수 태그 제외 규칙을 추가한다.
refine은 기존 프롬프트와 변경 요청으로 전체 프롬프트를 작성한다. regenerate와 수동 생성은
LLM을 우회하며 불변 이미지 기록의 설정은 바꾸지 않는다.
규칙의 조사 근거, 태그 선택표와 상세 예시는 [프롬프트 작성 지침](PROMPT_GUIDE.md)에 둔다.
문서 전체를 컨텍스트에 넣지 않는다. 온라인 조회 후보는 [로컬 태그 검색](#74-로컬-태그-검색)의
한도 안에서 참고 어휘로 추가한다.
현재 참고표의 범위와 실제 tokenizer로 측정한 예산은
[태그 지침 적용 기록](reviews/2026-10-05-danbooru-tag-reference.md)에 기록한다.
생성 설정에서 로컬 LLM을 선택하면 접힌 고급 영역에서 두 한도와 thinking 사용 여부, 추론 수준을
변경할 수 있다. 불변 `PromptSettings`는 이미지 설정과 함께 preferences에 원자적으로
저장되며 작업 접수 시 고정한다. 현재 작업에는 저장 후 변경한 값을 적용하지 않는다.
공통 `tag_search_enabled`는 기본 `True`이며 기존 저장값에 필드가 없으면 이 기본값을 사용한다.
생성 설정은 작성 모델 선택과 고급 설정 사이에 검색 체크박스를 두고 닫을 때 함께 저장한다.
Anima 이외의 이미지 모델에서는 선택을 비활성화하며 값은 보존한다.
컨텍스트 또는 모델 경로가 변경되면 다음 LLM 호출에서 모델을 다시 로드한다.
출력 한도, thinking 및 추론 수준 변경은 모델을 재사용한다. GGUF의 chat template에
`enable_thinking`을 명시하여 기존 템플릿의 thinking 분기를 선택한다.
해당 기능이 없는 템플릿에 thinking 끄기를 요청하면 명시적 오류를 반환한다.

LLM 응답은 내부에서 스트리밍으로 소비하며 토큰마다 취소 여부를 확인한다.
취소 시 completion generator를 닫고 이미지 생성으로 넘어가지 않는다.
프로젝트 소유 `PromptProgress` callback은 엔진 경계에서 thinking과 프롬프트를 분리한다.
Application은 사고 내용을 버리고 최종 프롬프트 스트림만 Job에 임시 저장한다.
로컬 모델 적재가 필요하면 VRAM 확보부터 `loading_prompt_model`을 표시한다. 엔진의 `on_ready`
callback은 준비 완료 후 추론 직전에 로컬 LLM은 `prompting`, ChatGPT는 `thinking`으로 전환한다. 적재된 모델을 재사용하면 로딩 단계는 생략하며
적재 실패·취소 시에는 추론 시작을 알리지 않는다. ChatGPT도 같은 준비 완료 계약을 따른다.
polling bridge는 작업 상태·`thinking_enabled`·`prompt_text`로 placeholder를 갱신한다.
사고 내용은 bridge로 전달하지 않는다. 추론 중 thinking이 켜져 있고 최종 프롬프트가 아직 없으면
`생각 중…`, 그 외의 프롬프트 추론은 `프롬프트 생성 중…` 상태로 표시한다.
제어 태그가 토큰 경계에서 나뉘어도 표시하지 않으며, 정상 종료된 전체 응답에서만
이미지 생성용 최종 프롬프트를 추출한다. 임시 텍스트는 DB·로그에 저장하지 않고
성공·실패·취소 후 Job에서도 지운다. 표시용 프롬프트는 최대 65536자로 제한한다.
이미지 생성 중에는 같은 placeholder에 step/전체 steps와 진행률을 표시한다.
Job은 요청에 고정된 width/height를 bridge에 전달한다. 이미지 목록도 이미지별
저장된 width/height를 포함해 원본 로딩 중의 공간을 확보한다. UI의 imageFrameStyle은
생성 중·로딩 중·완료 이미지에 동일한 비율과 표시 상한(너비 550px, 높이 520px)을 적용한다.
컨테이너 너비에 맞춰 축소하며 원본 크기보다 확대하지 않는다.

미완료 요청 목록도 요청에 저장된 width/height를 bridge에 전달한다.
Conversation의 RequestFailure는 같은 imageFrameStyle로 실패·중지 placeholder를 만든다.
내부 콘텐츠를 절대 배치해 프레임 비율을 유지하고, 짧은 오류와 재시도 버튼은 중앙 정렬하며
공간이 부족하면 프레임 안에서 스크롤한다. 실패는 붉은 톤, 사용자 중지는 중립색으로 구분한다.
기존 이미지 버전이 있으면 이미지와 실패 placeholder를 원래 행 안에 함께 표시한다.
재시도가 접수된 요청은 아직 목록에 이전 오류가 남아도 Job의 request_id로 오류 표시를 숨긴다.
작업 종료 오류는 저장된 요청에서 표시하며 App의 하단 오류 배너에 중복 추가하지 않는다.
bridge 호출·설정·클립보드 등 요청 외 오류는 기존 배너나 해당 팝업에서 표시한다.

추론 수준의 기본값은 medium이다. 최종 프롬프트용 512토큰과 여유 128토큰을 예약하고
`max(0, max_tokens - 640)`의 50%/75%/100%를 low/medium/high 예산으로 사용한다.
기본 출력 한도에서 예산은 각각 704/1056/1408토큰이다.
소수점은 버린다. Thinking을 끄면 예산은 0이며 해당 processor도 사용하지 않는다.
512는 최종 프롬프트 예약 정책의 기준값이다. 현재 ComfyUI Anima tokenizer는
512에서 입력을 자르지 않고 adapter는 짧은 입력만 512까지 padding한다.
LLM과 이미지 엔진의 tokenizer도 다르므로 이 예산을 Anima의 최대 입력 길이로 해석하지 않는다.
이는 모델의 네이티브 reasoning_effort 옵션이 아니라 앱이 적용하는 토큰 예산이다.
종료 태그와 최종 답변 구분자도 예산에 포함한다. 예산보다 제어 토큰이 많으면
자유 추론 없이 즉시 제어 토큰부터 생성하며 이때도 전체 출력 한도는 유지한다.
완료용 logits processor가 예산에 도달하면 </think>와 최종 답변 구분자를 생성하게 하여
중단된 사고 문장을 계속 쓰지 않고 최종 프롬프트 작성을 이어 간다. 구분자는 반환/표시 전에 제거한다.
모델이 먼저 thinking을 마치면 개입하지 않으며 thinking을 끄면 processor를 사용하지 않는다.
사용자가 저장한 설정의 자동 전환 코드는 두지 않는다.
프롬프트 샘플링은 thinking 시 temperature 0.6/top_p 0.95, 비활성 시 0.7/0.8을
사용한다. 품질 태그의 반복을 줄이기 위해 repeat_penalty 1.1을 적용한다.
LLM의 최종 답변 형식은 한 문단의 영어 프롬프트다. thinking 및 제어 구분자가 끝나고
실제 답변이 시작된 뒤 문단 경계에서 EOS를 생성하여 분석을 다시 시작하지 않도록 한다.
같은 토큰에 문단 경계와 후속 분석이 포함되어도 첫 문단만 표시하고 이미지 엔진에 전달한다.
수동 프롬프트 입력은 이 LLM 응답 형식 제한을 거치지 않는다.

추론 설정 근거: [이미지 모델 권장값](https://huggingface.co/circlestone-labs/Anima),
[프롬프트 LLM 샘플링 권장값](https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive).

아이콘은 `lucide-react`의 개별 component import를 사용한다. 전송/중지는 하나의 버튼이며,
이미지 뷰어는 Modal의 한 줄 toolbar에 맞춤·확대/축소·닫기를 함께 배치한다.
모델 상태 bridge는 선택된 파일 이름만 전달하여 전체 경로를 UI에 노출하지 않는다.

HTML을 직접 로드한 WebView2에서는 브라우저 Clipboard API를 사용할 수 없으므로
프롬프트 복사는 Python bridge로 전달하여 Windows UI thread의 클립보드 API를 사용한다.
이미지 복사는 이미지 ID로 PNG를 조회하고 동일한 경로 검증을 거친 뒤 STA UI thread에서
Bitmap과 PNG 클립보드 형식으로 저장한다. 클립보드 저장 실패는 CLIPBOARD_FAILED로 표시한다.
두 복사 버튼은 CopyButton의 고정 크기 아이콘을 완료 시 체크로 전환하며 reduced-motion을 존중한다.

이미지 hover는 해당 ID의 상세 정보를 필요할 때만 읽고 이미지가 바뀌면 다시 읽는다.
반투명 blur 커버는 생성 placeholder와 같은 stream-label/텍스트 스타일을 사용한다.
공통 PromptText는 짧은 텍스트를 세로 중앙에 놓고, 긴 텍스트는 이미지 안에서만
스크롤한다. 생성 canvas는 비율이 고정된 frame 안에 절대 배치해 내용으로 늘어나지 않는다.
추론·프롬프트 작성 상태와 이미지 생성 진행률도 이 frame 안에 표시한다.
스트리밍 텍스트는 맨 아래를 따르던 경우에만 자동 스크롤한다.
팝업을 열면 hover 표시를 초기화하고, 프로그램에 의한 초점 복원과 팝업 제거 때의
마우스 진입 이벤트를 새 hover로 취급하지 않는다. 실제 마우스 이동이나 Tab 탐색으로 해제한다.
분기 성공 알림은 새 세션 반환 이후 표시하고 자동으로 닫으며 기존 레이아웃을 움직이지 않는다.

App의 이미지 탐색 커서는 대화 행 ID다. 뷰어는 그 행에서 선택된 이미지의 source를 사용한다.
상하 탐색은 화면 커서만 이동하고 좌우 탐색은 기존 select_version을 사용하여 선택을 저장한다.
한 문서 키보드 이벤트에서 대화/뷰어 탐색을 처리하며 편집 중 입력, 다른 팝업, IME와 수정 키를 제외한다.
중복된 버전 변경 요청을 막고 뷰어의 source/이미지 ID가 바뀌면 zoom/pan을 초기화한다.
App은 모든 팝업에 대해 공통 modalOpen 상태를 계산해 헤더·대화·입력 영역을 inert로
설정한다. 대화는 overflow를 잠그고 자동 스크롤과 선택 행 scrollIntoView를 중단한다.
팝업을 닫으면 잠금을 해제하고 선택한 이미지로 초점을 돌린다.
공통 Modal의 초점 복원은 preventScroll을 사용해 읽던 위치를 유지한다.
선택 행으로의 이동은 실제 선택이 달라진 경우에만 수행한다.
팝업과 프롬프트 내부 scroll container는 overscroll-behavior로 스크롤 체인을 막는다.
뷰어는 passive가 아닌 native wheel listener에서 기본 스크롤과 이벤트 전파를 막고
확대·축소를 처리한다. 드래그에는 touch-action: none을 적용한다.
Lightbox는 배율과 이동량을 하나의 상태로 갱신한다. 휠은 뷰어 중앙에서 커서까지의
좌표를, 도구 모음은 뷰어 중앙을 기준으로 이미지 지점을 고정한다.
새 이동량은 `anchor + (position - anchor) * (newZoom / oldZoom)`으로 계산하며
배율 한도를 적용한 실제 비율을 사용한다. 드래그는 직전 포인터 위치의 차이만
더하므로 드래그 중 확대해도 보정한 위치를 이전 시작 위치로 되돌리지 않는다.
Modal의 선택적인 초점 복귀 callback으로 뷰어 종료 후 탐색한 이미지에 초점을 돌린다.

헤더 로고는 이미지 없이 `moru` 텍스트만 표시한다. line-height: 1과 위쪽 2px 보정으로
소문자 글리프의 시각적 세로 중앙을 맞추고, 언어 선택 메뉴와 20px 간격을 둔다.
작업 기록 선택 메뉴의 너비는 .header-actions select에만 적용해 언어 선택 메뉴는 내용에 맞춘다.
빈 대화 화면 이미지의 원본은 docs/ICON.png다. Vite에서 인라인하여 서버 없이 표시한다.
같은 원본에서 만든 src/moru/assets/icon.ico를 pywebview 창 아이콘과 PyInstaller --icon에 사용한다.
아이콘 원본을 교체할 때는 ICO의 16/24/32/48/64/128/256 크기도 함께 갱신한다.

수정·검증 이력은 docs/reviews/YYYY-MM-DD-description.md에 보관한다.
현재 요구사항과 기술 설계는 docs/SPEC.md와 docs/TECH.md로 유지하고 이력 문서와 구분한다.

앱은 viewport 높이에 고정하고 대화 flex 영역에 `min-height: 0`을 적용한다.
하단 입력 영역은 대화 위에 겹쳐 배치하며 도구 영역의 배경은 투명하게 둔다. ResizeObserver로 입력 영역 높이를
측정해 대화 하단 여백을 확보한다. 버튼 사이의 빈 공간은 대화의 클릭·스크롤을 가로막지 않는다.
body의 overflow는 숨겨 페이지 전체 스크롤을 막고, 긴 대화는 대화 영역 안에서 스크롤한다.
복사 버튼의 접근성용 숨김 문구는 버튼을 containing block으로 삼도록 배치해
대화 밖의 페이지 scroll height를 늘리지 않게 한다.
자연어 요청을 전송하면 bridge 응답을 기다리지 않고 즉시 맨 아래로 이동해 최신 대화 따라가기를 활성화한다.
그 외 대화 업데이트는 맨 아래를 따라가는 상태에서만 자동 이동한다. ResizeObserver로 이미지와 텍스트의 크기 변화를
추적하며, 위로 스크롤하면 입력창 중앙 상단의 플로팅 버튼으로 맨 아래로 이동한다. 실시간 프롬프트는
placeholder의 이미지 canvas 안에 표시하며 사고 내용은 표시하지 않는다.


## ChatGPT 프롬프트 제공자

`PromptSettings.provider`와 `chatgpt_model`을 preferences에 저장하고 작업 접수 시 기존
불변 설정과 함께 고정한다. 기존 설정은 `local` 기본값으로 읽는다. `PromptProviders`는
기존 `PromptGenerator` 계약으로 `LlamaPrompts` 또는 `ChatGPTPrompts`에 위임한다.
ChatGPT 선택 시 로컬 LLM을 unload하고 memory_required는 0이다. Application은 이 경우
이미지 worker의 reserve_memory를 호출하지 않는다. 이미지 생성·Fork·수동 생성 경계는 유지한다.

`chatgpt/instructions.py`의 `prompt_messages`는 짧은 모델별 지침과 기존 실제 대화·기준 프롬프트 구성을 사용한다.
두 엔진의 이력 구성과 출력 검증은 `prompts/text.py`에서 공유한다. ChatGPT 구현은 로컬
추론 모듈에 의존하지 않으며 각 엔진의 지침과 추론·스트림 처리는 해당 구현에 둔다.
`ChatGPTHttp`는 표준 라이브러리 HTTPS/SSE로 `POST https://api.openai.com/v1/responses`에
instructions·전체 input·선택 모델·store:false·stream:true를 보낸다. 로컬 추론 옵션은 전달하지 않는다.
`chatgpt_reasoning_effort` 기본값은 `default`이며 선택한 경우에만 `reasoning.effort`를 보낸다.
`chatgpt/options.py`는 공식 문서로 확인한 모델과 날짜별 snapshot의 추론 수준을 제공하고,
알 수 없는 계정 모델 별칭은 기본값만 허용한다. bridge의 `get_chatgpt_reasoning_efforts`는
네트워크 없이 같은 기준을 UI에 전달하며 실제 계정 정책에 따른 API 거절도 오류로 표시한다.

`chatgpt/stream.py`는 SSE의 답변과 완료 output을 읽고 거절·실패·불완전·중단을 구분한다.
완료 이벤트의 output이 빈 배열이면 앞서 받은 `response.output_item.done` 항목을 보존한다.
도구 호출·암호화된 추론·최종 답변을 잃지 않으며, 잘못된 타입의 output은 기존처럼 거부한다.
완료 항목의 의미는 [OpenAI 공식 SSE 문서](https://developers.openai.com/api/reference/resources/responses/streaming-events)를 따른다.
선택적 `on_stage(stage, found_tag_count)` 콜백을 제공자 라우터에서 전달하고 Application이
작업 상태와 개수를 함께 반영한다. ChatGPT 작성 중 실제 조회 결과의 태그 이름을 set으로
누적하며 검색 후보·정식 태그·관련 태그 사이의 중복을 제거한다. 검색어와 wiki 본문의 태그는
추측해 세지 않는다. 개수는 Job의 `found_tag_count`로 polling하며 매 작업 0에서 시작한다.
검색 상태에서만 기존 문구에 개수를 표시한다.
도구 호출 항목이 시작되거나 실제 조회를 실행할 때 `searching_tags`를 알리며 후속 요청에서도 유지한다.
최종 답변 메시지 또는 텍스트 출력이 시작되면 `prompting`으로 전환한다. 중간 설명인
`phase:commentary`는 최종 작성 시작으로 취급하지 않고 후속 input에 원래 phase를 보존한다.
phase가 없는 응답은 메시지·텍스트 출력 시점을 사용한다. 이 구분은
[OpenAI 공식 추론 문서](https://developers.openai.com/api/docs/guides/reasoning#phase-parameter)를 따른다.
도구 호출이 가능한 응답은 텍스트를 모아 두고, 호출 없이 완료된 최종 프롬프트만 표시한다.
도구를 제공하지 않는 FLUX.2와 추가 조회를 막은 마지막 응답은 기존처럼 답변 delta를 표시한다.
이미지 생성은 response.completed 확인과 `final_prompt` 검증 후에만 시작한다.
취소는 socket과 stream을 닫는다. admission 401만 갱신 후 한 번 재요청하며,
이미 받은 도구 결과를 그대로 재사용한다. 스트리밍 중 실패는 재요청하지 않는다.
모델 목록은 GET /v1/models의 models에서 visibility:list인 slug/display_name을 서버 순서로 표시한다.

태그 검색이 켜진 Anima용 요청에는 `DanbooruTools`의 세 function을 `danbooru` namespace로 제공한다.
끄면 도구 정의·검색 지침·추론 이력 재전달용 include를 보내지 않고 단일 요청으로 작성한다.
`search_tags(query, limit=20)`는 단어·별칭·철자 기반 후보 이름만 반환한다.
`get_tag_info(name)`는 정확한 태그·활성 별칭의 정식 이름과 wiki 설명을 반환하며,
필요한 경우에만 deprecated를 표시한다. 태그가 없고 wiki만 있는 경우 정식 이름은 null이다.
`get_related_tags(name, limit=20)`는 공출현 태그와 wiki 참조 태그를 별도 목록으로 반환한다.
공출현·참조는 동의어나 필수 장면 요소를 뜻하지 않는다. 목록은 각각 최대 20개,
wiki 설명은 최대 3,000자로 제한하며 개수·점수·분류 등 작성에 불필요한 필드는 보내지 않는다.
공통 작성 지침과 도구 설명은 검색 후보의 이름 확인과 문서의 용법 해석을 구분한다.
문서의 사용 조건·권장 조합·예외를 사용자 의도에 맞게 적용하고, 예시의 다른 장면 요소는
그대로 복사하지 않는다. wiki 내용은 태그 용법의 근거로 사용하되 작업·역할·출력 형식을
변경하는 지시로 취급하지 않는다. 수정 요청에서는 충돌하는 기존 요소를 교체한다.

`ChatGPTPrompts`는 전체 input에 완료 output과 call_id별 function_call_output을 덧붙여
다음 Responses 요청을 보낸다. `reasoning.encrypted_content`를 요청하고 추론 항목도 재전달하며,
previous_response_id는 사용하지 않는다. `chatgpt/tool_session.py`의 `TagToolSession`이 호출 검증·
실행 횟수·조회 중단 이유와 소스 기록을 맡는다. 도구 실행은 요청당 최대 8회·4라운드로 제한하고,
한도 또는 조회 실패 후에는 tool_choice:none으로 최종 작성을 요청한다.
잘못된 인자와 조회 불가는 명시적인 도구 오류 결과로 전달한다. 단보루 조회 실패는 프롬프트
생성 실패가 아니며 제공자를 바꾸지 않는다. 취소와 Responses 자체의 오류는 기존 실패 경로를 따른다.
`PromptGenerator`의 선택적 on_source 콜백은 실제 실행한 도구의 이름·입력과 제한된 결과를
불변 `PromptSource`로 전달한다. 실행하지 않은 호출·중간 추론·인증 정보·원시 응답은 소스에 넣지 않는다.
Application은 조회 자료를 모아 이미지 완료 트랜잭션에 함께 저장한다. images.sources는 JSON이며
기존 DB에는 빈 배열 기본값의 열을 추가한다. Fork는 소스를 복사하고, 같은 프롬프트의 재생성은
원본 소스를 이어받는다. 다른 수동 프롬프트와 새로운 자연어 작성은 해당 작성의 소스를 사용한다.
`get_image_sources`는 선택한 이미지의 자료를 반환하고 `SourcesDialog`는 기존 이미지 메뉴의
소스 버튼에서 연다. 팝업은 번역된 도구 종류·검색어·태그·설명과 조회 실패를 표시하며 원시 JSON은
노출하지 않는다. wiki 설명과 관련 태그의 두 목록은 기본적으로 닫힌 `details`로 표시한다.
관련 목록의 summary에는 태그 수를 표시하고 빈 목록은 생략한다. wiki 설명은 텍스트로 렌더링하며
HTML로 실행하지 않는다. 태그 링크는 고정 wiki URL로 만든다.
기존 Modal의 닫기·초점 복원·배경 잠금을 공유하며 소스가 없는 이미지도 같은 메뉴를 유지한다.

`DanbooruTags`는 autocomplete·활성 alias·tag/wiki·related_tag 응답에서 필요한 정보만 추출한다.
`DanbooruHttp`는 고정된 safebooru.donmai.us에 식별 가능한 User-Agent로 익명 GET을 보내며
ChatGPT 인증 정보를 전달하지 않는다. 표준 라이브러리만 사용하고 요청 사이 최소 1초 간격,
5분 TTL의 최대 128개 메모리 캐시를 둔다. 호출별 타임아웃은 10초이며 socket을 중단해
취소·전체 호출 기한을 반영한다. HTTP 429만 1초 대기 후 한 번 재시도한다.
재시도 실패·통신 오류·잘못된 응답은 `TagLookupError`로 전달하고 도구 경계에서 조회 불가로 변환한다.
API 계약은 [Danbooru API 안내](https://safebooru.donmai.us/wiki_pages/help:api)와
[공식 자동완성 구현](https://github.com/danbooru/danbooru/blob/master/app/logical/autocomplete_service.rb),
[관련 태그 구현](https://github.com/danbooru/danbooru/blob/master/app/logical/related_tag_query.rb)을 따른다.

`ChatGPTAuth`는 최초 dynamic_agent_client·영구 host UUID·PKCE S256·state·nonce를 사용한다.
발급 client ID로 코드를 교환하고 OIDC discovery/JWKS와 PyJWT[crypto]로 RS256 서명·issuer·
audience·만료·nonce를 검증한다. 이 의존성은 표준 라이브러리에 없는 JWT 서명 검증을 위해 추가한다.
기본 브라우저를 열기 전에 임의 포트의 127.0.0.1 HTTPServer를 시작하고 콜백·취소·5분 만료 시 닫는다.
계정은 client ID와 검증된 subject로 구분하고 재로그인 시 기존 매핑을 유지한다.
구독 scope가 없으면 로그인은 보관하되 추론을 허용하지 않는다.

`CredentialStore`는 `%LOCALAPPDATA%/Moru/chatgpt.dpapi`에 host·등록·토큰·만료를 사용자
범위 DPAPI로 암호화해 원자적으로 저장한다. UI에는 토큰·host·subject를 전달하지 않으며
callback URL을 기록하지 않는다. 사용자 저장소의 OS 파일 잠금과 RLock으로 refresh를 직렬화하고
갱신 전 최신 저장값을 읽는다. 성공 시 access·refresh·scope·만료를 함께 교체한다.
일시적 실패는 토큰을 보존하고 terminal refresh 실패만 토큰을 지운다. 로그아웃은 discovery의
revocation endpoint 호출 후 토큰을 지우되 계정 매핑과 host는 유지한다. 원격 해제 실패는 UI에 전달한다.

bridge는 로그인·상태·취소·연결 해제·계정 선택·모델 목록·제공자 선택을 제공한다.
ModelsDialog는 준비할 방식과 GPT 모델 선택을 유지하며 선택한 방식의 파일 준비 또는 `features/chatgpt/Account`만 표시한다.
모델 준비와 생성 설정은 모두 이미지 영역을 먼저 표시하고 구분선 뒤에 프롬프트 영역을 둔다.
고급 설정은 프롬프트 영역 안에 두며 별도 구분선을 사용하지 않는다.
`configure_prompt_writer`는 provider 변경을 거부하고 준비 상태를 요구하지 않은 채 옵션만 저장한다.
idle 잠금 안에서 최신 설정을 읽어 저장하여 동시 제공자 선택을 덮어쓰지 않는다.
GPT 모델 선택은 즉시 저장하며 실패 시 이전 선택을 유지한다. 숨겨진 로컬 모델의 진행/실패 다운로드도
다른 모델의 다운로드 영역에 표시하여 취소할 수 있게 한다.
첫 로그인 안내 중에는 ModelsDialog의 렌더링을 일시 중단하고 준비 선택을 유지하여, 안내를 닫으면
선택했던 ChatGPT 설정으로 돌아온다. 두 모달의 focus trap을 동시에 활성화하지 않는다.
SettingsDialog는 준비된 제공자 선택과 이미지 생성 옵션을 표시하고, 접힌 고급 설정에 PromptOptions를 둔다.
최근 요청 수는 공통으로 표시하고 ChatGPT 선택 시 `features/chatgpt/PromptOptions`의 추론 수준을 표시한다.
로컬 전용 추론 옵션은 숨기며 두 제공자의 값을 따로 보관한다. 제공자를 바꿔도
draft를 유지하며 모든 닫기 경로에서 변경된 이미지·프롬프트 설정을 `update_settings`에 전달한다.
저장 성공 후에만 닫으며 변경이 없으면 bridge 호출을 생략한다. 폼 검증은 닫기 시점에 수행하고
숨겨진 고급 필드가 잘못되면 해당 영역을 펼친다. 저장 중에는 fieldset을 비활성화하며 ref로 중복 호출을 막는다.
검증·저장 실패 시 draft와 팝업을 유지한다. 저장 버튼과 계정·파일 준비 기능은 제공하지 않는다.
입력 영역에는 고정 폭의 제공자 선택만 두고 조건부 안내 문단은 넣지 않는다. `features/chatgpt/Account`는
상태별 로그인·재로그인·권한 허용을 구분하고 연결 완료 시 계정 추가·로그아웃만 표시한다.
카드 상단은 계정 라벨과 사용량 링크를 한 행에 두며 제공자 제목은 반복하지 않는다.
로컬 파일 영역도 선택된 제공자 이름을 중복 표시하지 않고 두 모델 준비 영역 사이에 구분선을 둔다.
모델 선택과 새로고침 아이콘은 한 행에 배치한다. 전송·정책 설명은 접힌 이용 안내에 둔다.
환영 모달은 구독·전송 안내를 제공하며 확인은 계정별로 저장한다. 인증·거절·사용량·통신 오류는 안정적인 코드로 번역하며
자동 제공자 전환은 없다. 실제 로그인·구독 추론 검증은 수동 통합 검증으로 분리한다.
프로토콜은 [SIWC 공식 문서](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)와
[Responses 제한](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)을 따른다.

## 개발 및 검증

Python 3.12, uv와 Node.js가 필요하다. 실제 추론과 Windows 배포 빌드에는 inference extra를 설치한다.

```powershell
uv sync --frozen --extra inference
uv run --extra inference python scripts/setup_comfyui.py
cd frontend
npm ci
npm run build
cd ..
uv run --extra inference python -m moru
```

일반 테스트는 GPU와 모델을 로드하지 않는다.

```powershell
uv run pytest
uv run ruff check src tests scripts app.py
cd frontend
npm run test
npm run check
npm run build
```

실제 모델/GPU 검증과 portable 빌드는 프로젝트 루트에서 별도로 실행한다.
`smoke_tag_queries.py`는 검색어 추론만 실행하며 HTTP 조회·최종 프롬프트·이미지 생성은 생략한다.

```powershell
uv run --extra inference python scripts/smoke_tag_queries.py
uv run --extra inference python scripts/smoke_runtime.py --prompt --reasoning-level low
uv run --extra inference python scripts/smoke_runtime.py --image aesthetic --width 1024 --height 1024
uv run --extra inference python scripts/smoke_runtime.py --prompt --image flux --width 1024 --height 1024
uv run --extra inference python scripts/build_portable.py
uv run --extra inference python scripts/smoke_portable.py <빌드된-Moru-폴더> --ui-only
```

배포 파일은 `release/Moru.7z`이며 모델과 사용자 데이터는 포함하지 않는다.
압축에는 Windows용 7-Zip을 사용한다. PATH의 `7z` 또는 `%ProgramFiles%/7-Zip/7z.exe`를 찾는다.
빌드 전에 설치하려면 `winget install --id 7zip.7zip --exact --source winget`을 실행한다.
임시 압축 파일의 무결성 검사에 성공한 뒤 기존 배포 파일을 교체한다.
`--skip-archive`는 폴더만 빌드하며, `--archive-only --reuse-staging <빌드-폴더>`는
기존 `dist/Moru`를 다시 압축한다.

### 표시 언어

React UI는 i18next와 react-i18next를 사용한다. 한국어/영어 텍스트는
`frontend/src/locales/{ko,en}/`의 JSON 리소스로 분리하고 정적 빌드에 모두 포함한다.
언어 선택에 네트워크 요청이나 런타임 번역 API를 사용하지 않는다.
`useTranslation` 구독으로 UI와 접근성 이름을 갱신하며 날짜는 선택한 locale로 포맷한다.
Python `get_language` bridge로 저장 언어를 먼저 읽고 나서 전체 bootstrap을 실행한다.
모델 상태 등의 초기화 실패가 언어 복원을 막지 않도록 분리한다. `set_language` bridge는
생성 설정과 별도로 표시 언어를 저장한다. 저장 성공 후 UI 언어를 전환하고 문서의 `lang` 속성도 갱신한다.
새 설치의 저장 기본값은 한국어이며, 지원하지 않는 저장값/누락된 번역은 영어를 사용한다.
저장 언어를 아직 읽지 못한 UI와 네이티브 시작 오류에서 설정 읽기 실패 시에도 영어를 사용한다.
오류는 안정적인 error code를 번역하며 사용자 입력, 프롬프트와 파일 이름은 변경하지 않는다.
