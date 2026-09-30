# 배포 (packaging)

aniREF를 **Python 없는 Windows PC**에서 바로 돌아가는 형태로 묶는다. 결과물은 두 가지:

| 파일 | 내용 |
|---|---|
| `dist\aniREF-<버전>-portable.zip` | 압축 풀고 `aniREF.exe` 실행. 설치 없음, 설정·로그는 폴더 안 `data\`에 저장 |
| `dist\aniREF-<버전>-setup.exe` | 원클릭 설치(관리자 권한 불필요). 시작 메뉴, `.aniref` 연결, 제거 지원 |

평소에는 **태그를 push하면 GitHub Actions가 알아서 만든다**(아래 "릴리스 내기"). 아래 로컬
빌드는 패키징 자체를 고칠 때만 필요하다.

## 파일

| 파일 | 역할 |
|---|---|
| `aniref.spec` | PyInstaller 설정(폴더 방식, 창 모드, 아이콘, 버전 정보, 뺄 Qt 모듈) |
| `build.ps1` | 아이콘 → PyInstaller → **셀프테스트** → zip → 설치 파일. 빌드는 이것만 실행하면 된다 |
| `installer.iss` | Inno Setup 6 설치 파일 스크립트(사용자 폴더 설치, 한/영 UI, `.aniref` 연결) |
| `make_icon.py` | `aniref.ui.icons.app_icon()`(코드로 그린 아이콘)을 `aniref.ico`로 저장 |
| `aniref.ico` | 위 스크립트가 만든 아이콘. exe·설치 파일·파일 연결이 모두 이 파일을 쓴다 |
| `portable.txt` | zip에만 들어가는 표시 파일. 이 파일이 exe 옆에 있으면 포터블 모드 |
| `../.github/workflows/release.yml` | 태그 push → 테스트 → 빌드 → Release 업로드 |

## 로컬에서 빌드하기

```powershell
# 준비 (한 번만)
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" pyinstaller
# 설치 파일까지 만들려면 Inno Setup 6.3 이상도 필요 (없으면 zip까지만 만들고 넘어간다)
#   choco install innosetup    또는    https://jrsoftware.org/isdl.php

# 빌드
.\packaging\build.ps1
```

옵션: `-SkipInstaller`(zip까지만), `-Python <경로>`(기본값은 `.venv`의 python, 없으면 PATH의
python), `-SelftestTimeoutSec 240`.

빌드는 이 순서로 진행되고, 한 단계라도 실패하면 거기서 멈춘다.

1. `dist\`, `build\pyinstaller|selftest|portable` 정리
2. `make_icon.py`로 `aniref.ico` 생성
3. PyInstaller로 `dist\aniREF\` 생성 (약 155 MB)
4. **셀프테스트 (설치판)**: `dist\aniREF\aniREF.exe --selftest`를 `%APPDATA%`를 임시 폴더로
   돌려놓고 실행 → 종료 코드 확인 + **exe 폴더에 아무 것도 쓰지 않았는지** 확인
5. `build\portable\aniREF\`에 복사 + `portable.txt` 추가 → **셀프테스트 (포터블)**:
   설정·로그가 `data\`에 생기고 `%APPDATA%`에는 아무 것도 안 생기는지 확인 → `data\` 삭제
6. `dist\aniREF-<버전>-portable.zip` 생성 (약 61 MB)
7. `ISCC.exe`가 있으면 `dist\aniREF-<버전>-setup.exe` 생성

### 셀프테스트(`--selftest`)

`aniREF.exe --selftest`는 창을 띄우지 않고 (임시 폴더에 PyAV로 만든) 30프레임짜리 영상을
**실제 import → 플레이어 경로**로 열어서 프레임을 앞뒤로 이동하고, 각 프레임 그림에 새겨진
번호가 요청한 번호와 같은지 확인한다. 통과하면 0, 실패하면 1로 끝나고 이유는 로그
(`%APPDATA%\aniREF\logs\aniref.log`, 포터블은 `data\logs\aniref.log`)에 남는다.

FFmpeg DLL 누락, Qt 플러그인 누락, 빠진 모듈처럼 "빌드해야만 드러나는" 문제를 동료에게
보내기 전에 잡는 장치다. 소스에서도 돌아간다: `python -m aniref --selftest`.

## 릴리스 내기

1. `src/aniref/__init__.py`의 `__version__`을 올린다 (예: `0.2.0`). 이게 유일한 버전 출처다 —
   exe 버전 정보, zip·setup 파일 이름, 설치 파일 버전이 모두 여기서 나온다.
2. 변경 사항을 커밋하고 push한다.
3. 태그를 만들어 push한다. **태그 이름은 `v` + 버전**이어야 한다(다르면 워크플로가 실패한다).
   ```powershell
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. Actions에서 `Release` 워크플로가 테스트 → 빌드 → 셀프테스트 → 설치 파일 생성을 하고,
   결과를 GitHub Releases에 올린다. 릴리스 노트는 자동 생성되니 앞에 한두 줄 덧붙이면 좋다.
5. 동료에게는 Releases 페이지 링크만 주면 된다(GitHub 계정 없이 받을 수 있다).

빌드만 확인하고 싶으면 Actions 탭에서 `Release`를 **Run workflow**로 직접 실행한다. 이때는
Releases에 올리지 않고 산출물만 워크플로 아티팩트로 남는다.

### 처음 실행할 때 나오는 Windows 경고

코드 서명 인증서가 없어서 `setup.exe`나 `aniREF.exe`를 처음 실행하면 SmartScreen이
"Windows의 PC 보호" 경고를 띄운다. **추가 정보 → 실행**을 누르면 된다. 동료 안내(README)에
이 내용을 넣어 둔다.

## TODO: LICENSE

저장소 루트에 **`LICENSE` (GPL-3.0 전문)를 추가해야 한다.** GitHub 저장소 페이지에서
`Add file → Create new file → LICENSE` 를 입력하면 나오는 라이선스 선택기에서
**GNU General Public License v3.0**을 고르면 전문이 채워진다.

- 이유: 배포본에 들어가는 FFmpeg(PyAV 휠 포함본)에 **x264/x265(GPL)**가 들어 있어서
  프로젝트 전체가 GPL-3.0이어야 한다. PySide6(LGPL)는 폴더 방식 빌드라 라이브러리 교체가
  가능해 조건을 만족한다.
- 파일만 추가하면 된다: `aniref.spec`이 있으면 `dist\aniREF\LICENSE.txt`로 복사하고,
  `installer.iss`는 그 파일이 있으면 설치 마법사의 라이선스 동의 화면에 띄운다.
  (`maya\` 폴더도 생기면 자동으로 앱 폴더에 같이 들어간다.)

## 참고

- **폴더 방식(onedir)**을 쓴다: 한 파일(onefile)은 실행할 때마다 임시 폴더에 풀어서 느리고,
  백신 오탐이 잦고, LGPL(Qt) 조건상으로도 폴더 방식이 깔끔하다.
- 크기의 대부분은 FFmpeg(`_internal\av.libs`, 약 63 MB), Qt(약 47 MB), numpy/OpenBLAS
  (약 27 MB)다. 쓰지 않는 Qt 모듈·플러그인·번역은 `aniref.spec`에서 빼 두었으니, 새로 Qt
  모듈을 쓰게 되면 `_QT_UNUSED`와 `_DROP` 목록을 먼저 확인할 것.
- HTTPS는 Windows 기본 TLS(schannel)를 쓴다. Qt hook이 빌드 PC의 PATH에 있는 OpenSSL을
  주워 담지 않도록 `aniref.spec`에서 빼고 있다.
- 업데이트로 덮어쓸 때 실행 중인 aniREF는 설치 파일이 닫으라고 물어본다(Restart Manager).
- 포터블 zip을 이전 버전 폴더에 덮어쓰면 `data\`(설정·로그)는 그대로 유지된다.
