# aniREF

게임 애니메이션 레퍼런스 분석 / 키포즈 조합 툴.
여러 레퍼런스 영상에서 좋은 키포즈를 뽑아 비교·조합하고, Maya 블로킹에 바로 쓴다.

**Video → Frame → Key Pose → Compare → Combine → Blocking**

설계, 데이터 모델, 단축키, 마일스톤은 [docs/DESIGN.md](docs/DESIGN.md) 참고.

## 할 수 있는 것

| 영역 | 기능 |
|---|---|
| 플레이어 | 프레임 정확 재생·이동(VFR 게임 녹화 포함), 루프, 0.1x~2x 슬로우, Mirror, 여러 영상 탭, Focus 모드, 항상 위 |
| 드로잉 | 펜 · 직선 · 화살표 · 원 · 지우개, 프레임별 드로잉 + 모든 프레임 가이드, Undo/Redo |
| 분석 보기 | Onion Skin, 실루엣, Motion Trail(검끝 궤적 · Root Motion 이동 거리 · 속도), 타이밍 구간, 키포즈 간격(원본 fps ↔ 애니 fps) |
| 키포즈 | `K`로 원본 해상도 추출, Phase · 태그 · 메모 · 앞발/체중, 라이브러리 필터와 검색 |
| 조합 | Sequence Board(드래그로 조합, hold 타이밍), Flipbook, 비교 보드(행 = 영상, 열 = Phase) |
| 내보내기 | Contact Sheet PNG(클립보드 복사), Maya 마커 JSON/CSV + Maya 셸프 스크립트 |
| 확인 | 레퍼런스 vs 내 Playblast 비교 창(나란히 · 겹쳐 · 차이, 시간/프레임 동기화) |
| 기타 | 한국어/영어, 단축키 바꾸기, 자동 저장 · 복구, 사용 설명서(F1)와 단축키 오버레이(?) |

## 설치 (개발용, Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

동료에게 배포할 때는 빌드된 포터블 zip / 설치 파일을 쓴다 → [packaging/README.md](packaging/README.md).

## 실행

```powershell
.\.venv\Scripts\python.exe -m aniref
```

처음이라면 시작 화면의 **3분 시작 가이드**를 누르거나, 프로그램 안에서 `F1`(사용 설명서) / `?`(단축키)를 누르세요.

## Maya 마커

`maya/install_aniref.mel`을 Maya 뷰포트에 끌어다 놓으면 셸프에 aniREF 버튼이 생긴다. aniREF에서 `Ctrl+Shift+E`로 내보낸 마커 JSON을 그 버튼으로 불러오면 Time Slider Bookmark가 만들어진다(Maya 2020 이상).

## 레퍼런스 영상 점검

```powershell
.\.venv\Scripts\aniref-probe.exe D:\refs\MH_SNS_01.mp4
```

프레임 수, fps/VFR 여부, 키프레임 간격과 함께 seek·재생 디코딩·뒤로 한 프레임 이동 속도를 보여준다.

## 테스트 · 화면 확인

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\screenshots.py shots ko
```

테스트는 처음 실행할 때 `test_media/`에 프레임 번호가 바코드로 새겨진 테스트 영상을 만들고, 여러 형식(H.264 B-frame, 긴 GOP, Open GOP, VFR, HEVC, VP9, ProRes, AVI)에서 프레임 정확도를 확인한다. UI 테스트는 화면 없이 돈다.
`tools/screenshots.py`는 모든 화면을 실제 데이터로 렌더링해 PNG로 저장한다(UI 리뷰용).

## 빌드

```powershell
.\packaging\build.ps1
```

PyInstaller로 `dist\aniREF\`를 만들고, 빌드된 exe의 `--selftest`(영상 열기 → 프레임 이동 → 프레임 번호 검증)를 통과해야 포터블 zip과 설치 파일을 만든다. 태그(`v*`)를 push하면 GitHub Actions가 같은 과정을 돌려 Release에 올린다.

## 라이선스

GPL-3.0 (함께 배포하는 FFmpeg에 GPL 구성요소 포함). 저장소 루트에 `LICENSE` 파일을 추가해야 한다.
