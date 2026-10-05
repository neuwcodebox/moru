# Moru

[English](README.md)

**말로 그리고, 비교하고, 분기하세요. 모두 로컬에서.**

Moru는 대화로 이미지를 만드는 Windows 데스크톱 앱입니다. 원하는 장면을 설명하고,
결과를 본 뒤 무엇을 바꿀지 말하세요. 로컬 LLM이 이미지 프롬프트를 작성하고,
Anima가 내 컴퓨터에서 이미지를 생성합니다.

작업은 하나의 대화로 쌓입니다. 같은 요청을 다시 시도하고, 마음에 드는 버전을 고르고,
과거 이미지로 돌아가 다른 방향으로 이어갈 수 있습니다.

![Moru에서 자연어로 이미지를 생성하고 수정하는 화면](docs/demo-ko.webp)

## 이미지가 답이 되는 대화

처음에는 원하는 장면을 평소 쓰는 말로 설명하세요.

> 금발 여성이 편의점에서 라면을 먹는 장면.

결과를 보면서 다음 요청을 이어갑니다.

> 비가 내리는 저녁으로 바꿔줘.
>
> 표정은 무표정하게 해줘.

Moru는 현재 이미지의 실제 프롬프트와 최근 요청을 참고해 다음 프롬프트를 작성하고
새 이미지를 생성합니다. 간단한 아이디어도 지정한 내용을 지키면서 어울리는 조명,
분위기, 질감을 보강합니다. 프롬프트가 작성되는 모습과 이미지 생성 진행률은
대화 안에서 확인할 수 있습니다.

## 여러 결과를 비교하고, 다른 방향으로 분기하기

**다시**는 같은 프롬프트와 현재 생성 설정으로 새 이미지 버전을 생성합니다.
결과는 같은 대화 행의 이미지 버전으로 묶입니다. 버전을 넘겨 보며 원하는 결과를
선택하고, 그 버전을 기준으로 다음 대화를 이어가세요.

**분기**는 선택한 이미지까지의 대화를 복사해 별도 작업을 시작합니다.
한쪽에서는 수채화로, 다른 쪽에서는 밤 풍경으로 이어갈 수 있습니다.
원래 작업은 남아 있고, 각 분기의 이후 작업은 따로 저장됩니다.

성공한 이미지와 프롬프트, 생성 설정, 선택한 버전은 로컬에 저장됩니다.
나중에 작업을 다시 열어 이어서 만들 수 있습니다.

## 프롬프트는 자동으로, 세부 조정은 직접

- **실제 프롬프트 편집:** 이미지에 사용된 프롬프트를 확인·복사하거나 직접 고쳐
  새 버전을 생성할 수 있습니다.
- **생성 방식 선택:** 빠른 반복에는 Anima Turbo, 더 많은 샘플링 단계를 사용하는
  생성에는 Anima Aesthetic을 선택합니다. 이미지 크기, Steps, CFG, Seed도 조절할 수 있습니다.
- **프롬프트 LLM 조절:** Thinking, 추론 수준, 컨텍스트·출력 한도와 최근 대화 참고 범위를
  조절할 수 있습니다.
- **결과 확인과 공유:** 전체 화면 뷰어에서 확대·이동하며 이미지와 버전을 탐색하고,
  이미지 자체를 클립보드에 복사할 수 있습니다.
- **한국어·영어 UI:** 작업을 유지하면서 인터페이스 언어를 바꿀 수 있습니다.

## 프롬프트부터 이미지까지 로컬에서

프롬프트 작성과 이미지 생성 모두 로컬에서 실행합니다. 외부 API 키가 필요하지 않으며,
요청·프롬프트·이미지를 외부 추론 서비스로 보내지 않습니다.
모델을 준비한 뒤에는 오프라인으로 이미지를 만들고 수정할 수 있습니다.

작업·이미지·설정은 앱의 `data/` 폴더에, 다운로드한 모델은 `models/`에 보관합니다.
앱을 옮길 때 이 폴더도 함께 옮기면 작업 기록과 모델을 유지할 수 있습니다.

## 시작하기

Windows, NVIDIA GPU와 드라이버, Windows WebView2 Runtime이 필요합니다.

### 포터블 ZIP

[Moru.zip 다운로드 (Google Drive)](https://drive.google.com/file/d/1Y_aYECQ6VqFdV51_GoDl_Uy2-r51NWwW/view?usp=sharing)

1. `Moru.zip` 전체를 압축 해제하고 `Moru.exe`를 실행합니다.
2. **모델 설정**에서 필요한 모델을 다운로드하거나 이미 가진 로컬 파일을 선택합니다.
3. 입력창에 원하는 장면을 적어 전송하고, 이미지가 나오면 수정 요청을 이어갑니다.

포터블 배포본에는 앱 실행에 필요한 런타임이 포함되므로 Python, Node.js, ComfyUI를
별도로 설치할 필요가 없습니다. 모델은 따로 준비하며 각 배포자의 라이선스를 따릅니다.
모델을 다운로드할 때는 인터넷 연결이 필요합니다.

### 모델 수동 다운로드

앱에서 다운로드가 안 되면 해당 모델의 **모델 설정 → 직접 다운로드 하기**를 열거나
아래 파일 페이지 링크를 이용하세요. Hugging Face의 다운로드 버튼으로 파일을 받은 뒤,
Moru의 해당 모델에서 **파일 선택**을 눌러 받은 파일을 지정합니다.
파일 이름을 바꿀 필요 없이 원하는 폴더에 저장할 수 있습니다.

프롬프트 작성·문장 이해·이미지 복원 모델은 두 Anima 버전에 공통으로 필요합니다.
Anima는 사용할 버전만 받으면 됩니다. 두 버전을 모두 사용하려면 둘 다 받으세요.

| 모델 | 받을 파일 |
| --- | --- |
| 프롬프트 작성 모델 | [Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf](https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/blob/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf) |
| 문장 이해 모델 | [qwen_3_06b_base.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/text_encoders/qwen_3_06b_base.safetensors) |
| 이미지 복원 모델 | [qwen_image_vae.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/vae/qwen_image_vae.safetensors) |
| Anima Turbo | [anima-turbo-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-turbo-v1.1.safetensors) |
| Anima Aesthetic | [anima-aesthetic-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-aesthetic-v1.1.safetensors) |

### 소스에서 실행

Git, Python 3.12, uv, Node.js 22.12 이상을 준비한 뒤 PowerShell에서 실행하세요.
처음 준비할 때는 의존성과 ComfyUI를 다운로드합니다.

```powershell
git clone https://github.com/neuwcodebox/moru.git
cd moru
uv sync --frozen --extra inference
uv run --extra inference python scripts/setup_comfyui.py
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
uv run --extra inference python -m moru
```

다음부터는 저장소 폴더에서 `uv run --extra inference python -m moru`로 실행합니다.
모델 설정 방법은 같으며, 이 경우 `data/`와 `models/`도 저장소 폴더에 보관합니다.

## 개발

Python 코어와 React UI로 구성됩니다. 개발 환경 준비, 테스트와 포터블 빌드는
[TECH.md](docs/TECH.md#개발-및-검증), 제품 동작은 [SPEC.md](docs/SPEC.md)를 참고하세요.
