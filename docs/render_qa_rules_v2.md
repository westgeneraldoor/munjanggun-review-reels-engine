# HTML-to-MP4 Render QA Rules v2

문장군 리뷰 영상은 HTML 프리뷰가 좋아 보여도 MP4 렌더가 다르면 실패입니다.

## 핵심 사고 원인

기존 렌더러는 HTML 프리뷰의 390px 디자인을 그대로 캡처하지 않고, 무대를 1080px로 키운 뒤 다시 레이아웃했습니다.

그 결과:

- 자막 크기 비율이 HTML과 달라짐
- 자막 위치가 예상보다 위/아래로 밀림
- 상품 썸네일과 자막 간격이 달라짐
- HTML 검수가 최종 MP4 품질을 보장하지 못함

## 고정 규칙

1. HTML 프리뷰는 디자인 기준 화면입니다.
2. MP4 렌더는 HTML 레이아웃을 다시 계산하면 안 됩니다.
3. 렌더는 390px 기준 프리뷰를 `deviceScaleFactor`로 고해상도 캡처해야 합니다.
4. 최종 출력은 FFmpeg에서 정확히 `1080x1920`으로 보정합니다.
5. 최종 업로드용 MP4는 직원 편집본 기준에 맞춰 약 `9~10 Mbps` 비트레이트로 렌더합니다.
6. HTML 승인 후에도 MP4 대표 프레임 검수는 필수입니다.

## 최종 렌더 스펙

검수용 프리뷰와 최종 업로드용은 구분합니다.

```text
검수용: 720x1280 / 12fps 또는 30fps / 2~3 Mbps
최종 업로드용: 1080x1920 / 30fps / video 11000k / audio AAC 44.1kHz stereo 192k
```

`render_html_preview_v2.js`의 기본 최종 비트레이트는 아래 값입니다.

```text
--video-bitrate 11000k
--maxrate 12000k
--bufsize 24000k
--audio-bitrate 192k
--audio-sample-rate 44100
--audio-channels 2
```

## 렌더 전 필수 검수

렌더 전:

```text
STATUS.md의 mp4_allowed가 true인지 확인
APPROVAL_LOG.md에 HTML 승인 범위가 기록되어 있는지 확인
video_engine_v2.reels_qa preflight가 OK인지 확인
사용자 기획 승인 없이 생성된 HTML이면 렌더 금지
HTML에서 자막 위치/크기/가림 확인
`docs/reels_privacy_asset_qa_rules_v1.md` 기준 privacy_review 또는 privacy_sanitization_report 확인
voice.mp3 실제 길이 확인
공백 제외 내레이션 글자수 / 음성 길이 확인
초당 9.0자 이상이면 렌더 금지
원본 TTS 길이 / 최종 voice.mp3 길이 압축률 확인
압축률 1.20 이상이면 렌더 금지
기존 승인 톤과 다른 목소리이거나 발음이 뭉개지면 렌더 금지
자막이 의미 단위 1~2줄로 보이는지 확인
조사나 단어 조각이 단독 줄로 떨어지면 렌더 금지
모든 scene/beat의 asset + caption + narration 의미 일치 확인
의미가 한 칸이라도 밀려 있으면 렌더 금지
주소/건물명/가족사진/얼굴/차량번호가 보이면 렌더 금지
```

HTML 생성 전/렌더 전 공통 QA 명령:

```powershell
python -m video_engine_v2.reels_qa `
  --planning "<planning_recipe.json>" `
  --edit "<edit_recipe.json>" `
  --sync-manifest-out "<sync_manifest.json>"
```

`[FAIL]`이 하나라도 있으면 MP4 렌더를 진행하지 않습니다.

`sync_manifest.json`은 MP4 렌더 전 보관해야 하는 검증 증거입니다.
이 파일이 없거나, `ok: false`이면 렌더를 진행하지 않습니다.
특히 audio 블록의 `total_voice_cps`를 확인합니다.

```text
total_voice_cps = 전체 narration_ref 공백 제외 글자수 / final_voice_duration_sec
```

장면별 CPS가 낮아 보여도 `total_voice_cps`가 9.0 이상이면 실패입니다.
`render_duration_sec`는 영상 타임라인 길이이며, 실제 `voice.mp3` 길이 검증값으로 인정하지 않습니다.

렌더 후:

```text
대표 프레임 3~5장 추출
자막 크기 확인
자막 위치 확인
상품/리뷰 캡처 가림 확인
음성-자막-화면 싱크 확인
```

렌더 후 자동 증거 생성:

```powershell
node scripts/render-post-qa.mjs `
  --mp4 "<output review package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4" `
  --package "<output review package>" `
  --sync-manifest "<output review package>/sync_manifest.json"
```

이 스크립트는 아래를 자동으로 검사하고 기록합니다.

```text
MP4가 패키지 폴더 안에 있는지
파일명이 upload_10mbps 규칙을 따르는지
sync_manifest.ok / total_voice_cps / meaning_match evidence가 유효한지
final_voice_duration_sec가 있고 MP4 길이와 ±2초 이내인지
ffprobe 기준 1080x1920 / 30fps / H.264 / yuv420p / AAC 44.1kHz stereo인지
대표 프레임 5장을 _work/render_post_qa_*/representative_frames/ 아래 추출했는지
```

자동 검사 통과는 최종 승인이 아닙니다.
리포트는 반드시 아래 상태로 남아야 합니다.

```text
overall_status: manual_review_required
manual_review.status: pending
```

총괄 PD가 대표 프레임을 열어 개인정보, 자막 크기/위치, 상품/리뷰 가림, 음성-자막-화면 싱크를 확인한 뒤에만 최종 완료로 봅니다.

## 장면 의미 일치 기준

렌더 전에는 JSON 구조와 화면을 모두 확인합니다.

```text
asset이 Before이면 caption/narration도 Before 맥락이어야 합니다.
asset이 제품/댐퍼이면 caption/narration도 제품/댐퍼를 말해야 합니다.
asset이 리뷰캡처이면 caption/narration도 같은 리뷰 증거를 말해야 합니다.
```

아래처럼 자막과 내레이션이 서로 다른 소재를 말하면 실패입니다.

```text
caption: 브론즈 유리라 답답함보다 은은함
narration: 3연동 문은 부드럽고 댐퍼 덕분에 조용했다
```

음성 길이와 초당 글자수가 통과해도, 의미 일치가 깨지면 MP4 렌더를 진행하지 않습니다.

## 음성 속도 기준

문장군 TTS 기준은 DECISION_LOG D-017을 따릅니다.

```text
레퍼런스: 공백 제외 244자 / 35.02초 / 약 6.97자/초
권장 범위: 6.5~7.5자/초
허용 범위: 5.0~8.5자/초
실패 기준: 9.0자/초 이상
```

`voice.mp3` 길이가 타임라인과 맞아도, 초당 글자수가 높으면 실패입니다.
이 경우 HTML 프리뷰 단계에서 멈추고 내레이션 길이 또는 음성 생성 방식을 수정합니다.

## 음성 압축률/목소리 품질 기준

최종 `voice.mp3`가 타임라인에 맞아도, 원본 TTS를 과하게 압축하면 발음이 뭉개집니다.

```text
압축률 = 원본 TTS 길이 / 최종 voice.mp3 길이
권장: 1.00~1.12
주의: 1.13~1.18
실패: 1.20 이상
렌더 금지: 1.25 이상
```

025 living_review_v2 실패 사례:

```text
원본 TTS: 39.49초
최종 음성: 28.94초
압축률: 1.36배
판정: 실패. 발음 뭉개짐 위험.
```

또한 음성 톤은 기존 문장군 승인 음성과 비교합니다.
지나치게 차분한 여성 낭독, 낮게 처지는 톤, 받침/조사 뭉개짐은 수치와 무관하게 실패입니다.

## 대표 프레임 기준

최소 아래 타이밍을 확인합니다.

```text
0.5s  - 첫 후킹
3~5s  - 문제 제시
중반   - 제품/실측/전환
후반   - 리뷰 증명
마지막 - CTA
```

각 대표 프레임에서는 자막/싱크뿐 아니라 개인정보 위험도 함께 확인합니다.

```text
주소/건물명/동호수 표식이 읽히는가?
가족사진이나 얼굴이 보이는가?
유리/거울 반사에 얼굴이 남아 있는가?
차량번호/송장/전화번호가 보이는가?
리뷰 캡처에 과도한 개인정보가 보이는가?
```

## 파일명 규칙

새 렌더러 기준으로 다시 만든 최종본은 기존 파일을 덮어쓰지 않습니다.

```text
*_final_render_YYYYMMDD_scale_lock.mp4
*_final_render_YYYYMMDD_upload_10mbps.mp4
```

기존 문제 렌더는 `_work/`로 이동하거나 비교용으로 보관합니다.

## 절대 금지

- 여러 영상을 한 번에 최종 렌더하지 않기
- HTML만 보고 MP4 최종 승인하지 않기
- 1080px 무대 기준으로 HTML 레이아웃을 다시 계산하지 않기
- 자막 대표 프레임 확인 없이 사용자에게 “완료”라고 말하지 않기
- privacy 대표 프레임 확인 없이 사용자에게 “완료”라고 말하지 않기
