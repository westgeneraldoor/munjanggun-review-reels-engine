# Munjanggun Review Reels PD Standard v2

Date: 2026-06-11

This document records the production standard after reviewing the 005, 004, and 010 v2 final HTML previews.

## Current Judgment

The v2 direction is viable.

The strongest improvement is not visual polish by itself. The real improvement is that each review now has a clearer content purpose:

- 005: seasonal ad / cooling pain
- 004: trust / difficult-site proof
- 010: conversion / old-building noise and smell concern

This proves that the review engine can become more than an automatic editor. It can become a review-based short-form creative system.

## What Is Working

### 1. Hook Quality Improved

The first sentence is now a complete viewer-facing idea.

Good examples:

```text
에어컨 풀가동해도 거실이 덥다면?
다른 업체가 그냥 가던 현장
복도 소리 다 들리는 구축 빌라라면?
```

These are stronger than keyword fragments because they name the viewer's situation quickly.

### 1-1. Hook Compression Failure Rule

A planning hook and a screen hook are not automatically the same thing.
When a hook is shortened for the first screen, the editor must not remove the subject or the change.

Bad compression:

```text
중문은 설치 당일보다, 한 달 뒤가 더 진짜입니다
-> 한 달 뒤, 진짜입니다
```

This fails because the viewer no longer knows what is true, what changed, or why they should care.

Better:

```text
중문 설치 한 달 뒤,
집 분위기가 달라졌습니다
```

Hard rule:

```text
First-screen hook = subject + viewer situation/change.
Abstract payoff words alone are not hooks.
```

### 2. Review Proof Is Better

The review capture is now used as evidence, while the readable quote is pulled forward as copy.

Rule:

```text
review capture = evidence
large quote = readable proof
```

### 3. Template Purpose Is Becoming Distinct

004 and 010 no longer feel like the same video with different photos.

- 004 should feel like field difficulty -> professional handling -> trust.
- 010 should feel like old-building discomfort -> measurement -> changed living feel.
- 005 should feel like seasonal discomfort -> immediate benefit -> consultation.

This distinction must be protected as production scales.

## Current Weak Spots

### 1. Audio/Caption/Screen Sync Is Still The Main Risk

004 improved greatly, but the voice and visual/caption timing can still feel slightly off.

Rule:

```text
If the viewer can say "the voice is talking about A but the screen already moved to B",
the render is not approved.
```

Every final preview needs a sync QA pass before MP4 render.

### 2. Scene Count Must Be Controlled

More scenes can help only when they are micro-cuts inside the same spoken idea.

Recommended limit:

```text
20-23s ad: 6-7 major scenes, 8-10 micro visual moments
24-28s trust/conversion: 7-8 major scenes, 9-12 micro visual moments
30s+ profile content: only if the review has real process depth
```

Do not add scenes just because more photos exist.

### 3. Captions Can Still Become Too Dense

Some scenes, especially 004, risk having captions that are semantically good but visually heavy.

Rule:

```text
One scene = one thought.
One caption = one punch.
If it needs commas, split it.
```

### 4. Motion Effects Need More Editorial Hierarchy

Current motion is better, but future scaling needs effect hierarchy:

- Hook: highest impact
- Problem: tension
- Process: proof, not chaos
- Result: clean reveal
- Review: slow enough to read
- CTA: stable and legible

Too many high-energy transitions reduce trust.

## Approval Checklist Before MP4

Each HTML preview must pass:

- The first 2 seconds explain why the viewer should keep watching.
- The first hook names the subject or situation clearly. If it only says `진짜입니다`, `좋아졌습니다`, or `달라졌습니다` without context, it fails.
- The HTML first-screen hook is reviewed separately from the planning hook.
- Voice, caption, and image are talking about the same idea.
- No scene reveals the conclusion before the narration earns it.
- Review quote is readable in 1-2 seconds.
- CTA is visible and legible for at least 1.5 seconds.
- Product thumbnail does not get covered by center captions.
- No unsupported absolute claims such as `완벽 차단`, `무조건 절약`, or guaranteed savings.
- The video type feels distinct from previous outputs.

## Production Scaling Rule

Do not produce all reviews with one universal template.

Use a two-layer system:

```text
review analysis
-> purpose + video type
-> template-specific scene grammar
-> final timing and sync QA
```

Minimum production types:

- cooling effect
- old building noise
- difficult installation
- pet / child safety
- living-in installation
- cost concern / consultation trust
- design satisfaction

## 020_Robot Vacuum Direction Preview

The likely direction for 020 is not just "middle door installation".

It should probably be:

```text
old door / threshold discomfort
-> robot vacuum and child/living convenience
-> whole-home upgrade feeling
-> should have done it sooner
```

Potential hook candidates:

```text
로봇청소기, 문턱에서 자꾸 막힌다면?
오래된 방문 때문에 집 분위기가 답답했다면?
문턱 하나가 생활 동선을 막고 있었다면?
```

020 should not reuse the 005 or 010 rhythm. It needs a daily-life convenience rhythm.

## Final PD Standard

The goal is not:

```text
review -> pretty video
```

The goal is:

```text
review -> viewer pain -> proof -> changed living moment -> consultation
```

This is the production standard for v2.
