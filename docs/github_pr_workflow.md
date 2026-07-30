# GitHub PR Workflow

이 문서는 문장군 리뷰 릴스 엔진을 GitHub에서 안전하게 운영하기 위한 PR 기준입니다.

## Repository Scope

GitHub에는 엔진과 문서만 올립니다.

Tracked:

- 릴스 제작 워크플로 문서
- PD 기획, 작가, 모션, 렌더 QA 규칙
- Python/Node 렌더링 스크립트
- HTML 프리뷰 빌더
- 테스트 코드
- README, 운영 대시보드 템플릿

Not tracked:

- `.env`
- `reviews/` 원본 리뷰 텍스트
- `output/` 산출물 전체
- 고객 사진, 리뷰 캡처, 현장 영상, 음성, 최종 MP4
- ZIP/MP4/MP3/WAV/JPG/PNG 등 미디어 파일
- 로컬 폰트 파일
- `node_modules/`, `.codex_deps/`

## Branch Rule

작업은 항상 별도 브랜치에서 진행합니다.

```powershell
git switch -c codex/<work-name>
```

예시:

```powershell
git switch -c codex/render-qa-rules
git switch -c codex/privacy-asset-gate
git switch -c codex/105-motion-rule-update
```

## Before Commit

커밋 전 반드시 확인합니다.

```powershell
git status --short
```

다음 항목이 보이면 커밋하지 않습니다.

- `output/`
- `reviews/`
- `.env`
- 고객 사진/영상/음성
- 최종 MP4
- 로컬 폰트 파일

기본 테스트:

```powershell
python -m unittest discover -s tests
```

릴스 엔진 변경이면 해당 릴스의 QA도 실행합니다.

```powershell
python -m video_engine_v2.reels_qa --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --sync-manifest-out "<sync_manifest.json>" --require-one-shot-contract
```

렌더 관련 변경이면 ffprobe, 대표 프레임, 개인정보 노출 검수까지 확인합니다.

## PR Rule

PR은 기본적으로 Draft로 만들되, 전체 검증과 고객자료 scan이 끝난 구현 작업은 Ready for review로 열 수 있습니다.

```powershell
gh pr create --draft --base main --head codex/<work-name> --title "<title>" --body "<summary>"
```

PR 본문에는 아래를 포함합니다.

- 무엇을 바꿨는지
- 어떤 테스트를 통과했는지
- 고객 원본/산출물이 포함되지 않았는지
- MP4 렌더 여부
- 남은 검수 포인트

## Merge Rule

다음 조건을 만족할 때만 merge합니다.

- 테스트 통과
- PR diff에 고객 자료 없음
- `.env` 또는 키/토큰 없음
- 작업 목적과 무관한 파일 변경 없음
- 필요한 경우 사용자 승인 완료

## Render Output Rule

최종 MP4는 GitHub에 올리지 않습니다.

렌더 파일은 로컬 `output/` 또는 별도 공유/보관 위치에서 관리합니다. GitHub는 엔진, 규칙, 문서, 테스트만 관리하는 장소입니다.
