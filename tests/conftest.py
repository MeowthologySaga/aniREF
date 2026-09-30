from pathlib import Path

import pytest

from videogen import SPECS, ensure_videos

MEDIA_DIR = Path(__file__).resolve().parent.parent / "test_media"


@pytest.fixture(scope="session")
def test_videos() -> dict[str, Path]:
    return ensure_videos(MEDIA_DIR)


@pytest.fixture(params=SPECS, ids=[s.name for s in SPECS])
def video(request, test_videos):
    spec = request.param
    return spec, test_videos[spec.name]
