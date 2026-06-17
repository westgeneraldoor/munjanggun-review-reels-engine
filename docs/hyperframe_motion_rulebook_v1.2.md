# Hyperframe Motion Rulebook v1.2
> v1.1 대비 추가: Story Engine / Camera Engine / Audio Sync Engine (Metadata Mode) / Color-Lighting Engine

---

## 1. Motion Tokens
*(v1.1 동일 — 생략 없이 유지)*

```yaml
timing:
  instant: 0.18
  fast: 0.35
  medium: 0.65
  slow: 1.2
  dwell_short: 1.4
  dwell_medium: 2.2
  dwell_long: 3.4

stagger:
  chars: 0.012
  words: 0.05
  lines: 0.14
  cards: 0.08

scale:
  subtle: 1.03
  medium: 1.08
  punch: 1.18

blur:
  soft: 6
  medium: 12
  hard: 20

secondary_action:
  y_drift: 5
  opacity_drift: 0.04
  cycle_duration: 0.5
```

---

## 2. Premium Easings
*(v1.1 동일)*

```yaml
ease:
  premium_out: expo.out
  premium_inout: power3.inOut
  sharp_exit: power4.in
  soft_entry: sine.out
  luxury_float: circ.out
  zoom_scale: "expoScale(1, 3, power3.inOut)"
  number_roll: power3.out
  bounce_snap: "back.out(1.2)"
```

---

## 3. Story Engine ★ NEW

> 씬 간 연결 규칙. 각 씬은 독립 애니메이션이 아닌 narrative arc의 한 스텝이다.
> AI 에이전트는 scene_count 입력 시 아래 template 중 하나를 자동 선택하고
> 각 arc step에 씬을 1:1 매핑한다.

### 3-1. Story Templates

```yaml
story_templates:

  hook_proof_cta:
    steps: [hook, proof, benefit, trust, cta]
    description: "가장 범용. SaaS / 스타트업 기본형."
    arc_pacing:
      hook:    { tempo: fast,   emotion: urgency,   duration_ratio: 0.15 }
      proof:   { tempo: medium, emotion: premium,   duration_ratio: 0.25 }
      benefit: { tempo: medium, emotion: innovation, duration_ratio: 0.25 }
      trust:   { tempo: slow,   emotion: trust,     duration_ratio: 0.20 }
      cta:     { tempo: fast,   emotion: urgency,   duration_ratio: 0.15 }

  pain_solution_desire:
    steps: [pain, solution, desire, cta]
    description: "문제 직격형. 스타트업 런칭 / 비교 영상."
    arc_pacing:
      pain:     { tempo: fast,        emotion: urgency,    duration_ratio: 0.20 }
      solution: { tempo: medium,      emotion: innovation, duration_ratio: 0.35 }
      desire:   { tempo: slow,        emotion: premium,    duration_ratio: 0.30 }
      cta:      { tempo: fast,        emotion: urgency,    duration_ratio: 0.15 }

  before_after_future:
    steps: [before, after, future, cta]
    description: "변화 증명형. 금융 / 럭셔리 하드웨어."
    arc_pacing:
      before:  { tempo: slow,   emotion: trust,     duration_ratio: 0.25 }
      after:   { tempo: medium, emotion: premium,   duration_ratio: 0.35 }
      future:  { tempo: slow,   emotion: innovation, duration_ratio: 0.25 }
      cta:     { tempo: medium, emotion: trust,     duration_ratio: 0.15 }
```

### 3-2. Scene Transition Rules

> 연속된 두 씬의 arc step이 결정되면 아래 매트릭스에서 전환 방식을 자동 선택한다.

```yaml
transition_matrix:
  hook     -> proof:    zoom_through        # 에너지 유지하며 진입
  proof    -> benefit:  directional_wipe    # 논리적 순서감
  benefit  -> trust:    blur_dissolve       # 속도 감소, 신뢰 전환
  trust    -> cta:      scale_punch         # 에너지 재점화
  pain     -> solution: hard_cut + flash    # 극적 대비
  solution -> desire:   depth_parallax      # 몰입 심화
  before   -> after:    match_cut           # 대비의 연속성
  after    -> future:   cinematic_pan       # 확장감
  any      -> cta:      directional_wipe    # 기본 fallback
```

### 3-3. Message Escalation Rules

```yaml
message_escalation:
  # 헤드라인 스케일은 arc 진행에 따라 점층적으로 확대
  hook:    headline_scale: 1.0
  proof:   headline_scale: 1.1
  benefit: headline_scale: 1.2
  trust:   headline_scale: 0.95   # 의도적 축소 — 신뢰는 조용하게
  cta:     headline_scale: 1.4    # 최대 타격

  # 여백은 arc 중반 이후 감소 — 에너지 압축
  hook:    whitespace: 65%
  proof:   whitespace: 60%
  benefit: whitespace: 55%
  trust:   whitespace: 70%        # trust는 예외 — 넓게
  cta:     whitespace: 40%        # 공간 압박으로 행동 유도
```

---

## 4. Camera Engine ★ NEW

> 객체 애니메이션과 별개로 씬 전체에 적용되는 가상 카메라 워크.
> `.scene-root` 또는 `.camera-rig` 요소에 적용한다.

### 4-1. Camera Vocabulary

```yaml
camera_moves:

  dolly_in:
    description: "카메라가 피사체를 향해 직선으로 접근. 집중과 압박감."
    gsap_props:
      scale: 1.0 -> 1.15
      z: 0 -> 80
    duration: 2.0
    ease: power2.inOut
    use_when: [proof, benefit, CTA]

  dolly_out:
    description: "카메라가 후퇴. 전체 맥락 노출, 여유감."
    gsap_props:
      scale: 1.15 -> 1.0
      z: 80 -> 0
    duration: 1.8
    ease: sine.inOut
    use_when: [hook, trust]

  orbital_15deg:
    description: "피사체 주변을 15° 공전. Apple 하드웨어 회전 연출."
    gsap_props:
      rotationY: 0 -> 15
      transformPerspective: 1200
    duration: 3.0
    ease: power1.inOut
    use_when: [luxury_hardware, proof]

  macro_pan:
    description: "극단적 클로즈업 후 수평 패닝. 디테일 강조."
    gsap_props:
      scale: 2.0
      x: 0 -> -8%          # vw 기준 퍼센트
    duration: 2.5
    ease: sine.inOut
    use_when: [luxury_hardware, benefit]

  lens_compression:
    description: "배경을 전경 속도 대비 30% 느리게 이동. 피사계 심도 모방."
    gsap_props:
      foreground_x: 100%
      background_x: 70%    # 전경 대비 70% 이동 — parallax
    duration: 1.5
    ease: power1.inOut
    use_when: [any]

  focal_shift:
    description: "포커스 이동. 블러로 전/후경 전환."
    gsap_sequence:
      - { target: ".foreground", filter: "blur(0px) -> blur(8px)", duration: 0.4 }
      - { target: ".background", filter: "blur(8px) -> blur(0px)", duration: 0.4, offset: "-=0.2" }
    ease: power2.inOut
    use_when: [trust, innovation]
```

### 4-2. Camera Rules

```yaml
camera_rules:
  max_simultaneous_moves: 1        # 카메라 무브 동시 적용 금지
  avoid_zoom_and_pan_together: true # dolly + pan 동시 = 멀미 유발
  orbital_max_angle: 20            # 20° 초과 시 어색함
  dolly_in_max_scale: 1.2          # 이상은 zoom_through로 대체
```

---

## 5. Audio Sync Engine ★ NEW (Metadata Mode)

> v1.2 기준: Mode A (Metadata Sync) 전용.
> 실제 오디오 파일 분석 없이 bpm 메타데이터로 GSAP delay를 자동 계산한다.

### 5-1. Audio Metadata Schema

```yaml
audio_sync:
  mode: metadata               # metadata | detect_basic(v1.5) | waveform(v2.0)
  bpm: 124
  signature: 4/4
  drop_points: [8.0, 24.0]    # 초 단위 — 에너지 피크 시점
  energy_curve:
    - [0.0, low]
    - [4.0, medium]
    - [8.0, high]
    - [16.0, medium]
    - [24.0, high]
    - [32.0, low]
  accent_every: 2beat          # 컷 전환 단위
  headline_on_drop: true       # drop_point에 헤드라인 등장 강제
  cta_bar: 16                  # 16번째 bar에 CTA 등장
```

### 5-2. Beat Interval 자동 계산 공식

```javascript
// 엔진 내부 계산 — AI 에이전트는 이 수식으로 모든 delay를 도출한다
const bpm = 124;
const beat    = 60 / bpm;          // 0.484s
const bar     = beat * 4;          // 1.935s
const halfBar = bar / 2;           // 0.968s

// accent_every: 2beat → 컷 전환 간격
const cutInterval = beat * 2;      // 0.968s

// cta_bar: 16 → CTA 등장 절대 시간
const ctaTime = bar * 16;          // 30.97s
```

### 5-3. Beat-Mapped GSAP Timeline

```javascript
const bpm = 124;
const beat = 60 / bpm;
const bar  = beat * 4;

const tl = gsap.timeline();

// 헤드라인: drop_point 8.0s에 등장
tl.from(".headline span", {
  yPercent: 120, opacity: 0,
  stagger: 0.012, duration: 0.9,
  ease: "expo.out"
}, 8.0);

// 카드 cascade: drop 후 1bar 뒤
tl.from(".card", {
  y: 40, opacity: 0,
  stagger: 0.08, duration: 0.8,
  ease: "power3.out"
}, 8.0 + bar);

// scale punch: 매 2beat마다
[0, 1, 2, 3].forEach(i => {
  tl.to(".punch-element", {
    scale: 1.08, duration: beat * 0.5, ease: "expo.out",
    yoyo: true, repeat: 1
  }, beat * 2 * i);
});

// CTA: 16bar째
tl.from(".cta-button", {
  scale: 0.8, opacity: 0,
  duration: 0.6, ease: "back.out(1.2)"
}, bar * 16);
```

### 5-4. Energy Curve → Motion Density 매핑

```yaml
energy_to_motion:
  low:    { cut_rate: slow,   stagger_multiplier: 1.5, scale_punch: 1.03 }
  medium: { cut_rate: medium, stagger_multiplier: 1.0, scale_punch: 1.08 }
  high:   { cut_rate: fast,   stagger_multiplier: 0.7, scale_punch: 1.18 }
  # stagger_multiplier: 기본 stagger 값에 곱함
  # high → chars stagger: 0.012 * 0.7 = 0.008s (더 빠르게)
```

---

## 6. Color-Lighting Engine ★ NEW

### 6-1. Color Emotion Palette

```yaml
color_emotion:

  trust:
    primary: "#0A1628"        # 딥 네이비
    accent:  "#2563EB"        # 클리어 블루
    bg:      "#F8FAFF"        # 쿨 화이트
    gradient: "linear-gradient(135deg, #0A1628 0%, #1E3A8A 100%)"
    avoid: [warm_tones, high_saturation_red]

  luxury:
    primary: "#0D0D0D"        # 퓨어 블랙
    accent:  "#C9A84C"        # 골드
    bg:      "#0D0D0D"
    gradient: "linear-gradient(135deg, #0D0D0D 0%, #1A1A1A 100%)"
    avoid: [bright_colors, flat_white_bg]

  innovation:
    primary: "#0F0F1A"        # 다크 바이올렛 블랙
    accent:  "#7C3AED"        # 바이올렛
    secondary_accent: "#06B6D4" # 시안
    gradient: "linear-gradient(135deg, #7C3AED 0%, #06B6D4 100%)"
    avoid: [muted_tones, serif_heavy_type]

  urgency:
    primary: "#FFFFFF"
    accent:  "#EF4444"        # 레드
    bg:      "#0A0A0A"
    gradient: "linear-gradient(90deg, #EF4444 0%, #F97316 100%)"
    avoid: [soft_pastels, slow_transitions]

  premium:
    primary: "#1A1A2E"
    accent:  "#E2E8F0"        # 쿨 실버
    bg:      "#0F0F1A"
    gradient: "linear-gradient(135deg, #1A1A2E 0%, #16213E 100%)"
    avoid: [warm_yellows, high_contrast_clashes]
```

### 6-2. Lighting Effects

```yaml
lighting:

  rim_glow:
    description: "피사체 테두리 발광. 럭셔리/혁신 씬."
    css: "box-shadow: 0 0 40px 8px rgba(124, 58, 237, 0.4)"
    gsap:
      from: { boxShadow: "0 0 0px 0px rgba(124,58,237,0)" }
      to:   { boxShadow: "0 0 40px 8px rgba(124,58,237,0.4)", duration: 1.2, ease: "power2.out" }
    use_when: [innovation, luxury]
    max_intensity: "rgba(*, *, *, 0.5)"   # 0.5 초과 = 과잉 — 금지

  soft_shadow:
    description: "신뢰감 UI 카드 그림자. 부드럽고 넓게."
    css: "box-shadow: 0 8px 32px rgba(0,0,0,0.12)"
    gsap:
      from: { boxShadow: "0 2px 8px rgba(0,0,0,0.06)" }
      to:   { boxShadow: "0 8px 32px rgba(0,0,0,0.12)", duration: 0.8, ease: "power1.out" }
    use_when: [trust, premium]

  gradient_pulse:
    description: "배경 그라디언트 미세 pulse. 생동감."
    gsap:
      from: { backgroundPosition: "0% 50%" }
      to:   { backgroundPosition: "100% 50%", duration: 4.0, repeat: -1, yoyo: true, ease: "sine.inOut" }
    css_base: "background-size: 200% 200%"
    use_when: [innovation, urgency]

  cinematic_vignette:
    description: "화면 가장자리 암부 처리. 시선을 중앙으로."
    css: "box-shadow: inset 0 0 120px rgba(0,0,0,0.6)"
    apply_to: ".scene-root"
    use_when: [luxury, trust]

  lens_flare_subtle:
    description: "광원 이동 시 미세한 플레어. 과용 절대 금지."
    gsap:
      opacity: 0 -> 0.3 -> 0
      duration: 0.6
    max_per_scene: 1            # 씬당 1회 초과 금지
    use_when: [luxury_hardware, innovation]
```

### 6-3. Color × Emotion 자동 매핑

```yaml
# product_type + emotion 입력 시 color scheme 자동 선택
color_mapping:
  saas + premium:        premium
  saas + urgency:        urgency
  luxury_hardware + any: luxury
  finance + trust:       trust
  finance + premium:     trust       # finance는 trust 팔레트 우선
  startup_hype + any:    urgency
  any + innovation:      innovation  # innovation은 emotion 우선
```

---

## 7. Scene Grammar (v1.2 업데이트)

> Story Engine arc step이 추가되어 각 씬에 `arc_step` 키가 필수화됨.
> Camera Engine move가 씬 레벨에서 선언됨.

### Hero Reveal

```yaml
scene: hero_reveal
arc_step: hook                # Story Engine 연결
total_duration: 5.2
camera_move: dolly_in         # Camera Engine 연결
audio_sync_ref: drop_points[0] # 첫 번째 drop에 씬 시작 맞춤
color_scheme: premium         # Color Engine 연결
sequence:
  - step: bg_fade_in
    target: ".bg-layer"
    props: { autoAlpha: 0 -> 1 }
    duration: 0.8
    ease: soft_entry

  - step: product_scale
    target: ".product-hero"
    props: { scale: 0.92 -> 1.00, autoAlpha: 0 -> 1 }
    duration: 1.0
    ease: premium_out
    offset: "-=0.3"

  - step: headline_chars_stagger
    target: ".hero-title span"
    props: { yPercent: 120, scale: 1.2, autoAlpha: 0 -> 1 }
    duration: 0.9
    stagger: chars
    ease: premium_out
    offset: "-=0.2"

  - step: lighting_apply
    target: ".product-hero"
    lighting: rim_glow
    offset: "-=0.5"

  - step: glow_hold
    target: ".product-hero"
    props: { filter: "brightness(1.08)" }
    duration: 1.6
    secondary_action: true

  - step: zoom_transition
    target: ".scene-root"
    props: { scale: 1.0 -> 3.0 }
    duration: 1.0
    ease: zoom_scale
```

### Dashboard Showcase

```yaml
scene: dashboard_showcase
arc_step: proof
total_duration: 6.8
camera_move: macro_pan
color_scheme: saas + premium  # color_mapping 자동 → premium
sequence:
  - step: headline_line_mask
    target: ".dash-headline"
    props: { clipPath: "inset(0 100% 0 0) -> inset(0 0% 0 0)" }
    duration: 0.65
    ease: premium_out

  - step: cards_cascade_bottom_up
    target: ".dash-card"
    props: { y: 40, autoAlpha: 0 -> 1 }
    duration: 0.8
    stagger: cards
    ease: premium_out
    offset: "-=0.2"

  - step: lighting_apply
    target: ".dash-card"
    lighting: soft_shadow

  - step: chart_draw_line
    target: ".chart-path"
    props: { strokeDashoffset: 100% -> 0% }
    duration: 1.2
    ease: power3.inOut
    offset: "-=0.1"

  - step: KPI_counter
    target: ".kpi-value"
    props: { innerText: 0 -> target_value }
    duration: 1.5
    ease: number_roll
    offset: "-=0.8"

  - step: ui_hold
    duration: 2.8
    secondary_action: true
```

---

## 8. Product Profiles *(v1.1 동일 — camera / color 연결 추가)*

```yaml
saas:
  tempo: fast-medium-fast
  whitespace: medium
  focus_points: 3
  transitions: [wipe, parallax, grid_wave]
  camera_moves: [dolly_in, macro_pan]
  color_scheme: premium
  headline_hold: 1.4
  ui_hold: 2.8
  recommended_emotions: [premium, urgency]

luxury_hardware:
  tempo: slow-medium
  whitespace: high
  focus_points: 1
  transitions: [zoom_through, depth_fade, cinematic_pan]
  camera_moves: [orbital_15deg, macro_pan, focal_shift]
  color_scheme: luxury
  headline_hold: 2.0
  product_hold: 3.2
  recommended_emotions: [premium, innovation]

finance:
  tempo: medium
  whitespace: high
  focus_points: 2
  transitions: [fade_slide, precision_wipe]
  camera_moves: [dolly_in, dolly_out]
  color_scheme: trust
  headline_hold: 1.8
  trust_curve: high
  recommended_emotions: [trust, premium]

startup_hype:
  tempo: fast-fast-slow-fast
  whitespace: low
  focus_points: 4
  transitions: [speed_ramp, blur_cut, punch_zoom]
  camera_moves: [dolly_in]
  color_scheme: urgency
  headline_hold: 0.9
  recommended_emotions: [urgency, innovation]
```

---

## 9. Product × Emotion 충돌 해소 룰 *(v1.1 동일)*

```yaml
conflict_resolution:
  saas + premium:
    override: { ease: expo.out, whitespace: 55%, focus_points: 2 }

  luxury_hardware + trust:
    override: { whitespace: 70%, motion_amplitude: low, transitions: [depth_fade, cinematic_pan] }

  finance + urgency:
    rule: product_profile_base PRIORITY
    override: { speed: medium, scale_punch: 1.08, cut_rate: low }

  luxury_hardware + urgency:
    rule: product_profile_base PRIORITY
    override: { tempo: slow-medium, urgency_allowed_scenes: [CTA_blast] }

  startup_hype + trust:
    rule: emotion_overlay PRIORITY
    override: { whitespace: 55%, cut_rate: medium, motion_amplitude: medium }

  finance + startup_hype:
    rule: CONFLICT_ERROR
    message: "호환 불가. finance에는 [trust, premium] 중 선택."
```

---

## 10. Safety Rules

```yaml
max_simultaneous_focus_points: 3
min_text_read_time: 1.2
max_transition_chain: 2
avoid_random_rotation: true
avoid_multiple_bounce: true
avoid_excess_glow: true
secondary_action_threshold: 1.4
max_blur_px: 20
min_stagger_chars: 0.008
max_stagger_lines: 0.18
max_camera_moves_per_scene: 1
max_lens_flare_per_scene: 1
rim_glow_max_opacity: 0.5
```

---

## 11. Render Recipes (GSAP) *(v1.1 + 신규 추가)*

### Recipe 01~08 *(v1.1 동일 — 생략)*

### Recipe 09 — Beat-Mapped Timeline (Audio Sync)

```javascript
const bpm = 124;
const beat = 60 / bpm;   // 0.484s
const bar  = beat * 4;   // 1.935s

const tl = gsap.timeline();

// drop_point 8.0s에 헤드라인
tl.from(".headline span", {
  yPercent: 120, opacity: 0,
  stagger: 0.012, duration: 0.9,
  ease: "expo.out"
}, 8.0);

// 1bar 후 카드 cascade
tl.from(".card", {
  y: 40, opacity: 0,
  stagger: 0.08, duration: 0.8,
  ease: "power3.out"
}, 8.0 + bar);

// 매 2beat scale punch
[0, 1, 2, 3].forEach(i => {
  tl.to(".beat-element", {
    scale: 1.08, duration: beat * 0.5,
    ease: "expo.out", yoyo: true, repeat: 1
  }, beat * 2 * i);
});

// 16bar째 CTA
tl.from(".cta-button", {
  scale: 0.8, opacity: 0,
  duration: 0.6, ease: "back.out(1.2)"
}, bar * 16);
```

### Recipe 10 — Rim Glow (Lighting)

```javascript
gsap.fromTo(".product-hero",
  { boxShadow: "0 0 0px 0px rgba(124,58,237,0)" },
  { boxShadow: "0 0 40px 8px rgba(124,58,237,0.4)",
    duration: 1.2, ease: "power2.out" }
);
```

### Recipe 11 — Gradient Pulse Background

```javascript
// CSS: background-size: 200% 200%;
gsap.to(".bg-gradient", {
  backgroundPosition: "100% 50%",
  duration: 4.0,
  repeat: -1,
  yoyo: true,
  ease: "sine.inOut"
});
```

### Recipe 12 — Focal Shift (전/후경 블러 교체)

```javascript
const tl = gsap.timeline();
tl.to(".foreground", { filter: "blur(8px)", duration: 0.4, ease: "power2.inOut" })
  .to(".background", { filter: "blur(0px)", duration: 0.4, ease: "power2.inOut" }, "-=0.2");
```

### Recipe 13 — Orbital Camera (하드웨어 회전)

```javascript
gsap.to(".product-3d-rig", {
  rotationY: 15,
  transformPerspective: 1200,
  duration: 3.0,
  ease: "power1.inOut"
});
```

---

## 12. Master Prompt Input (v1.2)

```yaml
# 필수 입력
product_type: saas             # saas | luxury_hardware | finance | startup_hype
emotion: premium               # trust | urgency | premium | innovation
scene_count: 5
duration: 18                   # 초 단위 총 길이
cta: start_now

# 선택 입력
story_template: hook_proof_cta # 생략 시 product_type 기반 자동 선택
brand_style: apple+stripe
audio_sync:
  bpm: 124
  drop_points: [8.0, 24.0]
  headline_on_drop: true
  cta_bar: 16

# 엔진 자동 처리 (입력 불필요)
# - conflict_resolution: product_type + emotion 충돌 자동 해소
# - color_scheme: color_mapping 기반 자동 선택
# - camera_moves: product_profile 기반 자동 배정
# - scene_transitions: transition_matrix + arc_step 기반 자동 결정
# - secondary_action: dwell > 1.4s 씬 자동 적용
```
