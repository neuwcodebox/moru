# Moru × Sign in with ChatGPT 기술 조사

2026년 10월 10일 기준 · OpenAI 공식 개발자 문서 및 Moru GitHub 저장소

## 1. 결론: Moru에 도입할 수 있습니다

Moru의 프롬프트 생성 LLM을 ChatGPT 구독으로 사용할 수 있도록 만드는 방식이 가장 적합합니다.

현재 [Moru](https://github.com/neuwcodebox/moru)는 Python + React + pywebview 기반 Windows 데스크톱 앱이며, 로컬 LLM이 이미지 생성 프롬프트를 작성하고 Anima 또는 FLUX.2가 로컬에서 이미지를 생성합니다.

OpenAI가 공개한 오픈소스 앱용 \*Sign in with ChatGPT(SIWC)\*는 다음을 지원합니다.

- 별도 API 키 없이 ChatGPT 계정으로 OAuth 로그인
- 사용자의 ChatGPT Plus·Pro 구독으로 지원되는 AI 추론 요청
- 앱 실행 환경에서 직접 사용자 인증 정보 관리
- OAuth 클라이언트 동적 등록(Dynamic Client Registration)

별도 파트너 승인을 받아야 하는 일반 상용 웹사이트 로그인과 구분되는 기능입니다.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.openai.com\&sz=32)

OpenAI Developers

+1



### Moru에 적용할 구조

Moru · React UI

자연어 요청 · 프롬프트 수정 · 이미지 히스토리

Python 애플리케이션

로컬 LLM

기존 Qwen + llama.cpp

ChatGPT

OAuth + Responses API

선택한 LLM이 이미지 프롬프트 작성

로컬 이미지 생성 · ComfyUI

Anima / FLUX.2 → 이미지 → 기존 히스토리

이렇게 구성하면 기존 이미지 생성 파이프라인은 유지하면서 프롬프트 생성 모델만 선택할 수 있습니다. 로그인하지 않은 사용자도 기존 로컬 모델을 계속 사용하도록 만들면 됩니다.

다만 ChatGPT 구독 사용은 지원되는 Responses API 요청에 한정되며, 일반 OpenAI API 전체를 자유롭게 사용하는 권한은 아닙니다.

## 2. OAuth 인증 구현

공식 문서: [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)

### 인증 과정

1. Moru에서 로그인 시작

   Python이 `state`, `nonce`, PKCE verifier를 생성하고 `127.0.0.1`에 임시 콜백 리스너를 실행합니다.
2. 시스템 브라우저에서 ChatGPT 인증

   `https://auth.openai.com/api/accounts/authorize`로 이동합니다. 사용자가 자신의 계정으로 로그인하고 권한을 승인합니다.
3. Moru가 인증 코드를 수신

   브라우저가 `http://127.0.0.1:<port>/auth/callback`으로 리디렉션합니다. `state` 검증 후 authorization code를 받습니다.
4. OAuth 토큰 교환 및 검증

   Python이 코드를 access token·refresh token·ID token으로 교환합니다. ID token 서명, issuer, audience, nonce를 검증합니다.
5. 연결 완료

   인증 정보를 보호된 로컬 저장소에 보관합니다. 이후 해당 계정으로 모델 조회와 추론 요청이 가능합니다.

### 최초 등록에 필요한 값

| 항목                      | 값                                                  |
| ----------------------- | -------------------------------------------------- |
| Authorization endpoint  | `https://auth.openai.com/api/accounts/authorize`   |
| Token endpoint          | `https://auth.openai.com/api/accounts/oauth/token` |
| 최초 `client_id`          | `dynamic_agent_client`                             |
| `agent_name_hint`       | `Moru`                                             |
| `ext_agent_host_id`     | 설치 환경별 영구 UUID                                     |
| `response_type`         | `code`                                             |
| `code_challenge_method` | `S256`                                             |
| `redirect_uri`          | `http://127.0.0.1:1455/auth/callback` 등            |
| `resource`              | `https://api.openai.com/v1`                        |

요청할 OAuth scope는 다음과 같습니다.

```
openid profile email offline_access resource.invoke chatgpt.tokens.use.direct
```

중요한 부분은 최초 `client_id`입니다.

기존 OAuth 서비스처럼 개발자가 사전에 콘솔에서 애플리케이션을 등록하고 클라이언트 ID를 발급받을 필요가 없습니다.

첫 승인 후 콜백에서 실제로 발급된 `oaiapp_...` 형태의 ID를 저장하고 이후에는 그 ID를 재사용합니다. `dynamic_agent_client`는 최초 등록에만 사용합니다.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.openai.com\&sz=32)

OpenAI Developers

+1



Moru는 pywebview가 정적 React UI를 표시하는 구조인데, 인증을 위해 UI 전체를 HTTP 서버로 전환할 필요는 없습니다. 로그인 동안에만 Python 표준 라이브러리 `http.server`로 loopback 리스너를 실행하면 됩니다. 인증 화면은 내장 WebView가 아닌 시스템 기본 브라우저를 사용합니다.

## 3. ChatGPT 모델 호출

공식 문서: [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)

인증 후 다음 요청으로 현재 계정에서 사용 가능한 모델을 조회합니다.

```
GET https://api.openai.com/v1/models
Authorization: Bearer <ACCESS_TOKEN>
```

응답의 `models` 배열에서 `visibility == "list"`인 항목을 가져와 `display_name`으로 표시하고, 실제 요청에는 `slug`를 전달합니다.

모델명을 하드코딩하지 않는 편이 좋겠습니다.

### Responses API 예시

Moru에서 사용하려면 다음과 같은 요청 구조가 됩니다.

```
from openai import OpenAIclient = OpenAI(    api_key=access_token,    max_retries=0,)messages = prompt_messages(    text=user_request,    base_prompt=previous_prompt,    history=history,    model_id=image_model_id,)with client.responses.create(    model=selected_model_slug,    instructions=messages[0]["content"],    input=messages[1:],    store=False,    stream=True,) as stream:    for event in stream:        if event.type == "response.output_text.delta":            on_prompt_delta(event.delta)        elif event.type == "response.failed":            raise RuntimeError(event.response.error)        elif event.type == "response.completed":            on_completed()
```

핵심 API 호출 예시입니다. 실제 구현에서는 토큰 갱신, 취소, 완료 이벤트 확인, 응답 누적 및 Moru 오류 변환이 추가로 필요합니다.

기존 Moru의 `prompt_messages()`를 재사용하되, `system` 메시지는 `instructions`로 분리해야 합니다.

### 현재 Preview API 제약

| 항목                            | 지원     |
| ----------------------------- | ------ |
| Responses API                 | 지원     |
| SSE 스트리밍                      | 필수     |
| `store: false`                | 필수     |
| `instructions`                | 지원     |
| 사용자·어시스턴트 대화 이력               | 지원     |
| 텍스트·이미지 입력                    | 모델별 지원 |
| `temperature`, `top_p`        | 미지원    |
| `max_output_tokens`           | 미지원    |
| `previous_response_id` (HTTP) | 미지원    |
| 이미지 생성 도구                     | 미지원    |

따라서 Moru의 기존 `context_size`, `max_tokens`, `thinking` 등 로컬 LLM 전용 설정을 클라우드 모델에 그대로 적용하면 안 됩니다.

특히 Responses 요청마다 필요한 대화 이력을 전부 전달해야 합니다. 이 부분은 Moru가 이미 최근 요청과 이전 이미지의 실제 프롬프트를 기반으로 컨텍스트를 구성하므로 잘 맞습니다.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.openai.com\&sz=32)

OpenAI Developers

+1



## 4. 실제 Moru 코드에서 수정할 부분

현재 GitHub `main` 브랜치의 코드를 읽어보니, 이미 `PromptGenerator` 프로토콜로 엔진 경계가 분리되어 있습니다. 따라서 대규모 리팩터링은 필요 없어 보입니다.

| 파일                                                                                                    | 변경 내용                                     |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| [`ports.py`](https://github.com/neuwcodebox/moru/blob/main/src/moru/ports.py)                         | 기존 `PromptGenerator` 계약 유지                |
| [`prompting.py`](https://github.com/neuwcodebox/moru/blob/main/src/moru/prompting.py)                 | `prompt_messages()`와 `final_prompt()` 재사용 |
| `chatgpt_auth.py` (신규)                                                                                | OAuth PKCE, 토큰 검증·갱신·폐기                   |
| `chatgpt_prompts.py` (신규)                                                                             | Responses API를 사용하는 `PromptGenerator` 구현  |
| [`desktop.py`](https://github.com/neuwcodebox/moru/blob/main/src/moru/desktop.py)                     | 로컬/ChatGPT 프롬프트 엔진 선택 및 연결                |
| [`service.py`](https://github.com/neuwcodebox/moru/blob/main/src/moru/service.py)                     | 공급자별 추론 및 GPU 메모리 처리                      |
| [`api.py`](https://github.com/neuwcodebox/moru/blob/main/src/moru/api.py)                             | 로그인, 로그아웃, 모델 조회 bridge                   |
| [`SettingsDialog.tsx`](https://github.com/neuwcodebox/moru/blob/main/frontend/src/SettingsDialog.tsx) | LLM 공급자·ChatGPT 계정·모델 선택 UI               |

기존 로컬 LLM은 `LlamaPrompts`이고, 여기에 동일한 프로토콜을 구현한 `ChatGPTPrompts`를 추가하면 됩니다.

```
class ChatGPTPrompts:    def create(self, text, settings, cancelled, progress,               *, history=(), model_id="anima-turbo-v1.1"):        ...    def refine(self, prompt, text, settings, cancelled, progress,               *, history=(), model_id="anima-turbo-v1.1"):        ...    def memory_required(self, settings):        return 0    def unload(self):        pass
```

여기서 `memory_required()`가 0을 반환하는 것이 핵심입니다. 클라우드 프롬프트 생성에는 GPU 메모리가 필요 없으므로 Moru가 기존처럼 LLM 로딩 공간을 확보할 필요가 없습니다.

현재 `Application`에는 프롬프트 생성 전 GPU 공간 확보 과정이 들어 있습니다. 공급자가 ChatGPT인 경우엔 이 과정을 건너뛰어야 합니다.

그 밖에 시작 시 로컬 GGUF 프롬프트 모델을 필수로 요구하는 검사도 변경해야 합니다. ChatGPT를 선택했다면 이미지 모델만 준비되어 있어도 실행할 수 있어야 합니다.

## 5. 사용자 인터페이스

Moru의 기존 생성 설정 팝업에 다음 정도만 추가하면 충분하겠습니다.

프롬프트 작성 모델

UI 예시

로컬 LLMChatGPT

ChatGPT 연결됨

user\@example.com

모델자동 선택

ChatGPT 구독 사용량 적용

&#x20;사용량 관리

프롬프트 작성에 사용하는 요청 내용이 OpenAI 서버로 전송됩니다. 이미지 생성은 로컬에서 수행됩니다.

조작 가능한 UI 구성 예시이며 실제 계정 연결 또는 모델 조회 기능은 없습니다. 실제 모델 목록은 로그인 후 API에서 받아야 합니다.

공식 UI 가이드에서도 연결 후 계정 표시, 구독 사용 안내, 사용량 관리 링크, 사용량 제한 발생 시 안내를 요구하고 있습니다.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.openai.com\&sz=32)

OpenAI Developers



## 6. 인증 정보와 구독 제한

### 토큰 수명 및 보안

공식 문서에 명시된 토큰 정책입니다.

| 토큰             | 수명                          |
| -------------- | --------------------------- |
| Access token   | 1시간                         |
| Refresh token  | 30일                         |
| Refresh 후 새 토큰 | 30일 연장, 이전 refresh token 교체 |

Refresh token은 교체 방식이므로 같은 세션에서 동시 갱신이 일어나지 않도록 잠금을 사용해야 합니다.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.openai.com\&sz=32)

OpenAI Developers

+1



Windows 데스크톱 앱인 Moru에서는 토큰을 Windows DPAPI로 암호화하여 저장하는 방식을 권장합니다. React나 WebView의 localStorage에는 넣지 않고, Python 프로세스에서만 접근하도록 합니다.

설치별 host ID와 계정 연결 정보는 재시작 후 유지하되, 인증 토큰은 휴대용 앱 디렉터리와 분리해 사용자별 보호된 영역에 저장하는 편이 안전합니다.

### 구독 제한 및 오류

| 오류                                            | Moru 처리               |
| --------------------------------------------- | --------------------- |
| `subscription_sharing_user_not_eligible`      | 현재 계정이나 플랜에서 사용 불가 안내 |
| `subscription_sharing_usage_limit_exceeded`   | 사용량 관리 페이지 안내         |
| `subscription_sharing_unsupported_capability` | 미지원 API 옵션 확인         |
| `subscription_sharing_usage_unavailable`      | 일시적 실패, 제한된 재시도       |
| 토큰 만료                                         | Refresh 후 재시도         |
| 연결 해제                                         | 재로그인 안내               |

공식 Quickstart는 현재 Plus와 Pro를 지원 대상 요금제로 명시합니다. 그 외 요금제에 대해서는 실제 로그인과 사용 권한을 확인해야 합니다.

참고로 Plus의 5시간 사용량 한도는 연결된 앱들과 공유되고, Pro에는 그 5시간 한도가 적용되지 않는다고 문서에 명시되어 있습니다. 앱별 제한은 별도로 있을 수 있습니다.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.openai.com\&sz=32)

OpenAI Developers

+2



## 7. Moru에서 특별히 주의할 점

### 기존 로컬 전용 정책 변경

현재 Moru의 README와 SPEC은 사용자의 요청과 이미지가 외부로 전송되지 않는다는 것을 핵심 특징으로 내세우고 있습니다.

ChatGPT 공급자를 활성화하면 자연어 요청·기존 이미지 프롬프트·일부 대화 이력이 OpenAI에 전달되므로 다음처럼 동작을 명확하게 구분해야 합니다.

- 로컬 LLM: 기존과 동일하게 완전 로컬 동작
- ChatGPT: 프롬프트 작성 관련 텍스트만 전송
- 이미지 생성 결과: 계속 로컬에 저장

이것은 단순히 로그인 버튼을 추가하는 것보다 중요한 제품 요구사항 변경입니다.

### 라이선스 확인 필요

현재 GitHub 저장소를 확인했는데 Moru는 공개 저장소이지만 루트에 `LICENSE` 파일이 없고, GitHub API의 `license` 값도 `null`입니다.

공개 저장소와 오픈소스 라이선스를 부여한 프로젝트는 다릅니다. OpenAI의 일반 공개 경로가 오픈소스 앱 대상이므로, 정식 배포 전에 Moru의 라이선스를 명확히 정하는 것이 좋겠습니다. 라이선스 부재만으로 OAuth가 반드시 차단되는지는 공식 문서에서 확인되지 않았습니다.

또한 OpenAI 약관은 SIWC로 사용자의 ChatGPT 구독을 이용하는 기능을 앱의 유료 버전으로 제한하지 못하도록 규정하고 있습니다.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://openai.com\&sz=32)

OpenAI



## 8. 실제 시험 구현 순서

처음부터 전체 기능을 만들기보다는 두 단계로 나누는 편이 낫겠습니다.

1. 1차: 인증과 단순 추론 검증

   Python에서 OAuth 동적 등록 → 브라우저 로그인 → 토큰 검증 → 모델 목록 조회 → 간단한 Responses 요청까지 구현합니다. 이 단계에서 실제 계정의 SIWC 사용 가능 여부를 확인할 수 있습니다.
2. 2차: Moru 통합

   `ChatGPTPrompts`를 추가하고 공급자 선택, 사용자 요청·프롬프트 전송, 스트리밍 진행 표시, 취소, 인증 갱신, 오류 처리를 기존 이미지 생성 흐름과 연결합니다.

테스트는 OAuth state/nonce 검증, 토큰 교체, 응답 스트림 중단, 프롬프트 검증, 공급자 전환을 가짜 외부 클라이언트로 검증하고, 실제 API 로그인과 추론은 별도 통합 테스트로 분리하는 것이 적절합니다.

## 공식 자료 모음

| 문서                                                                                                          | 주요 내용                 |
| ----------------------------------------------------------------------------------------------------------- | --------------------- |
| [Quickstart](https://developers.openai.com/siwc/quickstart)                                                 | 전체 기능과 개방 범위          |
| [OSS Overview](https://developers.openai.com/siwc/token-sharing-open-source)                                | Host ID, Client ID 개념 |
| [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)            | OAuth 요청 및 토큰 교환      |
| [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)   | 실제 API 호출 코드          |
| [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions) | 토큰 갱신, 계정 관리          |
| [Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)     | API 필드와 도구 제한         |
| [Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)     | 에러 코드별 처리             |
| [UI/UX guidelines](https://developers.openai.com/siwc/ui-ux-guidelines)                                     | 로그인 UI, 사용량 표시        |

전체적으로 Moru는 이미 엔진 추상화가 잘 되어 있어서 ChatGPT 공급자를 추가하기 좋은 상태입니다. 우선 별도의 작은 OAuth 검증 코드를 만들어 실제 구독 기반 Responses 요청이 성공하는지 확인한 다음, 기존 `PromptGenerator`에 연결하는 방식을 권장합니다.

Codex app-server를 별도로 설치하거나 실행할 필요도 없습니다. Moru는 코딩 에이전트가 아니라 이미지 프롬프트 작성이 목적이므로, 공식 문서에서 지원하는 Responses API 직접 호출이 더 간단하고 적합합니다.

현재까지는 공식 문서와 저장소 코드에 기반한 기술 검토이며, 실제 Moru 계정 로그인이나 SIWC 추론 호출까지 실행해 확인한 상태는 아닙니다.

## 9. 구현 및 검증

- 로컬 LLM과 ChatGPT 중 하나 이상을 준비하고, 둘 다 준비한 경우 생성 입력 영역에서 전환하도록 구현했다.
  ChatGPT 전용 시작은 GGUF를 요구하지 않으며 로컬 LLM용 상세 지침과 ChatGPT용 간결한 지침을 분리했다.
- OAuth PKCE·OIDC 서명/클레임 검증·DPAPI 저장·회전 토큰 갱신·연결 해제와 계정별 모델 조회를 추가했다.
  Responses 완료·거절·취소·중단을 구분하며 자동 제공자 전환은 하지 않는다.
- 현재 요구사항과 구조는 [SPEC](../SPEC.md#34-프롬프트-작성-제공자)과
  [TECH](../TECH.md#chatgpt-프롬프트-제공자)에 반영했다. 기존 검토 원문은 유지했다.
  한국어·영어 README는 프롬프트 작성 방식의 선택, 이미지 모델 준비, 생성 시작 순서로 다시 정리했다.
  수동 다운로드 안내는 이미지 모델별 파일 구성과 로컬 LLM용 GGUF 준비 조건을 연결해 설명하며,
  두 언어의 내용과 실제 모델 준비·생성 설정 화면을 대조했다. 로컬 단보루 조회·전송 범위·조회 실패 시
  동작도 두 README에 동일하게 반영했고, 두 언어를 함께 갱신하는 규칙을 [AGENTS.md](../../AGENTS.md)에 기록했다.
- 모델 준비는 선택한 방식의 파일 준비 또는 계정 연결·GPT 모델 선택만 표시한다.
  GPT 모델 선택은 즉시 저장하며 활성 제공자를 바꾸지 않는다. 준비 화면에는 별도 저장 버튼을 두지 않는다.
  생성 설정은 준비된 작성 모델 선택, 이미지 옵션과 접힌 고급 추론 옵션을 제공하며 닫을 때 변경을 함께 저장한다.
  별도 저장 버튼은 없고 모든 닫기 경로는 저장 성공 후 종료한다. 검증·저장 실패는 입력값과 팝업을 유지한다.
  ChatGPT 선택 시 로컬 전용 추론 옵션은 숨기되 방식 전환 중 입력한 값은 유지한다.
  첫 로그인 안내 후에도 준비 선택을 유지하고, 숨겨진 모델의 다운로드 취소를 지원한다.
  ChatGPT에서 로컬 LLM으로 전환하면 프롬프트 모델 로딩과 추론 상태를 구분한다. 엔진 준비 완료 후에만
  생각 중 상태로 전환하고, 적재된 모델을 재사용하면 로딩 표시는 생략한다.
  계정 상태에 따라 로그인·재로그인·권한 허용을 구분하고, 모델 선택 옆에 새로고침 아이콘,
  계정 카드 상단에 사용량 링크, 접힌 이용 안내에 전송·정책 설명을 배치했다.
  선택된 제공자 이름의 중복 제목을 제거하고 계정 라벨과 사용량 링크를 한 행에 배치했다.
  두 화면은 이미지 설정을 먼저, 프롬프트 모델을 다음에 표시하고 두 영역 사이에 구분선을 둔다.
  생성 설정의 고급 옵션은 별도 구분선 없이 프롬프트 모델 선택 바로 아래에 배치했다.
  입력 도구 영역은 투명하게 대화 위에 겹치되 선택 메뉴·새 작업 버튼 자체는 불투명하게 유지한다.
  입력 영역 높이에 맞춰 마지막 내용의 여백을 확보한다.
  자연어 요청은 전송 직후 맨 아래로 이동하며, 이전 대화를 읽는 동안의 결과 갱신은 위치를 유지한다.
- ChatGPT 추론 수준을 생성 설정의 고급 옵션에 추가했다. 로컬 추론 수준과 독립적으로 저장하고,
  모델 기본값에서는 API 필드를 생략하며 선택한 수준만 `reasoning.effort`로 보낸다.
  모델별 선택지는 [공식 모델 안내](https://developers.openai.com/api/docs/guides/deployment-checklist)와
  [GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4),
  [GPT-5.5](https://developers.openai.com/api/docs/models/gpt-5.5) 문서 기준이다.
  알 수 없는 계정 모델 별칭은 기본값만 제공한다. 미지원 설정을 자동으로 바꾸지 않으며,
  저장 검증 실패는 이미지·프롬프트 설정을 모두 보존하고 API 거절은 재요청 없이 표시한다.
- Anima용 ChatGPT에 세 독립 단보루 검색 도구를 연결했다. 계약과 호출 제한은
  [TECH](../TECH.md#chatgpt-프롬프트-제공자)에 정리했다. 결과는 필요한 태그 이름·설명만 보내며
  요청의 핵심 개념에 맞는 정식 태그 이름과 의미를 확인하도록 지침을 바꿨다.
  조회 실패는 모델에 전달한 뒤 최종 작성을 계속하고,
  취소와 GPT 자체의 거절·중단은 기존 실패 경로를 유지한다. 중간 검색 설명은 프롬프트 미리보기에 표시하지 않는다.
  HTTP 429는 1초 후 한 번 재시도하며, 각 호출은 10초 타임아웃을 적용한다.
  이미지 메뉴의 소스 팝업에서 실제 조회의 입력·참고 자료·실패를 확인한다. 자료는 이미지 버전별로
  저장하고 기존 DB에는 빈 소스 열을 추가한다. 재시작·Fork·같은 프롬프트 재생성에도 자료가 유지된다.
  소스의 위키 본문과 관련 태그 목록은 항목별로 접어두고 목록의 개수를 표시한다.
  생성 설정의 작성 모델 선택과 고급 설정 사이에 공통 태그 검색 옵션을 배치했다. 끄면 로컬의 검색 단계와
  ChatGPT의 도구·조회 지침을 생략하며, 닫을 때 저장하고 재시작·제공자 전환에도 값을 유지한다.
  접기 스타일을 공유하고 검색 가능 여부를 명시했으며, 설정 테스트의 버튼 순서 의존과 불필요한 변수를 정리했다.
  관련 Python 테스트 162개, 소스·설정 UI 11개와 기존 설정·전환 UI 9개, ruff·TypeScript 검사·Vite 빌드가
  통과했다. 전체 테스트는 재실행하지 않았다.
- 빈 최종 프롬프트 오류의 진단을 위해 요청·응답·도구·최종 검증 로그를 요청 ID로 연결했다.
  상세 기록과 비공개 정보 제외 범위는 [TECH의 로그 정책](../TECH.md#27-로그)을 따른다.
  실제 재현 로그에서 빈 완료 output이 먼저 수신한 검색 도구 호출을 덮어쓰는 결함을 확인했다.
  빈 배열에서는 완료된 스트리밍 항목을 보존해 검색·추론 이력과 최종 답변을 유지한다.
  회귀 테스트는 수정 전 실패·수정 후 통과를 확인했다. 관련 테스트 68개와 ruff가 통과했고,
  사용자 요청에 따라 이 후속 수정의 전체 테스트는 다시 실행하지 않았다.
- 진행 표시를 초기 생각 중, 태그 검색 중, 최종 프롬프트 생성 중으로 구분했다.
  실제 도구 호출·조회와 답변 시작을 콜백으로 전달하며, 추가 조회 동안 검색 상태를 유지한다.
  중간 검색 설명은 최종 답변으로 표시하지 않고 placeholder 위치와 크기를 유지한다.
  검색 상태 줄에는 조회마다 중복 없이 누적한 태그 수를 갱신한다. 빈 결과·실패는 개수를
  늘리지 않으며 검색 종료 시 숨긴다. 각 작업은 0에서 시작한다.
  관련 Python 테스트 51개·진행 UI 테스트 5개, ruff·TypeScript 검사와 Vite 빌드가 통과했다.
  사용자 요청대로 전체 테스트는 재실행하지 않았다.
- 검색 결과 활용 지침과 세 도구 설명을 정리했다. 문서의 용법·조합·예외를 사용자 요청에
  반하지 않는 범위에서 전체 프롬프트에 적용하며, 특정 태그에 대한 별도 규칙은 추가하지 않았다.
  관련 테스트 81개와 ruff가 통과했다. 검증 범위는 지침 전달·문서 내용 보존·기존 도구 흐름이며,
  실제 GPT의 작성 품질은 이 자동 테스트로 보장하지 않는다. 전체 테스트는 재실행하지 않았다.
- 로컬 LLM의 Anima 작성에도 [두 단계 태그 검색](../TECH.md#74-로컬-태그-검색)을 연결했다.
  검색어를 한 번 생성하고 후보 이름만 조회해 한도 안에서 최종 작성에 전달한다. 현재 상태와
  보존된 이력·적재 모델은 공유하며 검색 출력은 숨긴다. 조회 실패는 소스에 기록하고 작성을 계속한다.
  실제 조회의 진행·중복 없는 태그 수·이미지별 소스는 기존 계약으로 전달한다. 상세·관련 태그 조회는 없다.
  로컬 출력 처리와 외부 조회 계약을 분리하고 중복 컨텍스트 계산을 정리했다.
  관련 테스트 177개와 ruff가 통과했다. 입력·예산·실패·취소·소스 저장과 두 작성 단계의
  동일한 추론 설정·쉼표 출력·공통 종료 안내를 가짜 경계로 검증했다.
  전체 테스트는 재실행하지 않았다. [실제 쿼리 smoke](../../scripts/smoke_tag_queries.py)에서
  설정된 Qwen3.5-4B Uncensored HauhauCS Aggressive Q4_K_M을 RTX 3060으로 실행해
  생성·색상 수정·이력 참조 수정·동물 장면 네 사례 모두 검색어를 받았다. 기본 thinking과
  사용자 출력 예산을 유지하며 색상 수정은 `sofa`, `blue`, 동물 장면은 `rabbit`, `white`,
  `carrot`, `sleeping`을 검색했다. 이력 참조는 `raincoat`를 찾았지만 유지할 머리색도 포함해
  변경 대상 선택의 한계가 남는다. 검증 범위는 실제 쿼리 추론이며 HTTP 조회와 이미지 생성은 포함하지 않는다.
- 리팩토링: [TECH의 폴더 구조](../TECH.md#31-구현-및-고정-런타임)에 따라 ChatGPT·단보루·
  프롬프트·이미지 구현을 역할별 패키지로 정리하고 UI도 기능별 폴더와 공통 컴포넌트로 구성했다.
  작성 지침과 요청별 도구 실행 상태를 분리했으며 공통 취소 검사로 조회 계층의 텍스트 처리 의존을 제거했다.
  기존 생성·소스·오류·진행 표시 계약을 유지하고 실행 진입점·smoke 스크립트·테스트 참조를 함께 갱신했다.
  새 의존성이나 범용 프레임워크는 추가하지 않았다. 관련 Python 테스트 378개와 UI 테스트 150개,
  ruff·TypeScript 검사·Vite 빌드가 통과했다. 최종 도구 실행 정리 후 관련 테스트 45개도 통과했다.
  wheel의 새 모듈·리소스 포함, wheel만 사용한 주요 모듈 import와 CLI 진입점을 확인했다.
  사용자 요청대로 전체 테스트는 재실행하지 않았다.
- 검증: 일반 Python 테스트 520개, React 테스트 167개, ruff·TypeScript 검사와 Vite 빌드가 통과했다.
  두 제공자의 생성·수정에 이력·이미지 모델·준비 완료 콜백이 전달되는지, 두 선택 메뉴에서
  미연결·권한 부족·모델 미준비·로그인 진행 중 조건을 같은 기준으로 처리하는지 테스트했다.
  자동 저장은 네 닫기 경로, 입력 검증, 저장 실패 재시도와 중복 요청 방지를 테스트하고 WebView2에서도 확인했다.
  첫 적재·ChatGPT 전환·컨텍스트 변경·모델 재사용과 로딩 실패·취소의 상태 전환은 가짜 엔진으로 검증했다.
  Python 테스트의 임시 디렉터리는 기존 Windows 임시 폴더 접근 오류를 피해 build 아래 고유 경로를 사용했다.
  가짜 계정을 사용한 640px WebView2에서 생성 화면·설정·모델 준비·제공자 전환과 화면 넘침을 확인했다.
  준비 화면의 추론 옵션 제거, 생성 설정의 제공자별 옵션 표시와 닫을 때 자동 저장도 확인했다.
  이미지 우선 순서, 준비 영역 사이 구분선과 중복 제목 제거도 React 테스트·WebView2에서 확인했다.
  전송 버튼·Enter의 즉시 이동과 기존 읽기 위치 유지도 확인했다. 긴 대화 WebView2에서는 도구 영역 뒤의
  대화 표시와 빈 공간의 클릭 통과, 여러 줄 입력창의 하단 여백과 화면 넘침을 검증했다.
  공급자 전환 전후 입력창·새 작업 버튼·선택 메뉴의 좌표와 크기가 같고, 새로고침 버튼은 드롭다운 옆의
  정사각형이며 사용량 링크와 떨어져 있음을 실제 WebView2에서 확인했다.
  GPT 추론 수준은 기존 설정의 기본값 복원, 제공자 전환 중 값 유지, 생성·수정 요청의 필드 전달,
  미지원 설정의 저장 원자성과 API 거절을 가짜 외부 응답으로 검증했다.
  WebView2에서 지원 수준 선택, 로컬 옵션과의 독립성, 닫을 때 자동 저장과 화면 넘침도 확인했다.
  사용자도 추론 수준 설정까지 실제 앱 실행에서 문제없음을 확인했다.
  단보루 세 도구는 실제 공개 API에서 읽기 전용으로 확인했다. 가짜 응답으로 전체 도구·추론 이력
  재전달, 실행 한도, 조회 실패 후 이미지 생성 완료, 취소·429 재시도·10초 기한과
  조회 후 GPT 거절·중단 시 이미지 미생성을 검증했다. 소스 저장·기존 DB 열 추가·재시작·분기·재생성과
  선택 버전의 소스 표시, 빈 결과·조회 실패 구분·텍스트 렌더링을 테스트했다. 640px WebView2에서는
  `smoke_ui_interactions.py --sources-only`로 소스 팝업의 표시·스크롤·배경 잠금·메뉴 초점 복원을 확인했다.
  전체 native smoke는 기존 hover 합성 이벤트 검사에서 중단되어 새 화면을 독립 검증했다.
  진단 로그는 추론 전용·빈 응답, 중단·잘못된 출력, 인증 재시도·조회 실패와 요청별 연결을
  가짜 응답으로 검증했으며 요청·응답 원문과 토큰이 기록되지 않는지도 확인했다.
- 제한: 실제 계정의 로그인·구독 추론 및 새 도구의 연속 Responses 호출은 자동화된 통합 검사에
  포함하지 않았고, 새 portable 배포본은 아직 검증하지 않았다.
  정식 배포 전 라이선스 확정과 배포 환경에서의 통합 확인이 필요하다.
