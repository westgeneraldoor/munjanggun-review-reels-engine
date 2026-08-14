# HTML-to-MP4 Render QA Rules v2

## 역할 기반 대표 프레임과 최종 완료 상태 (2026-08-14)

렌더 대표 프레임은 영상 길이의 고정 비율로 뽑지 않습니다. `sync_manifest.gate_inputs.edit_path`의 현재 edit recipe가 `edit_sha256`과 일치하는지 먼저 확인한 뒤 `event`, `problem`, 중간 전환, `review_proof`, `cta` 역할의 중간 시점을 사용합니다. 따라서 리뷰 증거 프레임이 CTA로 밀려나는 것을 허용하지 않습니다.

`render_complete`는 현재 MP4와 sync manifest가 자동 post-render QA 보고서에 해시 결속된 기술 완료입니다. 총괄 PD가 현재 MP4·현재 post-QA report·모든 대표 프레임을 직접 검수하고 `render-review-record` 영수증을 남겨야 `qa_reviewed: true`가 됩니다. 둘이 같은 MP4에 대해 모두 참일 때만 `final_delivery_complete: true`이며, 그전에는 사용자에게 최종 완성으로 보고하지 않습니다.

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

v2 production의 preflight/HTML/render는 `scripts/produce_review_v2.py`만 사용합니다.
내부 `render_html_preview_v2.js`는 gate receipt 없이는 실행할 수 없으며,
기존 MP4나 frame directory를 삭제하거나 덮어쓰지 않습니다.

HTML/render gate receipt는 한 번만 사용할 수 있습니다. artifact 생성 직전
`_work/production_gates/consumed/<receipt-sha256>.json`이 원자적으로 생성되며,
같은 receipt 또는 동일 내용의 복사본은 거부됩니다. receipt와 consumed marker는
승인·생성 이력이므로 cleanup 대상이 아닙니다.

## 장시간 렌더 작업 계약

에이전트가 실행하는 production MP4 렌더는 호출 도구의 고정 대기시간에 의존하지
않습니다. 공식 `render-start`가 승인·dependency·출력 경로를 검증하고 독립된 렌더
작업을 시작하며, 즉시 작업 ID와 상태 파일 경로를 반환합니다. `render-status`는 같은
작업의 상태와 `rendered_frames / expected_frames` 진행률을 읽습니다.

작업 상태는 `queued -> running -> succeeded|failed`만 허용합니다. 상태 기록은 package
아래 `_work/render_jobs/<job-id>/render_job.json`에 두며 package identity, HTML·artifact
evidence·HTML approval·sync·privacy SHA-256, 출력 상대경로, preset, PID, 시작·종료 시각,
로그 경로와 실패 사유를 결속합니다. 상태 파일과 로그는 production evidence이므로
cleanup 대상이 아닙니다.

호출 세션이나 터미널이 먼저 끝나도 독립 렌더 작업은 계속되어야 합니다. 진행률 정체,
프로세스 종료 또는 non-zero exit는 `failed`로 기록하고 성공으로 보고하지 않습니다.
부분 frame directory와 단회용 receipt는 자동 삭제·재사용하지 않으며, 재시도는 새
작업 ID·새 receipt·새 출력 파일명으로만 허용합니다. 첫 버전은 중단 프레임 resume를
지원하지 않습니다. 같은 출력명의 부분 frame이 남아 있으면
`RETRY_REQUIRES_NEW_OUTPUT`으로 시작 단계에서 차단합니다.

`render-status`가 `succeeded`이고 현재 MP4의 bytes/SHA-256을 기록한 뒤에만
`render-post-qa.mjs`로 넘어갑니다. 기존 동기식 `render`는 compatibility-only 로컬
진단 경로로
남기되, 에이전트 production 운영의 표준 진입점으로 사용하지 않습니다.

```powershell
python scripts/produce_review_v2.py render-start --package "<output review package>" --html "<html_preview>/index.html" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --out "<output review package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4"
python scripts/produce_review_v2.py render-status --package "<output review package>" --job-id "<job-id>"
```

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

## 개인정보 증거 바인딩

v2 production의 `privacy_asset_manifest.json`은 단순 체크 표시가 아니라
렌더 직전까지 검증되는 증거 계약입니다.

```text
checked: true
checked_at: 비어 있지 않은 시각
sanitization_report: package 내부의 실제 보고서 경로
unresolved_risks: []
selected_assets: edit_recipe.asset_roles와 정확히 같은 asset 집합
  - relative_path: package 기준 경로
  - bytes: 검수 시점 바이트 수
  - sha256: 검수 시점 SHA-256
```

선택 asset의 내용, asset 집합, privacy manifest가 바뀌면 기존
`sync_manifest.json`은 stale입니다. `produce_review_v2.py preflight`부터 다시
통과해야 하며, HTML/MP4 단계에는 이를 무시하는 옵션이 없습니다.

## HTML 승인 dependency 결속

`html_artifact_evidence.json`은 HTML 본문 hash만 보관하지 않습니다. renderer가
실제로 쓰는 모든 image asset, `voice.mp3`, repository 내부 engine font를 아래처럼
기록합니다.

```text
kind / scope / relative_path / bytes / sha256
```

image·voice는 package 내부여야 하고 font는 repository 내부 허용 경로여야 합니다.
상대경로 탈출, 절대경로, symlink 우회, 누락·중복 dependency는 실패입니다. 생성된 HTML의
asset URL과 edit recipe의 사용 집합도 evidence와 정확히 같아야 합니다. HTML 승인 파일은
artifact evidence SHA-256을 통해 이 전체 목록에 결속됩니다.

`sync_manifest.json`의 `gate_inputs.voice`는 voice 상대경로/bytes/SHA-256을 별도로
보관합니다. 따라서 같은 크기의 다른 voice로 바꿔도 sync가 stale이며, Python gate와
Node renderer는 frame directory를 만들기 전에 현재 image/voice/font hash를 다시
검증합니다.

## 렌더 전 필수 검수

렌더 전:

```text
STATUS.md의 mp4_allowed가 true인지 확인
APPROVAL_LOG.md에 HTML 승인 범위가 기록되어 있는지 확인
`scripts/produce_review_v2.py preflight`와 HTML artifact evidence가 유효한지 확인
`HTML_APPROVAL.json`의 package/path/SHA-256이 현재 HTML과 정확히 같은지 확인
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
자막의 실제 DOM 좌표가 1080x1920 기준 y=220~1470을 벗어나면 렌더 금지
자막의 명시·자동 줄바꿈을 합친 실제 DOM 줄 수가 3줄 이상이면 렌더 금지
one-shot 자막이 beat당 최대 3개를 넘거나, 여러 chunk 중 최소 8자 미만 문구가 있으면 렌더 금지
caption_chunks를 합친 내용이 음성 전문과 다르거나 beat 시간을 연속으로 덮지 않으면 렌더 금지
포인트 pop이 chunk 시작 520~650ms 뒤가 아니거나 420ms 동안 한 번 재생되지 않으면 렌더 금지
HTML 재생·스크럽·렌더 프레임에서 같은 영상 시간의 포인트 위치가 다르면 렌더 금지
모든 scene/beat의 asset + caption + narration 의미 일치 확인
의미가 한 칸이라도 밀려 있으면 렌더 금지
개인 세대를 특정하는 호수, 가족사진, 식별 가능한 얼굴, 차량번호가 보이면 렌더 금지
주소/건물명/아파트 동 번호는 단독 노출만으로 차단하지 않되, 개인 식별 정보와 결합되면 차단
```

HTML 생성 전 공식 preflight 명령:

```powershell
python scripts/produce_review_v2.py preflight `
  --package "<output review package>" `
  --planning "<planning_recipe.json>" `
  --edit "<edit_recipe.json>" `
  --privacy-manifest "<privacy_asset_manifest.json>" `
  --sync-manifest "<output review package>/sync_manifest.json"
```

`video_engine_v2.reels_qa`는 이 공식 경로가 내부에서 사용하는 diagnostic
module이며, production 산출물 생성의 직접 진입점이 아닙니다. gate가 실패하면
MP4 렌더를 진행하지 않습니다.

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
  --sync-manifest "<output review package>/sync_manifest.json" `
  --render-job "<output review package>/_work/render_jobs/<job-id>/render_job.json"
```

일반 HTML 렌더는 `--render-job`이 없거나 job 상태가 `succeeded`가 아니거나 현재 MP4
bytes/SHA-256이 다르면 post-render QA를 시작하지 않습니다. `_hyperframes_` 출력은
별도의 `hyperframes-render-gate.mjs` 승인 경로를 사용하므로 이 인자를 요구하지 않습니다.

이 스크립트는 아래를 자동으로 검사하고 기록합니다.

```text
MP4가 패키지 폴더 안에 있는지
파일명이 upload_10mbps 규칙을 따르는지
sync_manifest.ok / total_voice_cps / meaning_match evidence가 유효한지
final_voice_duration_sec가 있고 MP4 길이와 ±2초 이내인지
ffprobe 기준 1080x1920 / 30fps / H.264 / yuv420p / AAC 44.1kHz stereo인지
대표 프레임 5장을 _work/render_post_qa_*/representative_frames/ 아래 추출했는지
대상 MP4의 package identity, package-relative path, bytes, SHA-256
사용한 sync manifest의 package-relative path, bytes, SHA-256
```

자동 검사 통과는 최종 승인이 아닙니다.
리포트는 반드시 아래 상태로 남아야 합니다.

```text
overall_status: manual_review_required
manual_review.status: pending
```

총괄 PD가 대표 프레임을 열어 개인정보, 자막 크기/위치, 상품/리뷰 가림, 음성-자막-화면 싱크를 확인한 뒤에만 최종 완료로 봅니다.

## Post-render QA와 현재 MP4의 구분

`auto_status: pass`는 과거 QA pass 증거입니다. package state scan은 report의 package
identity, upload MP4 상대경로, bytes, SHA-256이 현재 package의 upload artifact와 모두
일치할 때만 `render_complete: true`로 계산합니다. hash가 없는 legacy QA report는
`post_render_qa_pass_evidence_present: true`일 수 있어도 `render_complete: unknown`이며
`legacy_report_missing_mp4_hash` limitation으로 남습니다. 이는 기존 upload MP4 package
삭제·재렌더 지시가 아니며, published/performance도 별도 증거 없이는 `unknown`입니다.

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
호수 표식이 읽히는가? (주소/건물명/아파트 동 번호는 허용)
가족사진이나 식별 가능한 얼굴이 보이는가? (불투명 유리 너머 실루엣은 허용)
유리/거울 반사에 얼굴이 남아 있는가?
차량번호/송장/전화번호가 가려지지 않고 보이는가?
리뷰 캡처에 상품주문번호/작성자 계정이 가려지지 않고 보이는가?
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
