# 문장군 영상 edit_recipe v2 스키마

> 목적: `script.md`, `subtitle.srt`, `voice.mp3`, 현장 사진 폴더를 실제 릴스 편집 타임라인으로 변환하기 위한 중간 데이터 계약.

## 핵심 개념

v1은 `scene` 중심이었다.

```text
HOOK / SCENE / CONFLICT / SOLUTION / TWIST / CLOSE
```

v2는 `micro_beat` 중심이다.

```text
짧은 자막
+ 특정 사진
+ 특정 모션
+ 나레이션 구간
+ 전환 효과
+ 선택 SFX
= 하나의 편집 비트
```

## 최상위 구조

```json
{
  "version": "2.0",
  "source": {},
  "style_dna": {},
  "asset_roles": {},
  "beats": [],
  "audio_plan": {},
  "render_targets": {}
}
```

## source

```json
{
  "package_dir": "output/inbox_20260609/010_구축소음_20260609_095709",
  "script": "010_구축소음_script.md",
  "srt": "010_구축소음_subtitle.srt",
  "voice": "010_구축소음_voice.mp3",
  "image_dir": "010_구축소음_이미지",
  "reference_edit": "010_구축소음_직원편집.mp4"
}
```

## style_dna

```json
{
  "tone": "review_story_reels",
  "caption_style": "large_yellow_keyword",
  "brand_badge": "none",
  "default_image_motion": "ken_burns",
  "transition_energy": "medium_high",
  "blur_policy": "only_when_layering_cards",
  "proof_ending": "review_capture"
}
```

## asset_roles

이미지 파일명을 역할로 태깅한다.

```json
{
  "before_main": "시공전 메인.jpg",
  "after_main": "시공완료 메인.jpg",
  "after_open": "시공완료 3연동 문열림.jpg",
  "after_side": "시공완료 측면.jpg",
  "after_entry_view": "시공완료 현관문에서바라보기.jpg",
  "place_exterior": "현장사진_외관.jpg",
  "place_entry_stairs": "현장사진_입구계단.jpg",
  "place_stairs": "현장사진_계단들.jpg",
  "measure_level": "실측 (2).jpg",
  "measure_wall": "실측 (3).jpg",
  "product_thumbnail": "상품썸네일.jpg",
  "review_capture": "리뷰캡처.jpg"
}
```

## beat

```json
{
  "id": "b01",
  "phase": "opening_hook",
  "time": [0.0, 0.7],
  "asset": "paper_graphic",
  "caption": "구축",
  "caption_emphasis": ["구축"],
  "motion": "paper_crumple_pop",
  "transition_in": "cut",
  "transition_out": "pop",
  "sfx": "paper_crumple",
  "sync_note": "intro before narration or first syllable"
}
```

## motion 후보

| motion | 용도 |
|--------|------|
| `paper_crumple_pop` | 오프닝 호기심 |
| `before_after_flash` | 비포에서 애프터로 반전 |
| `ken_burns_slow` | 일반 현장 사진 |
| `entry_path_pan` | 외관/계단/복도 동선 |
| `keyword_pop` | 짧은 문제 키워드 |
| `problem_shake` | 소음/냄새 불편 |
| `measure_scan` | 실측/레이저/줄자 |
| `product_card_flash` | 상품 썸네일 짧은 삽입 |
| `clean_glow_reveal` | 완료컷 해결감 |
| `review_capture_scroll` | 실제 리뷰 증명 |

## caption 규칙

- `caption`은 화면에 크게 뜨는 문구다.
- `narration_ref`는 해당 문구가 어느 내레이션 구간과 맞는지 적는다.
- `caption`은 SRT 원문보다 짧아도 된다.
- 한 beat의 caption은 15자 내외를 우선한다.

## audio_plan

```json
{
  "narration": "010_구축소음_voice.mp3",
  "bgm": {
    "enabled": true,
    "mood": "light_upbeat_reels",
    "volume_db": -24
  },
  "sfx": {
    "enabled": true,
    "volume_db": -12,
    "ducking": "narration_first"
  }
}
```

## render_targets

```json
{
  "preview": {
    "fps": 12,
    "resolution": [720, 1280]
  },
  "final": {
    "fps": 30,
    "resolution": [1080, 1920]
  }
}
```

## v2 성공 기준

- 첫 3초 안에 문제와 해결 이미지가 모두 등장한다.
- 30~35초 영상에 최소 15개 beat가 있다.
- 좌상단 고정 브랜드 배지가 없다.
- 제품 썸네일이 제품 설명 구간에 1회 이상 등장한다.
- 리뷰캡처가 마지막 4초 안에 등장한다.
- 자막은 내레이션과 구절 단위로 맞는다.
- 사진은 어둡게 묻히지 않고 정보가 보인다.
