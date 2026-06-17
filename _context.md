# _context.md — 문장군 숏폼 콘텐츠 엔진

> 마지막 업데이트: 2026-06-16 (얼굴 전용 Google Vision 블러 파이프라인 도입/주소 기본 허용 기준 보정)
> 담당 총괄: 총괄매니저 v2.17.0

## 현재 상태
- **Phase 2 진행 중** — F-001/F-005/F-002/F-003 완료
- generate.py는 invalid script.md 저장을 막고, 통과한 script.md에서 묶음별 output(`output/pilot`, `output/inbox_20260609`)을 생성함
- F-002/F-003 입력 계약 확정: SRT=자막 텍스트, TTS=내레이션 텍스트
- TTS 레퍼런스 속도 확정: 리뷰2 음원 기준 공백 제외 244자 / 35.02초 / 초당 약 6.97자
- 내레이션 글자수와 음원 길이는 품질 우선. 스크립트가 길면 음원도 길어져도 됨
- 리뷰 원본은 1리뷰 1파일. 권장 형식은 `리뷰묶음/001_짧은라벨.txt` + `리뷰번호/상품주문번호/내용`
- 한 줄 명령 `리뷰컨텐츠 신규 만들어줘`를 받으면 `REVIEW_CONTENT_COMMAND.md`를 따라 후보 3개 제안 후 선택받고 제작함
- 한 줄 명령 `리뷰 릴스 만들자`를 받으면 `docs/review_video_publish_workflow_v2.md`를 따라 리뷰 선택/패키지 폴더/사진 투입/기획 승인/HTML 프리뷰/사용자 승인/MP4 렌더/캡션·해시태그 점검까지 진행함
- `033 리뷰 릴스 만들자`처럼 번호만 지정한 명령은 HTML 제작 승인이 아님. 신규 세션은 사진검수/역할매핑/PD 기획안/scene 의미 일치 계획표까지만 제시하고 사용자 기획 승인 전 script/SRT/TTS/HTML 생성 금지(D-027)
- 릴스 현재 진행 상태/다음 후보/칸반은 `docs/reels_operations_dashboard_v1.md`를 우선 확인함
- `PROJECT_DASHBOARD.md`는 전체 현황판. 리뷰 수, 점수, 생성 패키지, 최근 결정, 다음 작업을 한눈에 본다
- HOOK 공감 질문형 광고 문장은 validate_script()에서 FAIL 처리함
- 신규 제공된 리뷰 목록 중 A급 후보 3개(`017_부모님반전`, `018_층간소음배려`, `019_박람회반값`)를 선별하여 제안하고 사용자 응답 대기 중
- 2026-06-09 붙여넣기 리뷰 100개를 정리함. 기존 017~019와 중복된 3개는 갱신했고, 020~116 신규 97개를 `reviews/inbox_20260609/`에 추가함
- 현재 정식 등록 리뷰는 116개이며, 신규 97개 1차 자동 채점 완료. 신규 97개 평균 6.6/12, A권/B권/C권 22/40/35
- 전체 리뷰 127개는 모두 채점 완료. 전체 A권/B권/C권 38/51/38, 전체 평균 7.0/12
- `020_로봇청소구축리모델링` 패키지 생성 완료. 다음 제작 후보는 `033_소음차단냄새먼지`, `114_반려동물소음차단`, `098_소음차단냄새먼지` 등 미제작 A권 후보
- 2026-06-09 파서 수정: `내용:` 아래 여러 줄 리뷰 본문을 끝까지 읽도록 보정. 020 생성 전 71자만 읽히던 문제를 353자 전체 입력으로 수정함
- 신규 채점표는 `reviews/inbox_20260609/_scores_20260609_020_116.md`
- 운영 원칙 보강: 다음 리뷰 추가부터는 `REVIEW_INTAKE_CHECKLIST.md` 기준으로 파싱/중복검사/파일정리/1차채점/후보선별/대시보드갱신/문맥갱신/무결성검증까지 같은 턴에 완료해야 함
- 영상엔진 v2 설계 시작. 핵심 전환은 `리뷰 -> 스크립트/SRT`가 아니라 `리뷰 -> 목적/타입/훅/타임라인 planning recipe -> 내레이션/SRT/HTML/MP4` 구조.
- `video_engine_v2/` 패키지 추가. 현재는 005_여름에어컨 광고형 파일럿용 rule-based analyzer/planner/converter를 제공함.
- 005_여름에어컨 ad_v2 산출물 생성 완료. 기존 음성 길이에 맞춘 sync-safe 검수본이며, 진짜 20~23초 광고 완성본은 v2 내레이션으로 새 음성을 생성해야 함.
- 2026-06-11 005_여름에어컨 ad_v2_final HTML 생성 완료. 새 22.98초 음성 기준이며 MP4는 아직 렌더하지 않음.
- 2026-06-11 004_어려운시공 difficult_installation_v2_final HTML 생성 완료. 새 26.98초 음성 기준이며 MP4는 아직 렌더하지 않음.
- 2026-06-11 010_구축소음 old_building_noise_v2_final HTML 생성 완료. 새 24.99초 음성 기준이며 MP4는 아직 렌더하지 않음.
- 2026-06-11 020_로봇청소구축리모델링 living_flow_v2_final HTML 생성 완료. 새 26.99초 음성 기준이며 MP4는 아직 렌더하지 않음. 방향은 로봇청소기/문턱/생활동선형.
- 2026-06-11 020_로봇청소구축리모델링은 `living_flow_geninsert_v3`가 현재 기준. 로봇청소기 문턱 막힘/문턱 없음 통과 장면은 생성 B-roll을 짧게 삽입했고, 중반 이후 싱크 보정을 위해 상품 썸네일 시작을 11.0초로 당김.
- 신규 세션용 영상 인수인계 문서는 `docs/video_session_handoff_20260611.md`.
- 2026-06-12 005/010/004/020-gen 최종 업로드용 MP4 렌더 완료. 최신 기준 파일명은 `*_final_render_20260612_upload_10mbps.mp4`.
- 최종 릴스 렌더 스펙 확정: 1080x1920 / 30fps / H.264 실제 전체 약 9~10Mbps / AAC 44.1kHz stereo 192k.
- `render_html_preview_v2.js` 기본 최종 렌더 옵션은 video 11000k, maxrate 12000k, bufsize 24000k, audio 192k, 44100Hz, stereo.
- 2026-06-12 다음 릴스 후보 5개(033, 114, 098, 034, 025) 사진 투입 폴더 생성 완료. 안내 문서: `docs/reels_photo_intake_20260612.md`.
- 2026-06-13 보충 후보 `105_냄새먼지친절상담` 패키지/이미지 폴더 생성 완료. 위치: `output/inbox_20260609/105_냄새먼지친절상담_20260613_105019/105_냄새먼지친절상담_이미지`. 사진 투입 후 사진검수/PD 기획안부터 진행.
- 2026-06-15 키워드 1개 강조 기준 채택. 문서: `docs/munjanggun_motion_rule_v1.md`. 105 테스트 variant: `105_냄새먼지친절상담_dust_care_trust_motion_rule_v1_keyword_accent_html_preview_v2`.
- 2026-06-15 다음 릴스 후보 5개 사진 투입 폴더 생성 완료: 036, 088, 100, 115, 116. 안내 문서: `docs/reels_photo_intake_20260615.md`.
- 2026-06-15 `리뷰 각색 작가`를 정식 팀원으로 임명. 문서: `docs/reels_writer_persona_v1.md`. 신규 릴스는 작가 브리프 없이 HTML 제작 금지.
- 2026-06-16 100_층간소음구축리모델링 `difficult_three_openings_v1` HTML 프리뷰 완료. 사용자 승인 훅은 `중문 두 곳에 방문 교체까지, 쉬운 현장이 아니었습니다`. `현장_외관.jpg`는 차량번호 노출로 제외했고, final voice는 raw copy 38.84초. MP4 렌더는 아직 미승인.
- 2026-06-17 036_냄새먼지깔끔시공 `damp_bathroom_door_v1` HTML 프리뷰 완료. 훅은 `물에 불어버린 욕실문, 그냥 둘 수 없었습니다`. 외관/입구 컷은 차량번호 가능성으로 제외했고, final voice는 raw copy 34.88초. MP4 렌더는 아직 미승인.
- 2026-06-17 116_친절상담기사칭찬 `top_finish_trust_v1` HTML 프리뷰 완료. 훅은 `저렴한 곳보다, 결국 마감이 중요했습니다`. `현장_외관.jpg`는 식별 리스크로 제외했고, final voice 37.233초/압축률 1.122로 QA 통과. MP4 렌더는 아직 미승인.
- 2026-06-17 088_소음차단냄새먼지 `open_privacy_noise_cold_v1` HTML 프리뷰 완료. 훅은 `답답한 중문은 싫고, 냉기와 소음은 막고 싶다면?`. 사용자 피드백으로 `3단 슬라이딩` 표현을 `3연동중문`으로 교체했고 TTS/SRT/HTML을 재생성함. `현장_주차장.jpg`는 차량번호 노출로 제외했고, final voice 36.44초/압축률 1.0/전체 CPS 6.56으로 QA 통과. MP4 렌더는 아직 미승인.
- 2026-06-17 115_구축리모델링이사중문 `crooked_gapwall_v1` HTML 프리뷰 완료. 훅은 `벽도 천장도 반듯하지 않은 구축집, 가벽까지 세워 맞췄습니다`. `현장_외관.jpg`는 차량번호/식별 리스크로 제외했고, final voice 39.372초/압축률 1.114/전체 CPS 7.01로 QA 통과. MP4 렌더는 아직 미승인.
- 2026-06-17 이번 일괄 렌더 5개 완료: 036, 088, 100, 115, 116. 모두 `*_final_render_20260617_upload_10mbps.mp4` 기준이며 ffprobe/spec/대표프레임/privacy QA를 통과했다.
- 2026-06-16 개인정보 QA 기준 보정. 주소/건물명은 기본 허용, 얼굴/가족사진/반사 얼굴/차량번호/송장/도어락/실명은 차단. 얼굴은 수동 좌표가 아니라 `video_engine_v2/privacy_face_blur.py`의 Google Vision Face Detection proposal을 먼저 만들고 사용자 검수 후 sanitized asset으로 승격한다.
- 2026-06-12 025/033/034 이미지 ZIP 압축 해제 완료. 025=17장, 033=16장, 034=18장. 다음 단계는 세 폴더 사진검수/역할매핑 후 우선 제작 후보 결정.
- 2026-06-12 098 이미지 ZIP 압축 해제 완료. 098=16장. 현재 사진검수 대기는 025/033/034/098, 사진대기는 114.
- 2026-06-12 025 living_review_v1 신규 세션 산출물은 TTS 속도 실패로 승인 금지. 공백 제외 280자 / 27.986초 = 10.0자/초. D-024 기준으로 내레이션 재작성 또는 음성 재생성 필요.
- 2026-06-12 025 living_review_v1은 훅도 실패. `한 달 뒤, 진짜입니다`는 중문/집 분위기/생활 변화 맥락이 빠진 추상 문장. D-025 기준으로 첫 화면 훅 재작성 필요.
- 2026-06-12 025 living_review_v2는 한 달 후기 + 집 분위기 변화 방향으로 개선됐고 MP4 렌더도 생성됐으나, 음성 품질 문제로 승인 보류. 기존 voice는 원본 TTS 39.49초를 28.94초로 압축한 1.36배 케이스라 발음 뭉개짐 위험이 큼. D-028 기준으로 재생성 필요.
- 2026-06-12 025 voicefix 후보 2개 생성 완료. 위치: `output/inbox_20260609/025_소음차단구축리모델링_20260612_102821/_work/voicefix_025_living_review_v2_20260612/`. 추천 확인 후보는 `voicefix_b_clear_reels_sulafat_29s.mp3`.
- 2026-06-12 033 entry_noise_smell_v2 신규 세션 산출물은 승인 금지. D-024 속도는 통과했지만 scene별 asset/caption/narration 의미가 어긋남. D-026 기준으로 planning/edit recipe 재작성 필요.
- 2026-06-12 D-027 추가. 번호 지정만으로는 script/SRT/TTS/HTML 생성 금지. 033은 기존 v2를 폐기하고 사진검수/PD 기획안부터 다시 시작해야 함.
- 2026-06-12 D-029 추가. 사진이 부족하거나 문맥과 맞지 않으면 생성 B-roll/이미지젠 인서트를 제안할 수 있음. 단 실제 시공 증거가 아니라 생활상황/불편체감 이해 보조로만 사용하고, literal QA를 통과해야 함.


## 최근 완료
- ✅ 005_여름에어컨 정식 패키지 생성 완료 (script, srt, tts 음원 26.97초)
- ✅ 020_로봇청소구축리모델링 정식 패키지 생성 완료 (script, srt, tts 음원, 캡션/해시태그 포함)
- ✅ 영상엔진 v2 설계 문서 4종 작성 (`docs/video_engine_v2_design.md`, `docs/video_templates_v2.md`, `docs/video_recipe_schema_v2.md`, `docs/refactor_roadmap_v2.md`)
- ✅ 현재 영상 파이프라인 감사 문서 작성 (`docs/current_video_pipeline_audit.md`)
- ✅ `video_engine_v2/` v2 파일럿 패키지 추가 및 테스트 작성
- ✅ 005_여름에어컨 ad_v2 planning/edit/narration/SRT/HTML/MP4 검수본 생성
- ✅ 005_여름에어컨 ad_v2_final 새 음성 + HTML 생성
- ✅ 004_어려운시공 difficult_installation_v2_final 새 음성 + HTML 생성
- ✅ 010_구축소음 old_building_noise_v2_final 새 음성 + HTML 생성
- ✅ 020_로봇청소구축리모델링 living_flow_v2_final 새 음성 + HTML 생성
- ✅ 020_로봇청소구축리모델링 living_flow_geninsert_v3 생성. 생성 B-roll 2개 사용: `AI인서트_로봇청소기_문턱막힘.png`, `AI인서트_로봇청소기_문턱없음통과.png`
- ✅ 신규 세션 인수인계 문서 작성: `docs/video_session_handoff_20260611.md`
- ✅ 005/010/004 MP4 렌더 완료: `*_render_20260611.mp4`
- ✅ 2026-06-12 업로드용 고비트레이트 MP4 4개 재렌더 완료: 005/010/004/020-gen `*_upload_10mbps.mp4`
- ✅ 렌더러 최종 기본 스펙 보강: `render_html_preview_v2.js`, `docs/render_qa_rules_v2.md`
- ✅ 신규 세션 트리거 보강: `GEMINI.md`, `REVIEW_CONTENT_COMMAND.md`, `docs/review_video_publish_workflow_v2.md`
- ✅ 릴스 운영 대시보드 추가: `docs/reels_operations_dashboard_v1.md`
- ✅ 다음 후보 5개 사진 투입 폴더 생성: 033, 114, 098, 034, 025
- ✅ 025/033/034 이미지 ZIP 압축 해제 완료: 025 17장, 033 16장, 034 18장
- ✅ 098 이미지 ZIP 압축 해제 완료: 16장
- ✅ D-024 릴스 TTS 속도 하드 게이트 추가: 9.0자/초 이상 실패, 장면별 10자/초 초과 재작성
- ✅ D-025 릴스 훅 압축 검수 하드 게이트 추가: 기획 훅과 HTML 첫 화면 훅을 별도 검수
- ✅ D-026 릴스 장면 의미 일치 하드 게이트 추가: scene별 asset + caption + narration 불일치 시 실패
- ✅ D-027 리뷰 번호 지정 시 기획 승인 게이트 추가: 번호만 받은 신규 세션은 PD 기획안에서 멈추고 승인 전 HTML 생성 금지
- ✅ D-028 TTS 압축률/목소리 품질 하드 게이트 추가: 원본/최종 음성 압축률 1.20 이상 실패, 1.25 이상 렌더 금지
- ✅ D-029 부족/부적합 사진의 생성 인서트 사용 게이트 추가: 사진 부적합 시 생성 이미지 제안 가능, 실제 증거 대체 금지
- ✅ 2026-06-15 리뷰 각색 작가 페르소나 공식 편입: `docs/reels_writer_persona_v1.md`
- ✅ 2026-06-16 004_어려운시공 privacyfix v1 재렌더 완료: 주소/건물명/가족사진/반사 얼굴 후보 익명화 후 `004_difficult_installation_privacyfix_v1_final_render_20260616_upload_10mbps.mp4` 생성
- ✅ 2026-06-17 업로드용 고비트레이트 MP4 5개 렌더 완료: 036/088/100/115/116 `*_final_render_20260617_upload_10mbps.mp4`
- ✅ 2026-06-16 소재 개인정보 QA 하드 게이트 추가: `docs/reels_privacy_asset_qa_rules_v1.md`, `video_engine_v2/reels_qa.py`, `tests/test_reels_qa.py`
- ✅ 2026-06-16 얼굴 전용 Google Vision 블러 도구 추가: `video_engine_v2/privacy_face_blur.py`, `tests/test_privacy_face_blur.py`. 주소/건물명은 기본 허용으로 기준 보정.
- ✅ 2026-06-13 릴스 엔진 고도화 감사 문서 작성: `docs/reels_engine_improvement_audit_20260613.md`
- ✅ 2026-06-13 Phase 1 잠금장치 도입: `video_engine_v2/reels_qa.py`, `tests/test_reels_qa.py`
- ✅ 2026-06-13 025/033/034/098/114 패키지 루트에 `STATUS.md`, `APPROVAL_LOG.md` 생성. 기본값은 안전하게 `mp4_allowed: false`.
- ✅ 2026-06-13 HTML 생성 전 preflight 규칙 연결: `python -m video_engine_v2.reels_qa --planning "<planning_recipe.json>" --edit "<edit_recipe.json>"`
- ✅ 2026-06-13 Phase 2 sync manifest 도입: `build_sync_manifest`, `apply_sync_evidence`, `write_sync_manifest`, `--sync-manifest-out`
- ✅ 2026-06-13 `sync_manifest.json` 필수 필드: scene_id, asset, caption, narration, planned_time, duration_sec, narration_chars_no_space, scene_cps, meaning_match, meaning_match_evidence, risk
- ✅ 2026-06-13 `sync_manifest.audio` 필수 필드: raw_tts_duration_sec, final_voice_duration_sec, compression_ratio, total_narration_chars_no_space, total_voice_cps
- ✅ 2026-06-13 `total_voice_cps = 전체 narration_ref 공백 제외 글자수 / final_voice_duration_sec`. 장면별 CPS가 통과해도 total_voice_cps 9.0 이상이면 실패.
- ✅ 2026-06-13 `render_duration_sec`는 타임라인 길이일 뿐 실제 voice.mp3 길이 증거로 인정하지 않음. final_voice_duration_sec 또는 voice_duration_sec가 없으면 실패.
- ✅ 2026-06-13 meaning_match는 planning scene에 명시된 boolean true 증거가 있을 때만 edit beat로 보강. 문자열/추정/유사도 기반 자동 true 금지.
- ✅ 2026-06-13 114 legacy edit recipe로 sync-only manifest 생성 테스트: `_work/114_pet_noise_relief_v1_sync_manifest_phase2_check.json`. 결과는 의도적으로 `ok: false` because legacy raw TTS/meaning_match evidence missing.
- ✅ STORY_EXTRACTION_RULES.md 작성
- ✅ prompts/screenplay.txt + persona.txt 완성
- ✅ 환경 구축 (google-genai, .env)
- ✅ generate.py F-001 파일럿 4건 통과
- ✅ HOOK 프롬프트 튜닝 (공감질문형→사건미리보기형)
- ✅ F-005 검증 로직 강화
- ✅ 자막 텍스트 기준 확정: 섹션 헤딩 외 앞뒤 대괄호 금지
- ✅ 리뷰2·리뷰11 재생성 및 F-005 통과
- ✅ F-002 SRT 자동 생성 구현
- ✅ 리뷰2·리뷰11 짧은제목_subtitle.srt 생성 확인
- ✅ F-003 Gemini TTS 구현
- ✅ 리뷰2·리뷰11 짧은제목_voice.mp3 생성 확인
- ✅ TTS 요약 제거: script.md 내레이션 원문 기준으로 음성 생성
- ✅ 말 속도 조정 적용: 리뷰2 35.02초 / 리뷰11 35.04초 (SRT 35초 ±3초 통과)
- ✅ 산출물 파일명 규칙 적용: `짧은제목_파일타입.확장자`
- ✅ F-006 구현: 리뷰번호/상품주문번호 파싱, script.md 메타데이터 자동 포함, 짧은 라벨 output 파일명
- ✅ 신규 운영 리뷰 16개를 `reviews/inbox_20260609/`에 1리뷰 1파일로 저장
- ✅ output 번호 충돌 방지: 파일럿 산출물은 `output/pilot/`로 이동, 신규 운영 산출물은 `output/inbox_20260609/`로 생성
- ✅ REVIEW_CONTENT_COMMAND.md 추가: 한 줄 명령으로 후보 제안 → 사용자 선택 → 패키지 생성 흐름 고정
- ✅ PROJECT_DASHBOARD.md 추가: 전체 진행률, 리뷰 자산 27개, 패키지 4개, 후보 점수 현황 정리
- ✅ 감사 후속 조치: HOOK 공감 질문형 검증 강화, .gitignore 추가, 대시보드 점수 드리프트 지표 추가, PRD output 구조 갱신
- ✅ D-018 기록: 리뷰 원본 장기 관리 규칙
- ✅ D-017 기록: 리뷰2 음원 속도 기준 고정, 글자수 단속 제거
- ✅ D-015 기록: SRT/TTS 입력 계약 + TTS 품질 기준
- D-014 기록: "중문 콘텐츠 X, 사건 콘텐츠 O"

## 핵심 결정
- "중문 콘텐츠 X, 사건 콘텐츠 O" (D-014) 🔒
- "영상엔진 v2는 planning recipe 중심으로 v1 옆에 추가" (D-019) 🔒
- Phase 1 순서 변경 (D-013) 🔒
- gemini-2.5-flash + google-genai SDK

## 다음 할 일
1. 신규 세션에서 `리뷰 릴스 만들자` 요청 시 `docs/review_video_publish_workflow_v2.md`와 `docs/reels_writer_persona_v1.md`부터 읽고 진행
2. 사용자가 사진을 넣으면 `docs/reels_photo_intake_20260612.md`의 5개 폴더를 확인
3. 대상 패키지의 `STATUS.md`, `APPROVAL_LOG.md`를 먼저 확인. 없으면 생성하고, 명시 승인 전 `mp4_allowed: false` 유지
4. 사진검수 후 `리뷰 각색 작가`가 writer brief를 작성하고, 사건/감정/증거/훅/말맛을 먼저 확정
5. 사진/영상 소재는 `docs/reels_privacy_asset_qa_rules_v1.md` 기준으로 얼굴/가족사진/반사 얼굴/차량번호/송장/도어락/실명/동호수를 먼저 검수. 주소/건물명은 기본 허용. 얼굴은 `python -m video_engine_v2.privacy_face_blur`로 proposal/contact sheet를 만든 뒤 사용자 검수 후 sanitized asset으로 승격하고 `privacy_review` 또는 `privacy_sanitization_report`를 남김
6. planning/edit recipe 생성 후 `apply_sync_evidence` 또는 동등 루틴으로 raw/final TTS duration과 scene별 meaning_match 증거를 보강
7. HTML 생성 전 `python -m video_engine_v2.reels_qa --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --sync-manifest-out "<sync_manifest.json>"` 실행. `[FAIL]`이 있으면 HTML 생성 금지. `PRIVACY_REVIEW_MISSING`도 실패 사유임
7. 현재 025/033/034/098은 압축 해제 완료 상태이므로 사진 수량/내용/파일명/부족 컷을 먼저 검수하고, 가장 제작 준비가 잘 된 후보부터 영상 기획 시작
8. 025는 기존 living_review_v1을 승인본으로 쓰지 말고, D-024 TTS 속도 기준과 D-025 훅 검수 기준 통과 후 HTML 재검수
9. 025는 기존 living_review_v2_voice.mp3를 승인본으로 쓰지 말고, voicefix 후보 확인 후 승인 음성으로 교체/재렌더
10. 033 entry_noise_smell_v2는 승인본으로 쓰지 말고, D-027에 따라 사진검수/작가 브리프/PD 기획안/scene 의미 일치 계획부터 다시 제시하고 사용자 승인 후에만 HTML 생성
11. HTML 승인 후에만 `*_upload_10mbps.mp4` 최종 렌더 및 대표 프레임 QA
12. 릴스 1건 완료 후에는 `docs/reels_operations_dashboard_v1.md`에서 다음 후보군을 보충하고, 새 사진 투입 폴더까지 준비

## 마지막 오더 번호
- 없음 (이번 세션은 총괄 직접 작업)
