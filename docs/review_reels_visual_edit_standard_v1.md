# 리뷰 릴스 비주얼·편집 표준 v1

## 훅과 사람 검수 증거 (2026-08-14)

HTML QA는 전체 beat 대표 프레임과 별도로 0.5초 및 첫 3개 훅 shot의 중간 시점을 캡처합니다. 첫 화면 한 장만 보고 훅을 통과시키지 않습니다. 작업자는 훅 순서, 의미 싱크, 자막 배치, 개인정보, 리뷰 캡처, CTA를 직접 본 뒤 `html-review-record`로 현재 HTML·artifact evidence·QA report·모든 QA frame의 해시 영수증을 남깁니다. 이 영수증이 없거나 stale이면 MP4 렌더 게이트를 통과하지 못합니다.

one-shot 음성은 preflight 전에 실제로 청취해 발음, 톤, 자막 싱크를 확인하고 `voice-review-record` 영수증을 남깁니다. 파일 존재나 TTS 생성 보고서만으로 청취 완료를 추정하지 않습니다.

이 문서는 production v2의 화면, 자막, 모션, 전환, 오디오 편집 기준입니다.
실험용 HyperFrames 규칙은 이 문서를 바꾸지 않으며 production 승격 전 별도 승인이
필요합니다.

## 1. 편집의 기준 단위

편집 단위는 효과가 아니라 의미입니다. 각 beat에서 사진·자막·음성이 같은 순간에
같은 이야기를 해야 합니다. 화면이나 자막이 음성보다 결론을 먼저 말하면 실패입니다.

기본 구성은 20~28초, 7~8개 major beat 또는 9~12개 micro moment입니다. 자막 한 덩어리를
곧바로 한 장면으로 간주하지 않고, 같은 문장 안에서도 원인·전환·결과처럼 의미가 갈리며
각 구절에 맞는 사진 근거가 있으면 별도 shot으로 나눕니다.

narrative-safe 비리뷰 사진이 8장 이상이면 비리뷰 사진 shot 9~12개를 목표로 합니다.
9개 미만이면 `SCENE_DENSITY_LOW` 경고를 내지만 하드 실패시키지 않습니다. 근거 사진이
부족하거나 같은 의미를 반복하게 되는 경우에는 억지로 컷을 채우지 않습니다.

리뷰 캡처를 제외한 사진 shot이 8개 이상이고 narrative-safe 자산이 충분한데도 같은
몇 장만 반복하면 `PHOTO_VARIETY_LOW` 경고를 냅니다. 목표 고유 사진 수는 전체 사진
shot의 절반을 올림한 값이며 최대 6장, 사용 가능한 근거 자산 수를 넘지 않습니다.
이 경고를 없애려고 원문과 무관하거나 제품이 거의 보이지 않는 사진을 억지로 넣지 않습니다.

### D-026 장면 의미 일치 하드 게이트

HTML 또는 MP4 전 모든 scene/beat의 `asset + caption + narration`이 같은 의미를
말하는지 검수합니다. edit recipe의 모든 beat는 `meaning_match: true`와 비어 있지 않은
`meaning_match_source` 또는 `meaning_match_evidence`를 가져야 합니다. 하나라도 빠지거나
일치하지 않으면 실패합니다.

- 실패: asset/caption은 시공 전인데 narration은 설치 후 변화를 말함
- 실패: caption은 브론즈 유리인데 narration은 3연동·댐퍼를 말함
- 실패: caption은 제품 구조인데 narration은 원문에 없는 차단 효과를 말함

의미뿐 아니라 시작 시점도 맞아야 합니다. caption은 narration보다 먼저 시작하지 않고,
visual은 narration보다 0.05초를 초과해 먼저 시작하지 않습니다. 자동 검사는 선언과
타이밍을 확인하지만 실제 의미의 타당성은 대표 프레임과 원문을 대조해 직접 검수합니다.

## 2. 화면 위계

- 고정 브랜드 배지와 의미 없는 좌상단 라벨을 두지 않습니다.
- 첫 화면 훅은 주어·상황·변화를 유지한 큰 자막으로 1초 안에 읽혀야 합니다.
- 제품 설치 결과가 핵심 보상인 리뷰는 첫 3컷을 `완성 결과 → 이전 상태 → 완성 결과`로 구성합니다. 세 컷은 각각 1.0초 이상 보여주고 마지막 CTA도 완성 결과를 최소 2.5초 유지합니다.
- 첫 3컷의 사진 경계는 자막 chunk 경계와 독립적입니다. 대상·상황·변화를 보존한 한
  완결 문장이 세 사진을 가로지를 수 있습니다. 첫 3컷뿐 아니라 모든 shot의
  `meaning_match_source`는 해당
  `asset_evidence`와 실제 `narration_fragment`를 함께 결속하고, 시공 전 화면에 설치 후
  결과처럼 의미가 반대인 발화를 얹으면 실패합니다.
- `before_state` shot은 자신이 결속한 `narration_fragment`의 자막 문맥이 끝난 뒤
  0.15초를 넘겨 다음 설치 결과 문구까지 남아 있을 수 없습니다. 이 제한은 의미가
  반대인 화면 누수를 막는 것이며 첫 3컷 전체를 자막 chunk 경계에 맞추는 규칙이 아닙니다.
- 자막은 짧고 크게, 한 화면 한 생각을 원칙으로 합니다.
- 실제 사진을 계속 어둡게 하거나 흐리게 처리하지 않습니다.
- 공간 동선, 제품 선택, 실측, 공정 장면은 실제 근거와 asset이 있을 때만 사용합니다.
- 제품 썸네일은 근거 있는 선택 장면에서만 쓰고 자막으로 제품을 가리지 않습니다.
- 리뷰 캡처는 증거로 식별되고 원문 인용이 실제로 읽혀야 합니다.
- 리뷰 캡처 카드는 하단 자막 안전영역 위에 배치해 자막이 원문 본문이나 밑줄 인용을 덮지 않게 합니다.

효과 강도는 `hook -> problem -> process/result -> review proof -> CTA`의 의미를
돕는 범위에서만 조절합니다. proof와 CTA를 화려한 효과로 덮지 않습니다.

## 3. 자막과 강조

- 한 화면 1~2줄, 줄마다 하나의 의미를 둡니다.
- 1080x1920 기준 자막 안전 영역은 `y=220~1470`입니다. 상단 220px과 하단
  450px은 플랫폼 UI 데드존으로 보고 훅·본문·CTA 자막을 넣지 않습니다.
- production one-shot의 각 beat는 음성 전문을 빠짐없이 덮는 1~4개의
  `caption_chunks`를 사용합니다. 최대 4개이며, 둘 이상으로 나눌 때 각 chunk는
  공백·문장부호를 제외하고 최소 7자를 가져 문맥이 보이게 합니다.
- chunk 시간은 beat 전체를 빈틈·겹침 없이 연속으로 덮고, 최종 음성의 실제 문장
  경계에 맞춥니다. 끝난 문장 뒤에 다음 문장 조각을 붙이지 않으며 글자 수 비례 추정만으로
  자막을 쪼개지 않습니다.
- 공식 one-shot TTS는 측정된 최종 음성 길이에 edit의 모든 beat·shot·caption chunk를
  한 번에 재결속하고, 같은 `caption_timeline`으로 SRT를 생성합니다. SRT와 HTML recipe가
  서로 다른 시간표를 쓰면 `VOICE_CAPTION_TIMELINE_STALE`로 실패합니다.
- 신규 기획은 retime 편차를 흡수하도록 첫 훅 3.5초 이하, 리뷰 캡처 5.4초 이하,
  마지막 완성 결과 3.0초 이상으로 작성합니다. production 하드 한계는 기존
  4.0초/6.0초/2.5초를 유지합니다.
- 공식 생성기는 0.25초를 넘는 시작 무음만 0.15초로 줄이고 새 voice hash와 길이를
  보고서에 결속합니다. 무음 교정은 Gemini 재호출 사유가 아닙니다.
- 최종 음성 retime과 실측 alignment calibration은 새 edit을 쓰거나 잠그기 전에
  duration-sensitive 계약을 다시 검사합니다. 실패한 recipe는 current artifact가 될 수 없습니다.
- `VOICE_CAPTION_TIMELINE_STALE`은 무조건 재생성 지시가 아닙니다. narration과 전체
  caption timeline이 같으면 immutable revision을 fork하고 기존 voice/SRT/report를
  재사용합니다. caption chunk나 timing이 바뀌었을 때만 실측 alignment 기반 calibration을
  사용하고, narration hash가 바뀐 경우에만 새 TTS를 생성합니다.
- Gemini TTS 보고서는 구간별 단어·문장 타임스탬프가 아니라 최종 음성의 총 길이만
  제공합니다. 따라서 위 재결속은 계획 시간을 총 길이에 선형 비례시켜 SRT와 HTML의
  시계만 일치시키며, 구간 내부의 실제 발화 시작·끝까지 자동 보장하지 않습니다. 작업자는
  실제 음성을 들으며 모든 자막 구간을 확인하고 `voice-review-record`의
  `caption_sync_approved`를 반드시 기록해야 합니다.
- 명시한 줄바꿈과 자동 줄바꿈을 합쳐 실제 화면이 3줄 이상이면 실패합니다. 문맥을
  다시 잘게 쪼개지 않고 한 화면 1~2줄을 유지하되, 장면이 뒤로 갈수록 글자를 줄이지 않습니다.
- 공식 HTML 전 `produce_review_v2.py layout-check`로 실제 production 템플릿의 모든
  caption chunk를 무산출 측정합니다. 이 검사는 3줄, 안전영역 이탈, DOM overflow를
  선제 차단하지만 대표 프레임 직접 검수를 대체하지 않습니다.
- 핵심 피사체, 얼굴, 제품 디테일, 리뷰 인용을 가리지 않습니다.
- production one-shot의 키워드 강조는 beat당 정확히 1개입니다. 키워드 크기는 본문과 동일하며 색으로만 위계를 줍니다.
- 핵심어 pop은 chunk 시작의 고정 지연값으로 실행하지 않습니다. `caption_accent.start_sec`를
  **강조 단어의 실제 발화 예상 시점**에 결속하며, 해당 단어 위치를 글자 수로 산정한 시점보다
  0.20초 이상 먼저 튀면 실패합니다. pop은 420ms 동안 한 번만 올라왔다가 제자리로 돌아옵니다.
- pop 진행률은 브라우저 실제 시간이 아니라 영상 시간으로 계산합니다. HTML 재생·스크럽·
  MP4 프레임 캡처가 같은 시각에 같은 포인트 위치를 보여야 합니다.
- production one-shot은 첫 훅만 `hero-calm 58px`, 이후 **본문은 `medium 46px`**로 고정합니다. proof·CTA를 포함해 뒤로 갈수록 `small`로 축소하지 않습니다.
- 음성 발음을 위해 `삼 연동 중문`처럼 적어야 해도 화면의 공식 제품명은 chunk의
  `display_text`로 `초슬림 3연동중문`처럼 표시합니다. 숫자 표기와 띄어쓰기 외 의미 변경은 실패합니다.
- 단어 강조마다 SFX를 붙이지 않습니다.
- 색상은 의미와 대비를 위해 쓰며 경고색·글로우·플래시를 장식으로 남발하지 않습니다.
- `white` 자막 테마는 아이보리 화이트 본문과 민트 핵심어를 사용하며 두꺼운 노란색을 기본값으로 강제하지 않습니다.
- 리뷰 증거 강조는 실제 원문 인용에만 2px 이하 밑줄을 겹쳐 표시합니다. review scene 시작
  0.10초 안에 시작하고 `draw_duration_sec` **0.20초 안에** 다 그어진 뒤 유지합니다. 선은 다음
  줄을 침범하지 않고 원본 캡처를 수정·재구성하지 않습니다.

## 4. 사진 모션과 전환

- production one-shot의 모든 beat는 실제 렌더 순서를 `shots`로 기록합니다. 허용 모션은 `static_hold`, `calm_push_in`, `calm_pull_out`, `calm_glide_left`, `calm_glide_right`, `calm_glide_up`, `review_capture_hold`뿐이며 비정지 모션은 `motion_reason`이 필요합니다.
- `calm_push_in`·`calm_pull_out`의 시작과 끝 scale 차이 0.05, 좌우 glide는 좌우 총 24px, 상하 glide는 상하 총 20px입니다. 회전·흔들림·플래시·blur·glow를 함께 넣지 않습니다.
- 한 beat 안의 여러 shot은 모두 같은 모션을 사용해 카메라를 한 방향으로 유지합니다.
  calm 모션은 shot 안에서 일정 속도로 진행하고 시작·끝에서 멈췄다가 급가속하지 않습니다.
- `calm_dissolve`는 380ms 동안 투명도만 전환합니다. 이전 사진은 마지막 카메라 위치를
  유지하며 dissolve가 별도의 확대·축소·이동 transform을 덮어쓰지 않습니다.
- `calm_slide`는 420ms 동안 새 사진을 한 방향으로 reveal하며 전체 영상에서 최대 2회만
  사용합니다. `soft_page_turn`은 440ms의 얕은 대각 reveal로 이야기의 핵심 전환에 최대
  1회만 사용합니다. 두 효과 모두 사진의 기존 calm transform을 덮어쓰지 않습니다.
- 과도한 확대, 얼굴·문틀·제품을 잘라내는 crop, 이유 없는 좌우 흔들림을 금지합니다.
- 20~28초 one-shot은 전체 12컷을 넘기지 않습니다. 사진이 충분하면 9~12개 micro
  moment를 목표로 하되 컷 수보다 완성 결과와 증거의 체류 시간을 우선합니다.
- 허용 전환은 `cut`, `calm_dissolve`, `calm_slide`, `soft_page_turn`입니다. 첫 3컷은
  `cut → calm_dissolve → calm_dissolve`를 유지하고 그 뒤의 hard cut은 금지합니다.
  `calm_slide`는 최대 2회, `soft_page_turn`은 최대 1회이며 나머지는
  `calm_dissolve 380ms`를 사용합니다.
- 리뷰 증거와 CTA는 `calm_dissolve`만 사용합니다. 페이지·슬라이드 효과로 읽는 화면을
  덮지 않습니다.
- 리뷰 증거는 한 장의 `review_capture_hold` 정지 화면으로 유지해 읽는 동안 움직이지 않습니다.
- 랜덤 전환, 플래시, 과한 blur/glow는 금지합니다.
- 첫 화면, 리뷰 증거, CTA의 가독성이 모션보다 우선합니다.

## 5. 오디오

- 내레이션이 master timeline입니다. 사진·자막·전환은 음성 의미 단위에 결속합니다.
- BGM과 SFX는 사용권이 확인된 소스만 사용합니다.
- BGM은 내레이션을 가리지 않도록 ducking하고, SFX는 실제 전환이나 사건을 설명할 때만 씁니다.
- draft loudness 기준은 약 -16 LUFS, true peak는 -1 dBTP 이하를 목표로 하되 최종
  판정은 `docs/render_qa_rules_v2.md`와 실제 측정값을 따릅니다.
- 공식 음성과 속도 기준은 `docs/review_reels_content_standard_v1.md`를 따릅니다.

## 6. 생성 이미지와 주장

생성 이미지는 생활 불편이나 보이지 않는 상황을 짧게 설명하는 보조 인서트만
가능합니다. recipe에 `generated_asset`, `generated_reason`, `not_real_proof`,
`visual_claim`, `literal_qa_result`를 남기고 실제 시공 증거처럼 보이게 만들지 않습니다.

화면 문구도 원문 결속을 따릅니다. 근거 없는 `완벽`, `100%`, `보장`, `무조건`,
`완벽 차단`과 원문에 없는 수치·감정·효과는 금지합니다.

## 7. QA

HTML은 1080x1920, 30fps production 설정과 동일한 레이아웃을 사용합니다. 공식 HTML
생성 후 모든 beat의 대표 프레임을 자동 캡처하고 작업자가 직접 확인합니다.
공식 HTML QA는 각 자막 chunk의 중간 시점에서 실제 DOM 위치와 실제 줄 수를 측정하고
`y=220~1470`을 벗어나거나 3줄 이상이면 실패합니다. 핵심어에는 유효한 절대
`caption_accent.start_sec`가 있어야 하고 pop 길이가 420ms와 다르면
`CAPTION_ACCENT_TIMING_INVALID`로 실패합니다. 계약 QA는 이 시각이 해당 chunk 안의
강조 단어 발화 예상 시점보다 0.20초 이상 빠르거나 0.45초 이상 늦으면 실패합니다.

검수 항목:

1. 첫 화면이 완성 결과를 먼저 보여주고 이전 상태와의 차이를 즉시 증명하는가
2. 모든 beat가 D-026의 `meaning_match: true`와 근거를 가지며 사진·자막·음성이 같은 의미인가
3. 자막이 `y=220~1470` 안에 있고, 문맥을 유지하며, 피사체와 리뷰 증거를 가리지 않는가
4. 개인정보와 생성 이미지 표시가 안전한가
5. 자막 줄바꿈, 대비, crop, 전환이 모바일에서 읽히는가
6. 최종 MP4가 `docs/render_qa_rules_v2.md`의 codec·해상도·오디오·대표 프레임 QA를 통과하는가

내부 builder나 renderer를 직접 실행하지 않고 `scripts/produce_review_v2.py`만 사용합니다.

## 리뷰 밑줄 정렬 계약

엔진은 리뷰 캡처 이미지를 읽지 못하므로 `top_pct`가 옳은 줄인지 스스로 알 수 없습니다.
좌표를 눈대중으로 찍으면 엉뚱한 줄에 밑줄이 그어진 채 자동 QA를 전부 통과합니다.

- 캡처에서 인용문이 **실제로 몇 줄에 걸치는지 보고 그 줄 수만큼** segment를 만든다.
- segment마다 그 줄이 덮는 조각을 `line_text`에 적는다.
  모두 이으면 `review_emphasis.quote`와 정확히 같아야 한다.
- segment는 위에서 아래로, 한 줄 높이씩 내려간다. 같은 `top_pct`를 두 번 쓰거나
  거슬러 올라가면 실패한다.
- 좌표가 그 줄 위에 실제로 놓였는지는 대표 프레임을 본 사람만 확인할 수 있으므로
  `--check review_underline_alignment_reviewed`가 HTML 검수 영수증에 필수다.

### 밑줄 좌표 픽셀 검증 (2026-08-19)

게이트가 캡처의 행별 잉크 밀도로 글자 줄 위치를 찾아 `top_pct`를 대조한다.

- 글자 띠 안을 지나면 `REVIEW_UNDERLINE_CROSSES_TEXT`. 밑줄은 글자 아래 여백에 둔다.
- 위에 글자가 없는 빈 자리면 `REVIEW_UNDERLINE_NOT_UNDER_TEXT`.
- 줄을 건너뛰거나 거슬러 올라가면 `REVIEW_UNDERLINE_LINES_NOT_CONSECUTIVE`.

어떤 글자를 덮는지까지는 판정하지 않는다. 그것은 `line_text` 계약과
`--check review_underline_alignment_reviewed` 사람 검수가 맡는다.

