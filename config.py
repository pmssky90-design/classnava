from pathlib import Path


SITE_NAME = "CLASSNOVA"
SITE_DESCRIPTION = "인천, 충청, 강원 지역의 과외 정보를 지역, 과목, 학년 기준으로 정리한 CLASSNOVA 학습 정보 사이트입니다."
SITE_URL = "https://classnova.kr"
LANGUAGE = "ko"

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
TEMPLATE_DIR = ROOT_DIR / "templates"
DATA_DIR = ROOT_DIR / "data"
GENERATED_PAGES_PATH = DATA_DIR / "pages_generated.json"
SAMPLE_PAGES_PATH = DATA_DIR / "pages_sample.json"
STATIC_DIR = ROOT_DIR / "static"
OUTPUT_DIR = ROOT_DIR / "output"

STATIC_OUTPUT_DIR = OUTPUT_DIR / "static"

DEFAULT_PAGES = [
    {
        "path": "index.html",
        "title": "CLASSNOVA | 지역별 과외 정보",
        "description": SITE_DESCRIPTION,
        "template": "index.html",
    },
]
