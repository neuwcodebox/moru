# Moru

[English](README.md)

Moru는 대화로 이미지를 만들고 수정하는 Windows 데스크톱 앱입니다.
로컬 LLM 또는 ChatGPT가 요청을 이미지 프롬프트로 작성하고, Anima 또는 FLUX.2가
내 컴퓨터에서 이미지를 생성합니다.

![Moru에서 자연어로 이미지를 생성하고 수정하는 화면](docs/demo-ko.webp)

## 시작하기

Windows, NVIDIA GPU와 드라이버, Windows WebView2 Runtime이 필요합니다.

[포터블 배포본 다운로드 (Google Drive)](https://drive.google.com/file/d/1Y_aYECQ6VqFdV51_GoDl_Uy2-r51NWwW/view?usp=sharing)

`Moru.7z` 전체를 압축 해제하고 `Moru.exe`를 실행하세요. Python, Node.js, ComfyUI는
배포본에 포함되어 있습니다. 모델 파일은 앱에서 별도로 다운로드하거나 직접 지정하며,
각 배포자의 라이선스를 따릅니다.

작업·이미지·설정은 `data/`, 다운로드한 모델은 `models/`에 보관합니다.
앱을 옮길 때는 두 폴더도 함께 옮기세요. 다른 컴퓨터에서는 ChatGPT에 다시 로그인해야 합니다.

## 사용 흐름

### 1. 모델 준비

**모델 준비**에서 이미지 모델을 고르고 필요한 파일을 준비하세요.
Anima Turbo, Anima Aesthetic, FLUX.2 klein 4B를 지원합니다.

이어서 프롬프트 작성 방식을 하나 이상 준비합니다.

- **로컬 LLM:** 모델 파일을 준비해 내 컴퓨터에서 실행합니다. 요청·프롬프트·대화 이력은
  로컬에 머물며, 오프라인에서도 작성할 수 있습니다.
- **ChatGPT:** 계정에 로그인하고 GPT 모델을 선택합니다. 로컬 LLM을 실행하지 않으며,
  인터넷 연결이 필요합니다. 요청·프롬프트·최근 대화 텍스트는 OpenAI로 전송되고,
  ChatGPT 구독 사용량과 콘텐츠 정책이 적용됩니다.

### 2. 생성 설정

**생성 설정**에서 준비된 이미지 모델과 프롬프트 작성 모델을 선택하고 이미지 크기와
생성 옵션을 조절하세요. Anima용 단보루 태그 검색은 로컬 LLM과 ChatGPT 모두에서 켜거나 끌 수 있습니다.
고급 설정에서는 최근 대화를 참고할 범위와 추론 옵션을 정합니다.
변경 사항은 설정 창을 닫으면 저장됩니다.

로컬 LLM과 ChatGPT를 모두 준비했다면 입력창 옆에서 작성 모델을 바로 전환할 수 있습니다.

### 3. 이미지 생성과 수정

원하는 장면을 입력하면 프롬프트를 작성한 뒤 이미지를 생성합니다.
Anima의 태그 검색이 켜져 있으면 요청에 맞는 단보루 태그를 온라인으로 찾아 프롬프트 작성에 참고합니다.
결과를 보고 수정 요청을 보내면 현재 이미지의 프롬프트와 최근 대화를 참고해 새 이미지를 만듭니다.

> 금발 여성이 편의점에서 라면을 먹는 장면.
>
> 비가 내리는 저녁으로 바꿔줘.
>
> 표정은 무표정하게 해줘.

이미지의 **프롬프트** 메뉴에서 실제 프롬프트를 확인·복사하거나 직접 고쳐 생성할 수도 있습니다.
태그 검색에 참고한 정보는 **소스** 메뉴에서 확인합니다.

### 4. 결과 비교와 다른 방향으로 이어가기

- **다시:** 같은 프롬프트와 현재 생성 설정으로 다른 결과를 만듭니다. 직접 프롬프트를 수정한
  결과도 같은 대화 행의 버전으로 묶이며, 원하는 버전을 선택해 다음 대화를 이어갑니다.
- **분기:** 선택한 이미지까지의 대화를 새 작업으로 복사합니다. 원래 작업을 보존하면서
  다른 스타일이나 장면을 시도할 수 있습니다.

이미지를 누르면 전체 화면에서 확대·이동하며 버전을 비교하고 클립보드에 복사할 수 있습니다.
작업과 결과는 자동으로 로컬에 저장되므로 나중에 다시 열어 이어서 만들 수 있습니다.

## 모델 파일 직접 준비하기

앱에서 다운로드가 안 되면 **모델 준비 → 직접 다운로드 하기**의 링크로 파일을 받은 뒤
**파일 선택**으로 지정하세요. 기존 파일 이름과 저장 위치를 그대로 사용할 수 있습니다.

<details>
<summary>모델별 파일 안내</summary>

Anima는 Turbo 또는 Aesthetic 가중치 하나와 공통 문장 이해·이미지 복원 모델이 필요합니다.
FLUX.2 klein 4B는 전용 모델 세 파일이 필요하며, 프롬프트 작성용 GGUF는 로컬 LLM을 사용할 때 준비합니다.

| 모델 | 받을 파일 |
| --- | --- |
| 로컬 프롬프트 모델 | [Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf](https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/blob/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf) |
| Anima 문장 이해 모델 | [qwen_3_06b_base.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/text_encoders/qwen_3_06b_base.safetensors) |
| Anima 이미지 복원 모델 | [qwen_image_vae.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/vae/qwen_image_vae.safetensors) |
| Anima Turbo | [anima-turbo-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-turbo-v1.1.safetensors) |
| Anima Aesthetic | [anima-aesthetic-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-aesthetic-v1.1.safetensors) |
| FLUX.2 klein 4B | [flux-2-klein-4b-fp8.safetensors](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/blob/5b4408e59397a4a37ccb46afe426d8ed86379441/flux-2-klein-4b-fp8.safetensors) |
| FLUX.2 문장 이해 모델 (FP4) | [qwen_3_4b_fp4_flux2.safetensors](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/blob/8556e4d870cda7c53c7942b190bfeea5be9bd411/split_files/text_encoders/qwen_3_4b_fp4_flux2.safetensors) |
| FLUX.2 이미지 복원 모델 | [flux2-vae.safetensors](https://huggingface.co/Comfy-Org/flux2-klein-4B/blob/5f526678002e43af5551dadb73ce2e8c91b43afe/split_files/vae/flux2-vae.safetensors) |

</details>

## 소스에서 실행

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
모델 준비와 사용 흐름은 같으며, `data/`와 `models/`는 저장소 폴더에 보관합니다.

## 개발

개발 환경·테스트·포터블 빌드는 [TECH.md](docs/TECH.md#개발-및-검증),
상세 제품 동작은 [SPEC.md](docs/SPEC.md)를 참고하세요.
