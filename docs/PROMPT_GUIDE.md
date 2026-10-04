# 이미지 프롬프트 작성 지침

이 문서는 프롬프트 LLM에 전달하는 규칙의 근거와 작성 예시를 설명한다.
실제로 전달하는 영문 지침은 `src/moru/prompt_instructions.py`의
`CREATE_SYSTEM`과 `REFINE_SYSTEM`이다. 앱은 이 문서 전체를 컨텍스트에 넣지 않는다.
작성 규칙과 필요한 태그 예시를 압축해 전달하고, 생성과 수정에 각각 맞는 예시를 사용한다.

## 조사 근거와 적용 범위

2026-10-05에 모델 제작자와 서비스 제작자의 문서를 확인했다.

| 자료 | 확인한 내용 | Moru에 적용하는 방법 |
| --- | --- | --- |
| [Anima 제작자 가이드](https://huggingface.co/circlestone-labs/Anima#prompting) | 태그·자연어 혼용, 태그 표기, 여러 인물의 외모 연결, 버전별 품질 태그 차이 | 현재 이미지 엔진의 문법과 선택한 버전의 제약을 우선한다. LLM 지침에는 모델명을 넣지 않는다. |
| [NovelAI 태그 설명](https://docs.novelai.net/en/image/tags/) | 학습된 시각적 개념을 태그로 표현하며, 태그와 강조 문법은 모델에 따라 다름 | 태그를 선택하는 방법을 참고한다. 서비스 전용 문법이나 품질 태그를 가져오지 않는다. |
| [NovelAI 이미지 생성 입문](https://docs.novelai.net/en/image/tutorial-imgintro/) | 쉼표로 구분한 영문 태그, 인물 추가 시 `no humans`와의 충돌 | 태그 목록을 문장과 연결하고 대상 수·배제 조건을 일치시킨다. |
| [Stable Diffusion XL 모델 카드](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | 장면을 묘사하는 자연어 입력 예시와 위치 관계 생성의 한계 | 주체·행동·장소를 구체적으로 쓰되, 좋은 문장이 관계 표현을 보장한다고 주장하지 않는다. |

공통으로 쓸 수 있는 것은 시각적으로 구체적인 묘사, 대상별 속성 연결,
상충하는 묘사 제거다. `score_*`, 작가 접두사, 강조 괄호, 모델 전용 태그는
모든 Stable Diffusion 계열에 통하는 표준이 아니다.
여기서 제시하는 순서는 작성과 검토를 쉽게 하는 순서이며,
태그를 앞에 두면 언제나 더 강하게 반영된다는 뜻이 아니다.

## 출력 계약

- 완성된 **영어 positive prompt 한 문단**만 반환한다.
- 관련 태그와 장면을 설명하는 짧은 문장을 함께 쓴다.
- 제목, 설명, Markdown, JSON, 필드명, 전체를 감싼 인용부호를 붙이지 않는다.
- negative prompt, seed, CFG, steps, 해상도 플래그, LoRA 호출을 쓰지 않는다.
- 수정 요청에도 변경 목록이나 패치 대신 전체 프롬프트를 반환한다.

문장은 구체적인 관계를 전달하고 태그는 학습된 시각 개념을 보조한다.
요청에 묘사할 내용이 충분하면 두 문장 이상을 사용할 수 있지만,
문장 수를 채우려고 없는 사람·옷·배경을 만들지 않는다.
비영어 고유명사는 알려진 영문 표기나 로마자 표기로 표현한다.

## 작성 순서

1. **대상과 수:** 무엇이 몇 개 나오는지 먼저 정한다. 사람 수 태그를 동물 수에 쓰지 않는다.
2. **정체성과 외모:** 요청한 캐릭터, 머리·눈·피부·털 색과 형태를 해당 대상에 연결한다.
3. **의상과 소품:** 누구의 옷인지, 누가 무엇을 들고 있는지 분명히 한다.
4. **행동과 관계:** 주체·행동·대상을 문장으로 쓴다. 위치가 요청되면 좌우·앞뒤도 유지한다.
5. **장소와 시간:** 실내외, 배경, 날씨, 낮·밤 등 요청한 환경을 묘사한다.
6. **구도와 조명:** 요청한 시점·프레이밍·빛만 추가한다.
7. **표현 방식:** 수채화·픽셀 아트 등 지정된 매체나 스타일을 반영한다.
8. **검토:** 요청한 내용이 모두 있는지, 불필요한 추가와 서로 모순되는 태그가 없는지 확인한다.

이 목록은 모든 항목을 채우라는 양식이 아니다. 사용자가 정하지 않은 성별,
표정, 복장, 시점, 스타일, 작가는 자동으로 정하지 않는다.
구체화를 요청한 경우에만 그 범위 안에서 시각적 표현을 확장한다.

## 실용 태그 선택표

아래는 자주 필요한 시각 개념을 표현하는 **선택 예시**다.
학습 데이터의 빈도 순위나 모든 태그의 효과를 측정한 결과는 아니다.
실행 지침에는 이 중 기본 어휘를 넣는다. 나머지는 상세 예시와 검토용이다.
태그가 불확실하면 비슷한 태그를 지어내기보다 평범한 영어 문장으로 설명한다.

| 목적 | 선택 예시 | 주의할 점 |
| --- | --- | --- |
| 사람 수 | `1girl`, `1boy`, `2girls`, `2boys`, `1girl, 1boy` | 성별과 수가 요청에서 분명할 때만 사용한다. 성별을 모르면 문장으로 사람 수를 표현한다. |
| 단일 대상 / 사람 없음 | `solo`, `no humans` | `solo`와 여러 대상을 동시에 쓰지 않는다. `no humans`와 인물 태그를 함께 쓰지 않는다. |
| 머리·눈 | `long hair`, `short hair`, `ponytail`, `silver hair`, `blue eyes` | 여러 인물은 색을 전체 태그로 나열하기보다 각 인물의 문장에 붙인다. |
| 옷·장신구 | `jacket`, `dress`, `uniform`, `glasses`, `scarf` | 요청하지 않은 의상을 기본값으로 넣지 않는다. |
| 자세·행동 | `sitting`, `standing`, `walking`, `sleeping`, `holding cup` | 누구의 동작인지 문장으로 연결한다. 복잡한 행동은 태그만으로 표현하지 않는다. |
| 표정·시선 | `smile`, `expressionless`, `closed eyes`, `looking at viewer` | 미소와 무표정, 감은 눈과 정면 응시 등의 충돌을 제거한다. |
| 프레이밍 | `portrait`, `close-up`, `upper body`, `full body` | 요청한 프레이밍을 선택한다. 서로 다른 프레이밍을 무작정 겹치지 않는다. |
| 시점 | `from side`, `from above`, `from below` | 위치 관계와 시점은 다르다. 대상의 좌우 배치는 문장으로 쓴다. |
| 환경 | `indoors`, `outdoors`, `forest`, `city`, `rain`, `snow` | 같은 장면의 환경이 모순되지 않게 한다. |
| 시간·빛 | `night`, `sunset`, `backlighting` | 요청한 시간과 조명을 유지한다. 밤 요청에 낮 묘사를 남기지 않는다. |
| 매체 | `watercolor`, `oil painting`, `sketch`, `pixel art` | 요청한 매체만 사용한다. 기본적으로 여러 스타일을 섞지 않는다. |

현재 엔진용 태그는 소문자와 공백을 사용한다. `long_hair` 대신 `long hair`처럼 쓴다.
점수 태그의 밑줄은 예외다. 문장과 고유명사는 정상적인 영어 대소문자를 사용한다.
같은 태그를 반복해 대상 수를 표현하지 않는다. 예를 들어 토끼 세 마리는
`rabbit, rabbit, rabbit` 대신 문장에서 `Three rabbits`로 표현한다.
작가 태그는 사용자가 지정했을 때만 `@` 접두사를 붙인다.
등급 태그도 요청했을 때만 넣는다.

품질 태그는 필수가 아니며 필요한 경우 간결하게 사용한다.
`masterpiece`, `best quality`, `8k`, `ultra detailed`를 길게 쌓는 것으로
요청의 구체적인 시각 정보를 대신하지 않는다. 점수 태그를 자동으로 만들지 않고,
Aesthetic 선택 시에는 `score_*`를 제외한다.
강조 구문과 서비스 전용 태그를 임의로 추가하지 않는다.

## 작성 예시

다음은 외부 문서에서 복사하지 않고 Moru의 출력 계약에 맞춰 작성한 예시다.
모든 예시를 매번 LLM에 전달하는 것은 아니다.

### 한 인물과 행동

요청: 은발 소녀가 편의점 앞에서 컵라면을 먹는 장면.

```text
1girl, solo, silver hair, convenience store. A silver-haired girl eats cup noodles in front of a convenience store. She holds the cup of noodles as she eats.
```

요청하지 않은 눈 색, 교복, 미소, 야간 조명을 넣지 않는다.
행동과 소품의 관계는 문장으로 쓴다.

### 동물만 있는 장면

요청: 초록 소파에서 검은 고양이 두 마리가 자고 있어. 사람 없이.

```text
no humans, cat, sleeping, sofa. Two black cats sleep together on a green sofa. Both cats have their eyes closed.
```

고양이 수는 문장으로 표현한다. `2girls`나 `solo`를 붙이지 않는다.

### 서로 다른 두 인물

요청: 왼쪽의 빨간 머리 여자는 흰 코트를 입고, 오른쪽의 검은 머리 남자는 파란 재킷을 입었어. 여자가 남자에게 책을 건네줘.

```text
1girl, 1boy, book. On the left, a red-haired woman wearing a white coat hands a book to the man on the right. The man has black hair and wears a blue jacket.
```

`red hair, black hair, white coat, blue jacket`를 공통 태그로 늘어놓으면
각 속성의 주인이 불분명해진다. 각 인물의 문장에 연결하고 전달 방향을 명시한다.

### 풍경과 지정 매체

요청: 사람 없는 눈 내리는 숲, 픽셀 아트로.

```text
no humans, forest, snow, pixel art. Snow falls through a forest rendered in pixel art.
```

두 문장을 쓰기 위해 동물이나 건물을 추가하지 않는다.
요청이 짧으면 한 문장으로도 충분하다.

### 기존 상태의 일부 변경

기준 프롬프트:

```text
no humans, dog, red scarf, snow, daytime. A brown dog wearing a red scarf stands in the snow during the day.
```

요청: 밤으로 바꾸고 나머지는 유지해줘.

```text
no humans, dog, red scarf, snow, night. A brown dog wearing a red scarf stands in the snow at night.
```

`daytime`과 낮이라는 문장을 모두 교체한다. 갈색 개, 빨간 목도리,
서 있는 동작, 눈 배경은 유지한다. `make it night`라는 편집 지시만 반환하지 않는다.

### 대상을 제거하는 변경

기준은 위의 야간 장면이며, 요청은 “목도리를 없애줘”다.

```text
no humans, dog, snow, night. A brown dog stands in the snow at night.
```

목도리의 태그와 묘사를 함께 제거한다. `red scarf, without a scarf`처럼
상충하는 표현을 남기지 않는다. 원하지 않는 특징을 negative prompt 형식으로
positive prompt 뒤에 나열하지 않는다.

## 대화 컨텍스트와 토큰 예산

- 시스템에는 공통 작성 규칙, 태그 선택표, 작업에 맞는 작성 예시가 들어간다.
- 생성에는 동물·여러 인물 예시, 수정에는 기존 상태 일부 변경 예시를 사용한다.
- 예시를 가상의 user/assistant 대화로 삽입하지 않는다. 실제 이력과 구분한다.
- 현재 이미지의 프롬프트가 기준 상태다. 최근 이력은 “처음 분위기로” 같은 참조를 이해하는 보조 자료다.
- 출력 공간을 먼저 예약하고, 입력이 넘치면 오래된 실제 대화 쌍부터 제거한다.
- 지침, 기준 프롬프트와 최신 요청은 자르지 않는다. 이들만으로도 초과하면 명시적 오류를 표시한다.

기본 2048 컨텍스트와 출력 1024는 입력에 1024토큰을 남긴다.
상세 지침만으로도 이전보다 많은 입력 공간을 사용하므로, 길게 누적된 프롬프트나
여러 턴의 이력이 필요한 경우 컨텍스트를 늘려야 한다.
출력 한도만 올리면 오히려 입력 공간이 줄어든다.
토큰 수는 선택한 LLM의 실제 채팅 템플릿과 tokenizer에 따라 달라진다.
작성 지침의 예시는 출력 형식을 가르치는 자료이며, 작은 LLM의 의미 보존이나
이미지 엔진의 정확한 인물 수·위치 표현을 보장하는 검증 결과는 아니다.

실제 모델의 출력은 일반 단위 테스트와 분리해 검토한다. GPU가 비어 있을 때
`uv run --extra inference python scripts/smoke_prompt_guidance.py`로 동물 수,
여러 인물의 속성·관계, 지정 매체, 일부 변경에 대한 새 샘플을 만들 수 있다.
예시의 고양이·책·목도리를 그대로 재현하는 요청 대신 토끼·우산·소파 색 변경을
사용한다. 결과는 `build/prompt-guidance-samples.json`에 저장하며 실제 사용자
이력이나 이미지 생성은 사용하지 않는다. 이 스크립트의 정상 종료는 출력 형식과
컨텍스트 적합성을 확인한다. 의미 보존과 불필요한 추가 여부는 출력도 직접 읽어 검토한다.
