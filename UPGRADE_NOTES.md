# LifePass AI MVP+ 변경 요약

## 해결한 오류

스크린샷의 오류는 `StreamlitValueAboveMaxError`입니다.

```text
The value 5000000 is greater than the max_value 3000000.
```

자연어 파싱 또는 기존 세션 상태에서 `profile.rent`가 5,000,000원으로 들어왔는데, 기존 코드의 월세 입력 위젯은 `st.number_input("월세", 0, 3000000, int(profile.rent))`처럼 최대값이 3,000,000원으로 고정되어 있었습니다. Streamlit은 `value > max_value`인 위젯을 렌더링하지 못하므로 앱이 중단되었습니다.

## 핵심 수정 파일

- `app.py`
  - `safe_number_input()` 추가
  - 전체 number input 범위 안정화
  - JSON 업로드/다운로드 추가
  - 인사이트 탭 추가
  - 녹색 CSS 테마 추가
  - 모든 dataframe에 안정적 key 부여

- `core/validation.py`
  - `validate_profile()` 추가
  - `safe_widget_bounds()` 추가
  - 입력값 hard limit/soft warning 분리

- `core/profile_parser.py`
  - 단위 생략 금액 표현 개선
  - 파싱 후 validation 적용

- `core/insights.py`
  - 상담 우선도 점수
  - 권장 액션
  - 서류 체크리스트 생성

- `tests/verify_mvp.py`
  - 파싱/검증/인사이트 회귀 테스트 추가

## 시연에서 새로 강조할 수 있는 포인트

1. 자연어 상담 문장에서 구조화 프로필 자동 생성
2. 파싱값이 이상해도 앱이 죽지 않고 경고로 안내
3. 현재 자격 판정뿐 아니라 1~3개월 내 혜택 상실 위험 예측
4. 복지 절벽 위험을 상담 우선도 점수로 요약
5. 추천 혜택별 필요 서류를 자동 통합
6. JSON 업로드/다운로드로 외부 시스템 연동 가능성 제시
7. 밝은 녹색 UX로 공공·복지 서비스 이미지 강화
