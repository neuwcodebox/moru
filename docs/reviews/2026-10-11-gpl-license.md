# GPL 라이선스 설정

- [LICENSE](../../LICENSE)는 제공된 GPL 템플릿의 프로젝트 설명·연도·저작자·프로그램명
  placeholder만 채웠다. 프로젝트 정보는 `Moru`, `2026 Neuwcodebox`이며 별도 문구를 추가하지 않았다.
  템플릿의 버전 허용 문구에 맞춰 `GPL-3.0-or-later`를 적용했다.
- Python·프론트엔드 패키지와 npm 잠금 파일, 영문·한글 README를 함께 갱신했다.
  `uv lock --check --offline`가 통과해 `uv.lock` 변경은 필요하지 않았다.
  README는 앱 라이선스와 외부 라이브러리·모델의 별도 라이선스만 두 문장으로 안내한다.
  문구 수정은 양 언어의 의미와 LICENSE 링크를 확인했으며 별도 자동 테스트는 추가하지 않았다.
- 배포본에는 소스 ZIP 대신 빌드 커밋·고정 ComfyUI revision의 GitHub 다운로드 링크를
  `SOURCE.txt`로 제공하며, 같은 안내를 7z 옆에도 저장한다. 규칙은
  [SPEC](../SPEC.md#18-라이선스와-소스-배포)과 [TECH](../TECH.md#라이선스와-배포-소스)에 기록했다.
  공개 링크와 커밋되지 않은 입력의 불일치·필수 배포 파일 누락을 테스트하며,
  의존성·모델의 원래 라이선스를 유지한다.
- 검증: Python 전체 616개, 프론트엔드 180개 테스트, Ruff 전체 검사, TypeScript 검사,
  Vite 빌드, wheel의 GPL 메타데이터·LICENSE 포함 확인이 통과했다.
- 환경의 기존 임시 폴더·캐시 쓰기 권한 때문에 Python 검증은 캐시를 끄고 새 `--basetemp`로,
  프론트엔드 테스트는 `--no-cache --configLoader runner`로 실행했다. 타입 검사와 빌드는
  프로젝트의 `npm run check`·`npm run build`로 통과했으며 검사 조건은 완화하지 않았다.
- 포터블 UI smoke는 입력 위치 대신 필드 이름으로 항목을 찾고 닫기 버튼으로 저장하도록
  수정했다. 추가된 프롬프트 설정의 기본값과 수정하지 않은 값의 보존도 검사한다.
  재빌드한 Windows 실행 파일에서 기본값·설정 저장·클립보드 복사 검사가 통과했다.
  WebView2와 Windows 클립보드가 필요한 회귀 검증은 이 포터블 통합 검사로 수행했으며,
  설정 저장 동작의 기존 프론트엔드 테스트도 통과했다. GPU smoke는 수행하지 않았다.
