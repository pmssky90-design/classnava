# CLASSNOVA

CLASSNOVA는 인천, 강원, 충청 지역을 중심으로 한 지역별 과외 정보 정적 사이트입니다.

이번 단계에서는 엑셀 데이터를 직접 읽지 않고, 추후 엑셀을 JSON 구조로 변환해 그대로 연결할 수 있는 Python 기반 정적 사이트 생성 구조를 준비합니다.

## 폴더 구조

```text
src/
templates/
data/
static/css/
static/js/
static/images/
output/
generator.py
config.py
README.md
```

## 생성 방법

```bash
python generator.py
```

실행 후 아래 파일이 생성됩니다.

```text
output/index.html
output/robots.txt
output/sitemap.xml
output/static/css/style.css
output/static/js/main.js
```

## 엑셀 연결 전 샘플 데이터 테스트 단계

현재 생성기는 `data/pages_sample.json`을 읽어 샘플 페이지를 생성합니다. 엑셀은 아직 읽지 않습니다.

샘플 데이터는 추후 엑셀 변환 결과와 같은 형태로 사용하기 위해 아래 필드를 가집니다.

- `title`: HTML title 값
- `slug`: `output/슬러그/index.html` 경로로 쓰이는 고유 값
- `parent`: 상위 페이지 slug. 최상위 페이지는 빈 문자열
- `description`: meta description 값
- `h1`: 페이지 본문 h1
- `summary`: 페이지 소개 문장
- `breadcrumb`: 수동 경로 탐색을 붙이기 위한 배열
- `links.children`: 하위 링크를 붙이기 위한 배열
- `links.related`: 관련 링크를 붙이기 위한 배열

생성 전 `validate_data()`가 아래 항목을 검사합니다.

- 중복 slug
- 빈 title
- 빈 slug
- 존재하지 않는 parent slug

검증을 통과해야만 `output` 생성 단계가 실행됩니다.

## 샘플 생성 페이지

```text
output/incheon-tutor/index.html
output/gangwon-tutor/index.html
output/chungcheong-tutor/index.html
output/incheon-math-tutor/index.html
output/incheon-english-tutor/index.html
output/gangwon-math-tutor/index.html
output/chungcheong-english-tutor/index.html
```

## 다음 단계 준비

- `data/`: 엑셀 파일 또는 엑셀에서 변환한 JSON 파일을 넣을 위치입니다.
- `generator.py`: `load_future_excel_data()` 함수에 엑셀 변환/읽기 로직을 연결할 수 있도록 비워 두었습니다.
- `templates/`: 메인 페이지와 지역/과목/학년/학교 페이지 템플릿을 추가할 위치입니다.
- `output/regions/`, `output/subjects/`, `output/grades/`, `output/schools/`: 향후 자동 생성 페이지의 기본 출력 경로입니다.

## SEO 기본값

- `title`
- `meta description`
- `canonical`
- 페이지당 1개의 `h1`
- `robots.txt` 전체 허용
- `sitemap.xml` 자동 생성

## 배포용 기본 파일

- `output/404.html`: 정적 호스팅용 오류 페이지
- `output/manifest.json`: CLASSNOVA 웹 앱 매니페스트
- `output/favicon.ico`
- `output/static/images/icon-192.png`
- `output/static/images/icon-512.png`

아이콘 원본을 교체할 경우 `static/favicon.ico`, `static/images/icon-192.png`, `static/images/icon-512.png`를 함께 갱신합니다.
