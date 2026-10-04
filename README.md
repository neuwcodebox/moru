# Moru

자연어로 이미지를 생성하고 대화로 수정하는 Windows용 로컬 데스크톱 앱입니다.
React 화면, pywebview JS bridge, 로컬 CUDA LLM, 숨겨진 ComfyUI core worker를 사용합니다.
사용자 요청과 이미지는 외부 API로 보내지 않습니다.

생성 기본값은 Anima Turbo, 1024 × 1024, **Steps 10, CFG 1.0, Seed Auto**입니다.
수정은 기존 결과를 보존하는 Fork이며, 작업·요청·이미지·분기는 SQLite에 저장됩니다.

## 개발 환경

Python 3.12와 `uv`, 프론트엔드 빌드용 Node.js가 필요합니다.
추론 의존성은 크기가 커서 `inference` extra로 분리했습니다. 일반 테스트는 모델과 GPU를
로드하지 않습니다. 실제 앱 실행과 배포 빌드에서는 이 extra를 설치하세요.

```powershell
uv sync --frozen --extra inference
uv run --extra inference python scripts/setup_comfyui.py
cd frontend
npm ci
npm run build
cd ..
uv run --extra inference python -m moru
```

`uv run --extra inference python -m app`도 같은 앱을 실행합니다.
개발 서버가 필요하면 `frontend`에서 `npm run dev`를 사용합니다. Python bridge는
데스크톱 창에서 제공되므로 브라우저 개발 서버에서는 실제 생성이 연결되지 않습니다.

## 모델

앱의 **모델 준비** 팝업에서 모델을 다운로드하거나 로컬 파일을 선택합니다.
다운로드는 고정된 버전의 파일을 SHA-256과 크기로 검증합니다. 모델이 준비된 후에는
오프라인으로 사용할 수 있습니다. 앱 폴더 아래의 모델 경로는 상대 경로로 저장합니다.

기본 경로는 `models/prompt/`와 `models/anima/`이며, 기존
`anima_turboV11.safetensors`, `qwen_3_600m.safetensors`,
`qwen_image_vae.safetensors`, `Qwen3.5-4B-Q4_K_M.gguf`도 자동으로 찾습니다.
기본 프롬프트 LLM은 `Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf`이며
기본적으로 thinking을 유지합니다. 생성 설정의 **고급 · 프롬프트 LLM**에서
컨텍스트 크기(기본 8192), 출력 토큰 한도(기본 4096), thinking 사용 여부를 바꿀 수 있습니다.
변경은 다음 생성부터 적용되고 재시작 후에도 유지됩니다.
작성 중에는 대화창에 **생각 중…**을 표시하고,
완성된 최종 프롬프트만 이미지 생성에 사용합니다.
설정은 `data/model-paths.json`, 작업 기록은 `data/anima.db`, 생성 이미지는
`data/images/`, 로그는 `data/logs/`에 저장됩니다.
모델의 사용 조건은 각 배포자의 라이선스를 따릅니다. 배포 ZIP의 `licenses` 폴더에
의존성 라이선스와 모델 출처를 포함합니다.

## Windows portable 빌드

개발 환경과 모델을 준비한 Windows에서 다음 명령을 실행합니다.

```powershell
uv run --extra inference python scripts/build_portable.py
```

빌드 결과는 `release/Moru.zip`입니다. 모델은 포함하지 않습니다. 압축을 풀고
`Moru.exe`를 실행하면 Python이나 Node.js를 별도로 설치할 필요가 없습니다.
NVIDIA GPU 드라이버와 Windows WebView2 Runtime은 필요합니다.

## 검증

```powershell
uv run pytest
uv run ruff check src tests scripts app.py
cd frontend
npm run test
npm run build
```

실제 NVIDIA GPU와 모델을 쓰는 추가 검증:

```powershell
uv run --extra inference python scripts/smoke_runtime.py --prompt --image turbo --steps 10
uv run --extra inference python scripts/smoke_runtime.py --image aesthetic --width 1024 --height 1024 --steps 10
uv run --extra inference python scripts/smoke_desktop.py
uv run --extra inference python scripts/smoke_application.py
uv run --extra inference python scripts/smoke_runtime.py --image turbo --cancel-restart
```

패키지 실행 검증은 `scripts/smoke_portable.py <빌드된 Moru 폴더>`로 실행합니다.
별도 임시 작업 폴더를 만들고 개발용 Python·Node·CUDA Toolkit을 PATH에서 제외한
실행 파일로 실제 CUDA 프롬프트 작성과 이미지 생성을 확인합니다.
`--ui-only` 옵션은 모델 추론 없이 화면, bridge, 실제 Windows 클립보드 복사를
확인합니다. 검증 중 임시로 사용한 클립보드는 원래 내용으로 복원합니다.

요구사항과 기술 설계의 원본은 [SPEC.md](docs/SPEC.md), [TECH.md](docs/TECH.md)입니다.
