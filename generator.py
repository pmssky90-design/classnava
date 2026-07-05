from __future__ import annotations

import hashlib
import html
import json
import shutil
import time
from datetime import date
from pathlib import Path
from string import Template
from typing import Any

from config import (
    DEFAULT_PAGES,
    GENERATED_PAGES_PATH,
    OUTPUT_DIR,
    SAMPLE_PAGES_PATH,
    SITE_NAME,
    SITE_URL,
    STATIC_DIR,
    STATIC_OUTPUT_DIR,
    TEMPLATE_DIR,
)


ROOT_SLUGS = {"강원도과외", "인천과외", "충청남도과외", "충청북도과외"}
FIXED_PAGE_IMAGE = "/static/images/본문이미지1.png"
THUMBNAIL_DIR = STATIC_DIR / "images" / "thumbnails"
THUMBNAIL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
THEME_COLOR = "#0b1f3a"
BACKGROUND_COLOR = "#ffffff"


def ensure_directories() -> None:
    for path in [
        OUTPUT_DIR,
        OUTPUT_DIR / "regions",
        OUTPUT_DIR / "subjects",
        OUTPUT_DIR / "grades",
        OUTPUT_DIR / "schools",
        STATIC_OUTPUT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def reset_output_directory() -> None:
    if OUTPUT_DIR.exists():
        for attempt in range(5):
            try:
                shutil.rmtree(OUTPUT_DIR)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(0.5)


def copy_static_assets() -> None:
    if STATIC_OUTPUT_DIR.exists():
        shutil.rmtree(STATIC_OUTPUT_DIR)
    shutil.copytree(STATIC_DIR, STATIC_OUTPUT_DIR, copy_function=shutil.copy)
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        shutil.copy(favicon_path, OUTPUT_DIR / "favicon.ico")


def render_template(template_name: str, context: dict[str, str]) -> str:
    template_path = TEMPLATE_DIR / template_name
    source = template_path.read_text(encoding="utf-8")
    return Template(source).safe_substitute(context)


def page_url_from_path(path: str) -> str:
    if path == "index.html":
        return f"{SITE_URL}/"
    if path.endswith("/index.html"):
        return f"{SITE_URL}/{path.removesuffix('index.html')}"
    return f"{SITE_URL}/{path}"


def root_static_path(path: str) -> str:
    return "/" + path.split("?", 1)[0].lstrip("/")


def absolute_static_url(path: str) -> str:
    return f"{SITE_URL}{root_static_path(path)}"


def output_relative_prefix(output_path: str) -> str:
    parent = Path(output_path.replace("\\", "/")).parent
    if str(parent) == ".":
        return ""
    return "../" * len(parent.parts)


def relative_static_path(path: str, output_path: str) -> str:
    return output_relative_prefix(output_path) + path.split("?", 1)[0].lstrip("/")


def static_context(output_path: str) -> dict[str, str]:
    return {
        "manifest_href": output_relative_prefix(output_path) + "manifest.json",
        "favicon_href": output_relative_prefix(output_path) + "favicon.ico",
        "icon_192_href": relative_static_path("/static/images/icon-192.png", output_path),
        "style_href": relative_static_path("/static/css/style.css", output_path),
        "script_src": relative_static_path("/static/js/main.js", output_path),
    }


def available_thumbnails() -> list[str]:
    if not THUMBNAIL_DIR.exists():
        return []
    images = [
        f"/static/images/thumbnails/{path.name}"
        for path in THUMBNAIL_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in THUMBNAIL_EXTENSIONS
    ]
    return sorted(images)


def select_thumbnail_path(slug: str) -> str:
    thumbnails = available_thumbnails()
    if not thumbnails:
        return FIXED_PAGE_IMAGE
    digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()
    return thumbnails[int(digest[:8], 16) % len(thumbnails)]


def json_ld_script(data: list[dict[str, Any]] | dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def website_schema() -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": f"{SITE_URL}/",
    }


def webpage_schema(title: str, description: str, url: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": description,
        "url": url,
        "isPartOf": {
            "@type": "WebSite",
            "name": SITE_NAME,
            "url": f"{SITE_URL}/",
        },
    }


def breadcrumb_schema(items: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": url,
            }
            for index, (name, url) in enumerate(items, start=1)
        ],
    }


def default_breadcrumb_items(title: str, url: str) -> list[tuple[str, str]]:
    return [("홈", f"{SITE_URL}/"), (title, url)]


def data_page_path(slug: str) -> str:
    return f"{slug.strip('/')}/index.html"


def page_title(page: dict[str, Any]) -> str:
    return str(page.get("h1") or page["title"])


def seo_title(title: str) -> str:
    clean = str(title).strip()
    if len(clean) < 12 and "CLASSNOVA" not in clean:
        return f"{clean} | CLASSNOVA"
    return clean


def page_description(page: dict[str, Any]) -> str:
    description = str(page.get("description") or "").strip()
    if description and len(description) >= 45:
        return description
    if description:
        return (
            f"{description} CLASSNOVA에서 지역, 과목, 학년 기준으로 관련 과외 정보를 함께 정리했습니다."
        )
    return f"{page['title']} 정보를 CLASSNOVA에서 확인하세요."


def page_summary(page: dict[str, Any]) -> str:
    summary = str(page.get("summary") or page.get("content") or "").strip()
    if summary:
        return summary
    return f"{page['title']} 페이지입니다. 지역, 과목, 학년 기준의 과외 정보를 구조화해 연결합니다."


def page_link(page: dict[str, Any]) -> dict[str, str]:
    return {"title": page_title(page), "url": f"/{page['slug']}/"}


def sort_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(links, key=lambda link: link["title"])


def build_link_list(links: list[dict[str, str]]) -> str:
    if not links:
        return ""

    items = []
    for link in links:
        title = html.escape(link["title"])
        url = html.escape(link["url"])
        items.append(
            '          <li class="link-card">'
            f'<a class="text-link" href="{url}">'
            f'<span>{title}</span>'
            '<small>페이지 정보 보기</small>'
            '</a></li>'
        )
    return "\n".join(['        <ul class="link-list">', *items, "        </ul>"])


def build_link_section(title: str, description: str, links: list[dict[str, str]]) -> str:
    if not links:
        return ""

    return "\n".join(
        [
            '        <section class="section page-section">',
            f"          <h2>{html.escape(title)}</h2>",
            f'          <p class="section-note">{html.escape(description)}</p>',
            build_link_list(links),
            "        </section>",
        ]
    )


def build_breadcrumb_from_parent(page: dict[str, Any], pages_by_slug: dict[str, dict[str, Any]]) -> str:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = page

    while current.get("parent"):
        parent_slug = str(current["parent"])
        if parent_slug in seen or parent_slug not in pages_by_slug:
            break
        seen.add(parent_slug)
        parent = pages_by_slug[parent_slug]
        chain.append(parent)
        current = parent

    crumbs = ['<a href="/">홈</a>']
    for item in reversed(chain):
        title = html.escape(page_title(item))
        url = html.escape(f"/{item['slug']}/")
        crumbs.append(f'<span aria-hidden="true">/</span> <a href="{url}">{title}</a>')

    title = html.escape(page_title(page))
    url = html.escape(f"/{page['slug']}/")
    crumbs.append(f'<span aria-hidden="true">/</span> <a href="{url}">{title}</a>')
    return "\n          ".join(crumbs)


def breadcrumb_items_from_parent(page: dict[str, Any], pages_by_slug: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = page

    while current.get("parent"):
        parent_slug = str(current["parent"])
        if parent_slug in seen or parent_slug not in pages_by_slug:
            break
        seen.add(parent_slug)
        parent = pages_by_slug[parent_slug]
        chain.append(parent)
        current = parent

    items = [("홈", f"{SITE_URL}/")]
    for item in reversed(chain):
        items.append((page_title(item), f"{SITE_URL}/{item['slug']}/"))
    items.append((page_title(page), f"{SITE_URL}/{page['slug']}/"))
    return items


def content_subject(page: dict[str, Any]) -> str:
    title = page["title"]
    return (
        f"{title}은 과목별 학습 흐름을 기준으로 내용을 살펴볼 수 있도록 정리한 페이지입니다. "
        "과목 학습은 단원 이해, 문제 풀이, 오답 정리, 반복 점검이 이어질 때 안정적으로 쌓입니다. "
        "지역과 학년이 함께 연결된 경우에는 생활권 안에서 어떤 학습 리듬을 만들 수 있는지, "
        "학교 일정과 시험 범위가 학습 계획에 어떤 영향을 주는지까지 함께 보는 것이 좋습니다. "
        "이 페이지는 특정 선택을 유도하기보다 관련 상위 지역, 하위 항목, 같은 범주의 페이지를 한곳에서 이어 보도록 구성했습니다."
    )


def content_grade(page: dict[str, Any]) -> str:
    title = page["title"]
    return (
        f"{title}은 학년별 공부 방향을 기준으로 지역 정보를 정리한 페이지입니다. "
        "학년이 올라갈수록 필요한 학습 방식은 달라지며, 기초 개념을 다지는 단계와 시험 흐름을 관리하는 단계가 구분됩니다. "
        "초등은 습관과 이해 중심, 중등은 개념 정리와 내신 대비, 고등은 과목별 우선순위와 시간 관리가 중요합니다. "
        "이 페이지에서는 상위 지역과 인접 페이지를 함께 연결해 학년별 학습 흐름을 비교하며 살펴볼 수 있게 했습니다."
    )


def content_school(page: dict[str, Any]) -> str:
    title = page["title"]
    return (
        f"{title}은 학교생활과 내신 흐름을 함께 고려해 볼 수 있는 페이지입니다. "
        "학교별 학습은 수업 진도, 수행평가, 시험 범위, 학사 일정의 영향을 크게 받습니다. "
        "같은 지역 안에서도 학교에 따라 준비해야 할 단원과 복습 시점이 달라질 수 있으므로, "
        "주변 지역과 학년, 과목 페이지를 함께 확인하면 공부 계획을 더 입체적으로 정리할 수 있습니다. "
        "이 페이지는 학교명을 중심으로 관련 구조를 이어 보는 데 초점을 둡니다."
    )


def content_dong(page: dict[str, Any]) -> str:
    title = page["title"]
    return (
        f"{title}은 동, 읍, 면 단위의 생활권을 기준으로 학습 환경을 살펴보는 페이지입니다. "
        "학생의 공부 습관은 집과 학교의 거리, 이동 시간, 방과 후 일정, 주변 학습 공간의 영향을 받습니다. "
        "가까운 생활권 안에서 꾸준히 반복할 수 있는 루틴을 만드는 것이 중요하며, "
        "인접한 동네나 상위 지역 페이지를 함께 보면 통학 환경과 학교 흐름을 비교하기 쉽습니다. "
        "이 페이지는 세부 생활권에서 출발해 상위 지역과 관련 과목 페이지로 자연스럽게 이동할 수 있도록 구성했습니다."
    )


def content_district(page: dict[str, Any]) -> str:
    title = page["title"]
    return (
        f"{title}은 시, 군, 구 또는 주요 생활권 단위의 학습 환경을 정리한 페이지입니다. "
        "지역 단위가 넓어질수록 학교 분포, 이동 동선, 학원가와 주거지의 흐름, 시험 준비 방식이 함께 달라집니다. "
        "특정 동네만 보는 것보다 하위 생활권과 주변 지역을 함께 살피면 학생에게 맞는 공부 리듬을 이해하기 좋습니다. "
        "이 페이지는 상위 지역과 하위 동네, 같은 범주의 형제 페이지를 연결해 지역 구조를 단계적으로 탐색하도록 돕습니다."
    )


def content_region(page: dict[str, Any]) -> str:
    title = page["title"]
    return (
        f"{title}은 광역 단위의 지역 학습 환경을 넓게 살펴보는 허브 페이지입니다. "
        "도시와 도 단위에서는 시군구별 학교 분포, 생활권 이동, 과목별 수요, 학년별 학습 흐름이 함께 나타납니다. "
        "하위 지역을 바로 비교할 수 있으면 큰 지역 안에서도 학생에게 맞는 공부 환경을 더 차분하게 파악할 수 있습니다. "
        "이 페이지는 세부 지역, 과목, 학년 페이지로 이어지는 출발점이며, 관련 페이지를 통해 구조적으로 탐색할 수 있게 구성했습니다."
    )


def build_intro(page: dict[str, Any]) -> str:
    region_type = str(page.get("region_type", ""))
    if region_type in {"province", "city"}:
        return content_region(page)
    if region_type == "district":
        return content_district(page)
    if region_type == "dong":
        return content_dong(page)
    if region_type == "subject":
        return content_subject(page)
    if region_type == "grade":
        return content_grade(page)
    if region_type == "school":
        return content_school(page)
    return content_region(page)


def build_body_sections(page: dict[str, Any]) -> str:
    title = html.escape(page["title"])
    region_type = str(page.get("region_type", ""))

    if region_type in {"province", "city"}:
        sections = [
            (
                "지역별 학습 환경",
                f"{title}에서는 넓은 지역 안의 시군구와 생활권을 함께 확인할 수 있습니다. "
                "지역별 학교 분포와 이동 동선을 살피면 하위 페이지를 볼 때 기준을 잡기 좋습니다.",
            ),
            (
                "과목과 학년 흐름",
                "과목별 페이지와 학년별 페이지는 서로 다른 기준으로 같은 지역을 보여줍니다. "
                "두 흐름을 함께 보면 기초, 내신, 시험 준비의 우선순위를 더 차분하게 정리할 수 있습니다.",
            ),
            (
                "하위 페이지 탐색",
                "아래 하위 페이지는 이 지역에서 이어지는 세부 지역과 학습 주제를 모은 것입니다. "
                "상위 지역에서 하위 생활권으로 내려가며 구조를 확인할 수 있습니다.",
            ),
        ]
    elif region_type == "district":
        sections = [
            (
                "생활권과 학교 흐름",
                f"{title}은 생활권 단위에서 학교와 이동 흐름을 함께 보기 위한 페이지입니다. "
                "세부 동네와 주변 지구를 비교하면 학생의 일상에 맞는 학습 리듬을 이해하기 쉽습니다.",
            ),
            (
                "세부 지역 연결",
                "하위 페이지에는 동, 읍, 면 또는 인접 생활권이 연결될 수 있습니다. "
                "같은 상위 지역의 페이지를 함께 보면 지역별 차이를 자연스럽게 비교할 수 있습니다.",
            ),
            (
                "학습 계획 기준",
                "시험 일정, 복습 주기, 과목별 약점 점검은 지역과 학교 흐름 안에서 달라질 수 있습니다. "
                "페이지 간 연결을 따라가며 필요한 기준을 좁혀 볼 수 있습니다.",
            ),
        ]
    elif region_type == "dong":
        sections = [
            (
                "공부 습관과 생활 동선",
                f"{title}은 학생의 일상 동선과 공부 습관을 함께 살피는 세부 생활권 페이지입니다. "
                "이동 시간이 길지 않은 환경에서는 반복 학습과 복습 루틴을 만들기 쉽습니다.",
            ),
            (
                "통학 환경 점검",
                "학교, 집, 주변 학습 공간의 위치는 학습 집중도와 시간 관리에 영향을 줍니다. "
                "상위 지역과 형제 페이지를 함께 보면 비슷한 생활권을 비교할 수 있습니다.",
            ),
            (
                "연결 페이지 활용",
                "상위 페이지는 넓은 지역 흐름을, 형제 페이지는 가까운 생활권의 차이를 보여줍니다. "
                "아래 링크를 통해 필요한 범위를 좁혀가며 확인할 수 있습니다.",
            ),
        ]
    elif region_type == "subject":
        sections = [
            (
                "과목별 학습 흐름",
                f"{title}은 과목의 개념 이해, 문제 적용, 오답 정리 흐름을 기준으로 볼 수 있는 페이지입니다. "
                "과목 특성에 따라 복습 주기와 점검 방식이 달라집니다.",
            ),
            (
                "지역과 과목의 연결",
                "같은 과목이라도 학교 진도와 지역 생활권에 따라 준비 방식이 달라질 수 있습니다. "
                "상위 지역과 형제 과목 페이지를 함께 보면 비교 기준을 잡기 좋습니다.",
            ),
            (
                "학년별 확장",
                "과목 페이지는 학년별 페이지와 함께 볼 때 더 구체적인 의미를 가집니다. "
                "기초 정리, 내신 준비, 심화 학습의 흐름을 단계적으로 살펴볼 수 있습니다.",
            ),
        ]
    elif region_type == "grade":
        sections = [
            (
                "학년별 공부 방향",
                f"{title}은 학년 단계에 맞춰 공부 방향을 살피는 페이지입니다. "
                "학년별로 필요한 개념 깊이, 복습 주기, 시험 준비 방식이 달라집니다.",
            ),
            (
                "학교 일정과 학습 리듬",
                "학사 일정과 시험 범위는 학습 계획의 기준이 됩니다. "
                "같은 지역 안에서도 학년별 흐름을 비교하면 준비해야 할 내용을 더 분명히 볼 수 있습니다.",
            ),
            (
                "과목 페이지와 함께 보기",
                "학년 페이지는 과목 페이지와 연결될 때 활용도가 높아집니다. "
                "아래 링크를 통해 같은 상위 지역의 다른 학습 흐름을 함께 확인할 수 있습니다.",
            ),
        ]
    else:
        sections = [
            (
                "학교생활과 학습 흐름",
                f"{title}은 학교생활과 내신 흐름을 함께 살피는 페이지입니다. "
                "수업 진도와 평가 방식은 학습 계획에 직접적인 영향을 줍니다.",
            ),
            (
                "주변 지역 연결",
                "학교 주변 생활권과 상위 지역 페이지를 함께 보면 통학 환경과 학습 루틴을 이해하기 쉽습니다. "
                "관련 페이지를 통해 넓은 지역 구조로 이동할 수 있습니다.",
            ),
            (
                "내신 준비 기준",
                "내신 준비는 시험 범위, 수행평가, 복습 기록을 함께 보는 과정입니다. "
                "학년과 과목 페이지를 연결해 필요한 흐름을 정리할 수 있습니다.",
            ),
        ]

    blocks = []
    for heading, body in sections:
        blocks.append(
            "\n".join(
                [
                    '        <section class="section page-section body-section">',
                    f"          <h2>{html.escape(heading)}</h2>",
                    f"          <p>{html.escape(body)}</p>",
                    "        </section>",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_default_content(page: dict[str, Any]) -> str:
    title = str(page["title"])
    slug_source = str(page.get("slug_source") or page["slug"])
    region_type = str(page.get("region_type", ""))
    profile = content_profile(region_type)
    title_suffix = str(page.get("title_suffix") or "").strip()
    parent_depth = int(page.get("_parent_depth", 0) or 0)
    children_count = int(page.get("_children_count", 0) or 0)
    strategy_key = "|".join(
        [
            str(page["slug"]),
            region_type,
            title_suffix,
            str(parent_depth),
            str(children_count),
        ]
    )
    digest = hashlib.sha256(strategy_key.encode("utf-8")).hexdigest()
    strategy_index = int(digest[:8], 16) % len(CONTENT_STRATEGIES)
    strategy = CONTENT_STRATEGIES[strategy_index]

    context = {
        "title": title,
        "slug_source": slug_source,
        "region_type": region_type,
        "title_suffix": title_suffix or "지역 학습 정보",
        "parent_depth": str(parent_depth),
        "children_count": str(children_count),
        "focus": profile["focus"],
        "scope": profile["scope"],
        "rhythm": profile["rhythm"],
        "detail": profile["detail"],
        "compare": profile["compare"],
        "guideline": profile["guideline"],
        "routine": profile["routine"],
        "exam": profile["exam"],
        "habit": profile["habit"],
        "warning": profile["warning"],
        "question": profile["question"],
        "answer": profile["answer"],
        "strategy_id": f"strategy-{strategy_index + 1:02d}",
        "digest": digest,
    }
    renderers = strategic_renderers(profile)
    blocks = [f"          <!-- content-strategy: {context['strategy_id']} -->"]
    blocks.extend(renderers[token](context) for token in strategy)
    return "\n".join(blocks)


CONTENT_STRUCTURE_PATTERNS: list[tuple[str, ...]] = [
    ("h2_0", "p_intro", "h2_1", "p_context", "h2_2", "p_links"),
    ("p_intro", "h2_0", "p_context", "ul_focus", "h2_1", "p_flow"),
    ("h2_0", "p_intro", "blockquote", "h2_1", "p_context", "h2_2", "p_links"),
    ("h2_0", "ul_focus", "p_intro", "h2_1", "p_context"),
    ("p_intro", "h3_0", "p_context", "h2_0", "ul_check", "h2_1", "p_links"),
    ("h2_0", "p_intro", "table", "h2_1", "p_flow"),
    ("h2_0", "p_intro", "h3_0", "p_context", "h2_1", "p_links"),
    ("p_intro", "ul_focus", "h2_0", "p_context", "blockquote", "h2_1", "p_links"),
    ("aside", "h2_0", "p_intro", "h2_1", "ul_check", "h2_2", "p_flow"),
    ("h2_0", "p_intro", "h2_1", "p_context", "aside", "h2_2", "ul_focus", "h2_3", "p_links"),
    ("p_intro", "blockquote", "h2_0", "p_context", "h3_0", "p_flow", "h2_1", "p_links"),
    ("h2_0", "table", "p_intro", "h2_1", "p_context", "ul_check"),
    ("h2_0", "p_intro", "h2_1", "ul_focus", "h2_2", "p_context", "h2_3", "p_links"),
    ("p_intro", "h2_0", "aside", "h2_1", "p_context", "h3_1", "p_flow", "h2_2", "p_links"),
    ("h2_0", "p_intro", "ul_focus", "h2_1", "p_context", "table", "h2_2", "p_links"),
    ("p_intro", "h2_0", "p_context", "h2_1", "blockquote", "h2_2", "ul_check", "h2_3", "p_links"),
]


CONTENT_STRATEGIES: list[tuple[str, ...]] = [
    ("h2_a", "intro", "h2_b", "develop", "ol", "h2_c", "close"),
    ("intro", "h2_a", "ul", "develop", "details", "h2_b", "close"),
    ("h2_a", "figure", "intro", "h2_b", "develop", "blockquote", "close"),
    ("intro", "aside", "h2_a", "develop", "h3_a", "dl", "h2_b", "close"),
    ("h2_a", "intro", "table", "h2_b", "develop", "h2_c", "figure", "close"),
    ("intro", "h2_a", "details", "develop", "h2_b", "ul", "close"),
    ("h2_a", "ol", "intro", "h2_b", "develop", "aside", "h2_c", "close"),
    ("figure", "intro", "h2_a", "develop", "dl", "h2_b", "close"),
    ("h2_a", "intro", "blockquote", "h3_a", "develop", "h2_b", "ol", "close"),
    ("intro", "h2_a", "develop", "h2_b", "table", "h2_c", "close"),
    ("h2_a", "details", "intro", "h2_b", "ul", "develop", "close"),
    ("intro", "h3_a", "develop", "h2_a", "figure", "h2_b", "close"),
    ("h2_a", "intro", "dl", "h2_b", "develop", "details", "h2_c", "close"),
    ("aside", "intro", "h2_a", "ol", "h2_b", "develop", "close"),
    ("h2_a", "intro", "h2_b", "blockquote", "develop", "ul", "h2_c", "close"),
    ("intro", "table", "h2_a", "develop", "h2_b", "details", "close"),
    ("h2_a", "figure", "h2_b", "intro", "develop", "h3_a", "close"),
    ("intro", "h2_a", "dl", "develop", "h2_b", "ol", "h2_c", "close"),
    ("h2_a", "intro", "aside", "h2_b", "develop", "table", "close"),
    ("details", "intro", "h2_a", "develop", "h2_b", "figure", "close"),
    ("h2_a", "intro", "ul", "h2_b", "develop", "h3_a", "dl", "close"),
    ("intro", "blockquote", "h2_a", "develop", "details", "h2_b", "ol", "close"),
    ("h2_a", "table", "intro", "h2_b", "develop", "ul", "h2_c", "close"),
    ("intro", "h2_a", "figure", "develop", "h2_b", "aside", "close"),
]


INTRO_FRAMES = [
    "{title} 페이지는 {slug_source}를 기준으로 {focus}을 살펴보되, {scope}을 먼저 잡고 {rhythm}으로 이어 보는 페이지입니다.",
    "{title}에서는 {slug_source}의 범위를 출발점으로 삼아 {focus}과 {detail}을 함께 정리합니다.",
    "{slug_source}를 찾는 사용자는 {scope}뿐 아니라 {rhythm}과 연결된 주변 페이지 흐름도 함께 볼 필요가 있습니다.",
    "{title} 페이지는 {title_suffix}이라는 제목 문구에 맞춰 {focus}을 구조적으로 읽을 수 있게 만든 페이지입니다.",
    "{slug_source} 페이지는 {compare}를 확인하기 전에 현재 범위가 어디에 놓이는지 잡아 주는 기준점입니다.",
    "{title} 페이지의 도입부에서는 {guideline} 현재 페이지 깊이 {parent_depth}단계와 하위 연결 {children_count}개도 함께 참고할 수 있습니다.",
    "{slug_source}를 살펴볼 때는 {habit} 이 흐름을 {title_suffix} 문구와 연결하면 페이지의 목적이 더 분명해집니다.",
    "{title} 페이지는 {exam} 이 기준을 바탕으로 {focus}을 읽도록 구성된 상세 페이지입니다.",
]

INTRO_TEMPLATES: tuple[str, ...] = tuple(
    f"{frame} {tail}"
    for tail in [
        "상위 범위와 세부 항목을 나누어 보면 필요한 정보의 위치가 더 분명해집니다.",
        "현재 페이지의 역할을 이해하면 주변 링크를 따라갈 때 흐름이 끊기지 않습니다.",
        "처음에는 넓은 기준을 확인하고, 이후에는 생활권과 과목 흐름을 좁혀 보는 방식이 알맞습니다.",
        "같은 키워드라도 연결된 지역과 학년 맥락에 따라 읽어야 할 포인트가 달라질 수 있습니다.",
        "페이지 안의 구조는 단순 설명보다 다음에 볼 범위를 정리하는 데 초점을 둡니다.",
        "주요 기준을 먼저 확인하면 하위 페이지나 형제 페이지로 이동할 때 비교가 쉬워집니다.",
        "검색어 자체보다 어떤 범위의 정보인지 파악하는 일이 먼저 필요합니다.",
        "지역과 과목, 학년의 연결을 함께 보면 페이지의 쓰임을 더 차분히 이해할 수 있습니다.",
        "여러 페이지를 흩어 보지 않도록 현재 범위와 주변 범위를 함께 정리했습니다.",
        "상세 정보를 보기 전 기준점을 세우면 이후 페이지 이동이 더 자연스럽습니다.",
    ]
    for frame in INTRO_FRAMES
)


DEVELOP_FRAMES = [
    "{slug_source} 관련 내용은 {detail}을 중심으로 보면 좋습니다.",
    "{title}의 중간 흐름에서는 {rhythm}과 {scope}을 따로 떼어 보지 않는 편이 자연스럽습니다.",
    "parent depth {parent_depth} 단계에 있는 {slug_source}는 상위 맥락과 현재 범위를 같이 읽어야 합니다.",
    "{children_count}개의 하위 연결을 가진 페이지라면 {detail}을 기준으로 탐색 순서를 잡는 것이 좋습니다.",
    "{title_suffix} 문구가 붙은 {slug_source}는 {focus} 안에서 어떤 세부 주제를 맡는지 확인하는 데 의미가 있습니다.",
    "{slug_source}의 실제 활용은 {routine} 이 흐름을 기준으로 {scope}을 다시 확인할 때 더 구체적입니다.",
    "{title} 페이지에서는 {exam} 이 내용이 {rhythm}과 연결되면서 시험 전후의 준비 순서를 잡아 줍니다.",
    "{slug_source}를 중심으로 볼 때 {warning} 그래서 {detail}을 따라가며 주변 페이지를 함께 확인하는 과정이 필요합니다.",
]

DEVELOP_TEMPLATES: tuple[str, ...] = tuple(
    f"{frame} {tail}"
    for tail in [
        "이 기준을 두면 지역 흐름과 학습 주제가 한꺼번에 섞이지 않고 순서대로 정리됩니다.",
        "특히 parent depth {parent_depth} 단계의 페이지에서는 상위 맥락과 현재 범위를 함께 확인하는 편이 좋습니다.",
        "하위 페이지가 {children_count}개 연결된 경우에는 먼저 큰 묶음을 보고 세부 항목으로 내려가는 흐름이 안정적입니다.",
        "문장 하나보다 링크 구조와 페이지 위치를 함께 보면 실제 탐색 경로가 더 잘 보입니다.",
        "주변 페이지와 비교하면 같은 주제 안에서도 지역, 과목, 학년 차이가 자연스럽게 드러납니다.",
        "현재 페이지의 제목 문구인 {title_suffix}도 읽는 방향을 잡는 보조 기준으로 활용할 수 있습니다.",
        "너무 빠르게 세부 항목으로 들어가기보다 현재 페이지가 담당하는 범위를 먼저 확인하는 편이 좋습니다.",
        "상위와 하위 정보를 번갈아 보면 같은 키워드의 의미가 더 입체적으로 정리됩니다.",
        "연결된 페이지 수와 깊이를 함께 보면 단순 목록이 아니라 계층형 구조로 이해할 수 있습니다.",
        "페이지마다 같은 설명을 반복하기보다 위치와 연결 관계를 중심으로 읽는 것이 핵심입니다.",
    ]
    for frame in DEVELOP_FRAMES
)


CLOSING_FRAMES = [
    "마지막으로 {title} 페이지는 {compare}를 확인하기 위한 연결 지점으로 볼 수 있습니다.",
    "{slug_source}에서 더 살펴볼 내용은 {detail}을 기준으로 다음 페이지에서 이어집니다.",
    "{title_suffix} 흐름을 마무리할 때는 {focus}과 주변 링크를 함께 보는 것이 좋습니다.",
    "현재 페이지는 {rhythm}을 정리한 뒤 상위와 하위 페이지를 이어 주는 역할을 합니다.",
    "{slug_source}의 내용을 다 본 뒤에는 {scope}과 {compare}를 다시 비교해 볼 수 있습니다.",
    "{title} 페이지를 정리할 때는 {habit} 이 기준이 다음 페이지 선택에도 이어집니다.",
    "{slug_source}에서 주의할 점은 {warning} 따라서 현재 페이지를 본 뒤 관련 링크를 통해 범위를 다시 점검하는 편이 좋습니다.",
    "{title_suffix} 내용을 마무리하려면 {question}에 대한 답을 확인하고, {answer}",
]

CLOSING_TEMPLATES: tuple[str, ...] = tuple(
    f"{frame} {tail}"
    for tail in [
        "아래 내부 링크를 따라가면 현재 범위에서 다음 범위로 자연스럽게 이동할 수 있습니다.",
        "상위 페이지와 형제 페이지를 함께 보면 같은 주제를 다른 기준으로 다시 확인할 수 있습니다.",
        "하위 항목이 있다면 세부 페이지에서 더 좁은 생활권과 학습 기준을 이어서 볼 수 있습니다.",
        "이 페이지는 특정 행동을 유도하기보다 구조를 이해하고 비교할 기준을 남기는 역할을 합니다.",
        "필요한 범위를 좁혀 가며 읽으면 검색어와 실제 페이지 구조가 더 잘 맞물립니다.",
        "관련 페이지를 함께 확인하면 단일 페이지보다 전체 사이트 안의 위치가 더 분명해집니다.",
        "현재 페이지에서 출발해 상위, 하위, 형제 페이지를 순서대로 살펴보면 흐름이 안정됩니다.",
        "같은 지역이나 과목 안에서도 다른 단계의 페이지를 함께 보면 차이를 비교하기 좋습니다.",
        "페이지 간 이동은 넓은 범위에서 좁은 범위로 내려가도록 설계되어 있습니다.",
        "현재 내용을 기준점으로 삼으면 다음 페이지를 선택할 때 불필요한 이동을 줄일 수 있습니다.",
    ]
    for frame in CLOSING_FRAMES
)


HEADING_TEMPLATES: tuple[str, ...] = (
    "{slug_source} 기준 정리",
    "{focus} 살펴보기",
    "{rhythm} 흐름",
    "{scope} 확인",
    "{title_suffix} 읽는 기준",
    "상위 범위와 현재 페이지",
    "하위 항목으로 이어지는 길",
    "주변 페이지 비교",
    "학습 정보의 위치",
    "연결 구조 활용",
    "세부 기준 나누기",
    "페이지 깊이와 범위",
    "관련 주제 확장",
    "생활권과 학습 맥락",
    "과목과 학년의 접점",
    "현재 페이지의 역할",
    "다음에 볼 항목",
    "비교해서 볼 기준",
    "내부 링크 활용",
    "정보 흐름 정리",
    "{slug_source} 주변 맥락",
    "{compare} 비교",
    "{detail} 방식",
    "탐색 순서 잡기",
)


def content_profile(region_type: str) -> dict[str, Any]:
    if region_type in {"province", "city"}:
        return {
            "focus": "광역 단위의 지역 학습 환경",
            "scope": "시군구별 학교 분포와 생활권 이동",
            "rhythm": "지역별 공부 흐름",
            "detail": "하위 지역을 단계적으로 살펴보는 방식",
            "compare": "넓은 지역과 세부 생활권의 차이",
            "guideline": "광역 페이지에서는 생활권을 먼저 나누고, 그 안에서 과목 선택과 학년별 준비 방향을 연결해 보는 것이 좋습니다.",
            "routine": "시군구별 학교 분포, 이동 동선, 주요 생활권을 차례로 보면 큰 지역 안에서도 공부 리듬의 차이가 보입니다.",
            "exam": "시험 준비는 지역 전체의 흐름보다 실제로 다니는 학교와 가까운 생활권의 일정에 맞춰 다시 좁혀 보는 과정이 필요합니다.",
            "habit": "넓은 지역을 볼 때도 매일 반복할 수 있는 복습 시간, 이동 후 집중 시간, 과목별 점검 순서를 함께 생각해야 합니다.",
            "warning": "광역 키워드만 보고 판단하면 세부 지역의 학교 흐름과 생활 반경 차이를 놓치기 쉽습니다.",
            "question": "이 지역에서 먼저 볼 기준은 무엇인가요?",
            "answer": "상위 지역의 전체 흐름을 본 뒤 시군구, 동, 과목, 학년 페이지로 내려가며 범위를 좁히는 방식이 안정적입니다.",
            "headings": ["학습 환경 살펴보기", "지역별 공부 흐름", "하위 지역 연결", "과목과 학년 확장", "생활권 비교"],
            "subheadings": ["넓은 지역에서 볼 기준", "세부 페이지로 이어지는 흐름"],
        }
    if region_type == "district":
        return {
            "focus": "시군구 생활권과 학교 흐름",
            "scope": "학교 분포, 주변 동네, 주요 이동 동선",
            "rhythm": "생활권 안에서 반복되는 학습 일정",
            "detail": "동네와 인접 지역을 함께 보는 방식",
            "compare": "상위 지역과 하위 생활권의 차이",
            "guideline": "시군구 단위에서는 통학권, 학교생활, 시험 준비 흐름을 함께 놓고 지역 내 학습 루틴을 읽어야 합니다.",
            "routine": "학교와 집 사이의 이동 시간, 방과 후 머무는 장소, 주말 복습 가능 시간을 나누면 현실적인 학습 흐름이 보입니다.",
            "exam": "내신 준비는 학교별 진도와 수행평가 일정에 따라 달라지므로 같은 구 안에서도 세부 생활권을 다시 확인하는 편이 좋습니다.",
            "habit": "지역 안에서 반복되는 일정이 안정되면 과목별 복습, 오답 확인, 시험 전 점검 순서를 유지하기 쉬워집니다.",
            "warning": "같은 시군구라도 통학 동선이 다르면 하교 후 사용할 수 있는 시간이 크게 달라질 수 있습니다.",
            "question": "시군구 페이지에서 가장 먼저 확인할 것은 무엇인가요?",
            "answer": "학교 분포와 주요 생활권을 먼저 보고, 이후 동네와 과목 페이지로 내려가며 실제 공부 루틴을 맞춰 보는 것이 좋습니다.",
            "headings": ["생활권과 학교 흐름", "지역 안에서 볼 기준", "상위와 하위 연결", "인접 지역 비교", "학습 계획 정리"],
            "subheadings": ["생활권을 나누어 보는 이유", "주변 페이지 활용"],
        }
    if region_type == "dong":
        return {
            "focus": "동네 생활권의 공부 습관",
            "scope": "집과 학교의 거리, 방과 후 이동 시간",
            "rhythm": "일상 속 복습 루틴",
            "detail": "가까운 생활권에서 반복 가능한 기준",
            "compare": "같은 상위 지역 안의 주변 동네",
            "guideline": "동 단위 페이지에서는 생활 반경, 하교 후 시간관리, 공부 습관, 반복 학습 환경을 구체적으로 보는 것이 중요합니다.",
            "routine": "집, 학교, 이동 경로가 가까울수록 짧은 복습을 여러 번 배치하거나 과목별 시간을 나누기 쉽습니다.",
            "exam": "시험 전에는 평소 이동 시간과 저녁 복습 시간을 기준으로 암기, 문제풀이, 오답 정리의 순서를 정해야 합니다.",
            "habit": "작은 생활권에서는 매일 같은 시간에 책상에 앉는 습관과 짧은 점검 루틴이 학습 안정성을 크게 좌우합니다.",
            "warning": "가까운 지역이라고 해도 하교 후 일정과 주변 환경이 다르면 반복 학습 조건이 달라질 수 있습니다.",
            "question": "동네 페이지는 어떤 기준으로 읽어야 하나요?",
            "answer": "생활 반경 안에서 실제로 반복할 수 있는 시간과 장소를 먼저 보고, 과목이나 학년 페이지와 연결해 확인하면 좋습니다.",
            "headings": ["공부 습관과 통학 환경", "일상 속 학습 리듬", "주변 페이지 연결", "생활권 기준", "복습 흐름"],
            "subheadings": ["작은 생활권에서 볼 점", "통학 환경과 학습 시간"],
        }
    if region_type == "subject":
        return {
            "focus": "과목별 학습 흐름",
            "scope": "개념 이해, 문제 적용, 오답 정리",
            "rhythm": "단원별 복습과 반복 점검",
            "detail": "지역과 학년 정보를 함께 보는 방식",
            "compare": "같은 지역의 다른 과목과 학년",
            "guideline": "과목 페이지에서는 개념 이해, 문제 적용, 오답 정리, 시험 대비 흐름이 끊기지 않도록 순서를 잡는 것이 핵심입니다.",
            "routine": "개념을 확인한 뒤 대표 문제를 풀고, 틀린 이유를 적은 다음 비슷한 유형을 다시 점검하는 루틴이 필요합니다.",
            "exam": "시험 준비에서는 범위표, 학교 진도, 자주 틀리는 유형을 함께 보며 단원별 우선순위를 정해야 합니다.",
            "habit": "과목 학습은 긴 시간보다 짧아도 꾸준한 개념 복습과 오답 재확인이 누적될 때 안정적으로 쌓입니다.",
            "warning": "문제 수만 늘리면 개념과 오답 원인이 정리되지 않아 같은 유형에서 다시 흔들릴 수 있습니다.",
            "question": "과목 페이지에서 확인할 핵심은 무엇인가요?",
            "answer": "개념, 문제 적용, 오답 정리, 시험 범위 연결을 순서대로 보고 지역과 학년 페이지로 확장하는 것입니다.",
            "headings": ["과목별 학습 흐름", "개념 정리와 복습", "연관 과목 연결", "학년별 차이", "지역별 준비 방향"],
            "subheadings": ["과목 흐름을 나누어 보는 기준", "진도와 복습의 균형"],
        }
    if region_type == "grade":
        return {
            "focus": "학년별 공부 방향",
            "scope": "개념 깊이, 복습 주기, 시험 준비 방식",
            "rhythm": "학년 단계에 맞춘 학습 계획",
            "detail": "과목 페이지와 함께 확장하는 방식",
            "compare": "초등, 중등, 고등 단계별 차이",
            "guideline": "학년 페이지에서는 학년별 변화, 내신 준비, 자기주도학습, 학습 습관을 단계별로 나누어 보는 것이 좋습니다.",
            "routine": "학년이 올라갈수록 복습 주기, 과목별 우선순위, 시험 전 점검 방식이 달라지므로 생활 루틴도 함께 조정해야 합니다.",
            "exam": "내신 준비는 평소 수업 이해, 수행평가 관리, 시험 범위 정리, 오답 반복의 순서가 연결되어야 합니다.",
            "habit": "자기주도학습은 계획표 자체보다 지킬 수 있는 공부 시간과 확인 가능한 복습 기록에서 시작됩니다.",
            "warning": "학년이 바뀌었는데 이전 방식만 유지하면 과목 수와 평가 방식 변화에 늦게 반응할 수 있습니다.",
            "question": "학년별 페이지는 어떻게 활용하나요?",
            "answer": "현재 학년의 평가 방식과 생활 리듬을 먼저 보고, 과목 페이지를 함께 확인해 준비 방향을 구체화하면 됩니다.",
            "headings": ["학년별 공부 방향", "학교 일정과 학습 계획", "과목 페이지 확장", "단계별 기준", "준비 흐름"],
            "subheadings": ["학년 단계별로 달라지는 점", "시험 일정과 복습 주기"],
        }
    return {
        "focus": "학교생활과 내신 흐름",
        "scope": "수업 진도, 수행평가, 시험 범위",
        "rhythm": "학교 일정에 맞춘 복습 계획",
        "detail": "주변 지역과 과목 페이지를 함께 보는 방식",
        "compare": "학교 중심 정보와 지역 정보의 차이",
        "guideline": "학교 페이지에서는 학교생활, 수행평가, 내신 흐름, 시험 전 루틴을 함께 정리하는 것이 중요합니다.",
        "routine": "수업 진도와 과제 흐름을 매주 확인하고, 수행평가와 지필평가 준비를 분리해 관리하면 부담이 줄어듭니다.",
        "exam": "시험 전에는 범위 확인, 단원별 개념 정리, 기출 유형 점검, 오답 재확인을 일정에 맞춰 반복해야 합니다.",
        "habit": "학교생활과 학습 습관이 이어지려면 수업 후 바로 정리하는 짧은 기록과 주말 누적 복습이 필요합니다.",
        "warning": "학교명만 보고 접근하면 실제 학사 일정, 평가 방식, 주변 생활권의 차이를 놓칠 수 있습니다.",
        "question": "학교 페이지에서 중점적으로 볼 내용은 무엇인가요?",
        "answer": "수행평가와 내신 흐름을 기준으로 학교생활과 과목별 준비를 연결해 보는 것이 가장 실용적입니다.",
        "headings": ["학교생활과 내신 흐름", "학교 주변 학습 환경", "관련 페이지 활용", "시험 범위 정리", "지역 정보 연결"],
        "subheadings": ["학교명을 기준으로 볼 점", "내신 흐름과 생활권"],
    }


def render_h2(text: str) -> str:
    return f"          <h2>{html.escape(text)}</h2>"


def render_h3(text: str) -> str:
    return f"          <h3>{html.escape(text)}</h3>"


def render_paragraph(text: str) -> str:
    return f"          <p>{html.escape(text)}</p>"


def render_intro_paragraph(data: dict[str, str]) -> str:
    return render_paragraph(
        f"{data['title']}은 {data['slug_source']}를 기준으로 {data['focus']}을 살펴보는 페이지입니다. "
        f"{data['scope']}을 함께 확인하면 단순한 키워드보다 실제 학습 환경에 가까운 흐름을 이해하기 좋습니다."
    )


def render_context_paragraph(data: dict[str, str]) -> str:
    return render_paragraph(
        f"{data['slug_source']} 관련 정보는 {data['rhythm']}을 중심으로 정리할 때 더 안정적으로 읽힙니다. "
        f"{data['detail']}을 적용하면 지역, 과목, 학년 정보를 한 번에 넓히기보다 필요한 범위를 차분히 좁혀 볼 수 있습니다."
    )


def render_flow_paragraph(data: dict[str, str]) -> str:
    return render_paragraph(
        f"{data['title']}에서는 {data['compare']}도 함께 살펴볼 수 있습니다. "
        "인접 페이지와 상위 페이지를 번갈아 확인하면 같은 주제라도 위치와 단계에 따라 달라지는 기준을 비교하기 쉽습니다."
    )


def render_links_paragraph(data: dict[str, str]) -> str:
    return render_paragraph(
        f"{data['slug_source']} 페이지의 내부 링크는 상위 지역, 하위 항목, 형제 페이지를 이어 주는 역할을 합니다. "
        "연결된 페이지를 따라가면 현재 페이지의 범위와 주변 주제를 구조적으로 확인할 수 있습니다."
    )


def render_focus_list(data: dict[str, str]) -> str:
    items = [
        f"{data['scope']} 확인",
        f"{data['rhythm']} 비교",
        f"{data['detail']} 적용",
    ]
    return render_list(items)


def render_check_list(data: dict[str, str]) -> str:
    items = [
        f"{data['slug_source']}의 기준 범위",
        f"{data['focus']}의 핵심 요소",
        "상위, 하위, 형제 페이지 연결",
    ]
    return render_list(items)


def render_list(items: list[str]) -> str:
    rows = [f"            <li>{html.escape(item)}</li>" for item in items]
    return "\n".join(["          <ul>", *rows, "          </ul>"])


def render_note(data: dict[str, str]) -> str:
    text = (
        f"{data['slug_source']}는 하나의 단일 정보보다 {data['focus']}과 연결 구조를 함께 볼 때 맥락이 또렷해집니다."
    )
    return f"          <blockquote>{html.escape(text)}</blockquote>"


def render_aside(data: dict[str, str]) -> str:
    text = (
        f"{data['title']}을 볼 때는 현재 페이지가 어떤 상위 범위와 연결되는지 함께 확인하면 페이지 이동 흐름을 잡기 쉽습니다."
    )
    return f'          <aside class="content-note">{html.escape(text)}</aside>'


def render_table(data: dict[str, str]) -> str:
    rows = [
        ("기준", f"{data['slug_source']}에서 보는 {data['focus']}"),
        ("확인 요소", f"{data['slug_source']} 관련 {data['scope']}"),
        ("연결 방향", f"{data['slug_source']} 페이지의 {data['detail']}"),
        ("학습 루틴", f"{data['slug_source']} 기준 {data.get('routine', data['rhythm'])}"),
        ("시험 준비", f"{data['title']}에서 확인할 {data.get('exam', data['compare'])}"),
    ]
    body = "\n".join(
        [
            "            <tr>"
            f"<th>{html.escape(label)}</th>"
            f"<td>{html.escape(value)}</td>"
            "</tr>"
            for label, value in rows
        ]
    )
    return "\n".join(
        [
            '          <table class="content-table">',
            "            <tbody>",
            body,
            "            </tbody>",
            "          </table>",
        ]
    )


def strategic_renderers(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "intro": render_strategy_intro,
        "develop": render_strategy_develop,
        "close": render_strategy_close,
        "h2_a": lambda data: render_strategy_h2(data, 0, profile),
        "h2_b": lambda data: render_strategy_h2(data, 1, profile),
        "h2_c": lambda data: render_strategy_h2(data, 2, profile),
        "h3_a": lambda data: render_strategy_h3(data, profile),
        "ul": render_strategy_ul,
        "ol": render_strategy_ol,
        "dl": render_strategy_dl,
        "details": render_strategy_details,
        "figure": render_strategy_figure,
        "blockquote": render_strategy_blockquote,
        "table": render_strategy_table,
        "aside": render_strategy_aside,
    }


def deterministic_index(data: dict[str, str], slot: str, size: int) -> int:
    key = f"{data['digest']}|{data['strategy_id']}|{slot}|{data['slug_source']}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % size


def fill_template(template: str, data: dict[str, str]) -> str:
    return template.format(**data)


def render_strategy_intro(data: dict[str, str]) -> str:
    index = deterministic_index(data, "intro", len(INTRO_TEMPLATES))
    text = (
        f"{fill_template(INTRO_TEMPLATES[index], data)} "
        f"{data['slug_source']}에서는 {sentence_fragment(data['guideline'])}를 기준으로 페이지 범위를 잡을 수 있습니다. "
        f"특히 {data['slug_source']} {data['title_suffix']} 흐름을 볼 때는 {sentence_fragment(data['habit'])}는 점을 함께 확인해야 합니다."
    )
    return render_paragraph(text)


def render_strategy_develop(data: dict[str, str]) -> str:
    index = deterministic_index(data, "develop", len(DEVELOP_TEMPLATES))
    text = (
        f"{fill_template(DEVELOP_TEMPLATES[index], data)} "
        f"{data['slug_source']} 기준으로 보면 {sentence_fragment(data['routine'])}는 점이 중요합니다. "
        f"{data['title']} 페이지에서는 {sentence_fragment(data['exam'])}는 흐름도 함께 이어집니다. "
        f"이 과정은 {data['slug_source']} 페이지가 상위와 하위 정보를 이어 주는 이유와도 연결됩니다."
    )
    return render_paragraph(text)


def render_strategy_close(data: dict[str, str]) -> str:
    index = deterministic_index(data, "close", len(CLOSING_TEMPLATES))
    text = (
        f"{fill_template(CLOSING_TEMPLATES[index], data)} "
        f"다만 {data['slug_source']}에서는 {sentence_fragment(data['warning'])}는 점을 놓치지 않아야 합니다. "
        f"따라서 {data['slug_source']} 페이지에서는 현재 범위를 확인한 뒤 내부 링크를 통해 필요한 세부 기준을 다시 살펴보는 흐름이 적절합니다."
    )
    return render_paragraph(text)


def render_strategy_h2(data: dict[str, str], offset: int, profile: dict[str, Any]) -> str:
    base = deterministic_index(data, f"h2-{offset}", len(HEADING_TEMPLATES))
    template = HEADING_TEMPLATES[(base + offset * 7) % len(HEADING_TEMPLATES)]
    text = fill_template(template, data)
    if offset == 0 and deterministic_index(data, "h2-prefix", 2) == 0:
        text = f"{data['slug_source']} {profile['headings'][offset]}"
    return render_h2(text)


def render_strategy_h3(data: dict[str, str], profile: dict[str, Any]) -> str:
    choices = [
        profile["subheadings"][0],
        profile["subheadings"][1],
        f"{data['title_suffix']} 세부 기준",
        f"{data['slug_source']} 연결 포인트",
    ]
    return render_h3(choices[deterministic_index(data, "h3", len(choices))])


def render_strategy_ul(data: dict[str, str]) -> str:
    items = [
        f"{data['scope']}을 먼저 확인하고 {data['title_suffix']} 흐름과 맞는지 점검",
        f"{data['rhythm']}을 주변 페이지와 비교하며 반복 가능한 학습 루틴 확인",
        f"{data['detail']}으로 다음 범위를 선택하고 상위, 하위, 형제 페이지 연결 확인",
        f"{data['warning']} 이 점을 피하기 위해 {data['slug_source']}의 실제 생활 흐름 재확인",
    ]
    return render_list(rotate_items(items, data, "ul"))


def render_strategy_ol(data: dict[str, str]) -> str:
    items = rotate_items(
        [
            f"{data['slug_source']}의 현재 범위와 parent depth {data['parent_depth']}단계 확인",
            f"{data['focus']}과 연결된 상위 페이지를 보고 큰 흐름 비교",
            f"{data['children_count']}개 하위 연결이 있다면 세부 항목에서 생활권과 과목 기준 확인",
            f"{data['title_suffix']} 흐름에 맞춰 시험 준비, 복습 루틴, 주변 페이지 점검",
            f"{data['warning']} 이 부분을 마지막에 다시 확인",
        ],
        data,
        "ol",
    )
    rows = [f"            <li>{html.escape(item)}</li>" for item in items]
    return "\n".join(["          <ol>", *rows, "          </ol>"])


def render_strategy_dl(data: dict[str, str]) -> str:
    rows = [
        ("페이지 범위", f"{data['slug_source']} / depth {data['parent_depth']} / 하위 페이지 {data['children_count']}개"),
        ("전개 기준", f"{data['title_suffix']} 문구를 중심으로 {data['focus']}을 확인"),
        ("학습 루틴", f"{data['slug_source']} 기준 {data['routine']}"),
        ("시험 준비", f"{data['title']} 기준 {data['exam']}"),
        ("주의할 점", f"{data['slug_source']}에서 {data['warning']}"),
    ]
    parts = ["          <dl>"]
    for term, desc in rotate_pairs(rows, data, "dl"):
        parts.append(f"            <dt>{html.escape(term)}</dt>")
        parts.append(f"            <dd>{html.escape(desc)}</dd>")
    parts.append("          </dl>")
    return "\n".join(parts)


def render_strategy_details(data: dict[str, str]) -> str:
    summary_options = [
        f"{data['slug_source']} 페이지 읽는 순서",
        f"{data['title_suffix']} 기준 펼쳐보기",
        f"{data['focus']} 확인 포인트",
    ]
    summary = summary_options[deterministic_index(data, "summary", len(summary_options))]
    text = (
        f"{data['slug_source']}는 {data['detail']}을 적용해 보면 상위 범위와 세부 페이지의 관계가 분명해집니다. "
        f"현재 깊이는 {data['parent_depth']}단계이며, 하위 연결은 {data['children_count']}개입니다. "
        f"{data['question']} {data['answer']} "
        f"추가로 {data['slug_source']}에서는 {sentence_fragment(data['warning'])}는 점을 확인하면 페이지를 이동할 때 기준이 흔들리지 않습니다."
    )
    return "\n".join(
        [
            "          <details>",
            f"            <summary>{html.escape(summary)}</summary>",
            f"            <p>{html.escape(text)}</p>",
            f"            <p><strong>Q.</strong> {html.escape(data['question'])}</p>",
            f"            <p><strong>A.</strong> {html.escape(data['answer'])}</p>",
            "          </details>",
        ]
    )


def render_strategy_figure(data: dict[str, str]) -> str:
    caption = (
        f"{data['slug_source']}의 핵심은 {data['focus']}에서 출발해 {data['compare']}를 비교하는 흐름입니다. "
        f"{data['scope']}을 확인한 뒤 {data['rhythm']}으로 이어 보면 페이지 안의 정보가 더 자연스럽게 연결됩니다."
    )
    return "\n".join(
        [
            '          <figure class="content-figure">',
            f"            <figcaption>{html.escape(caption)}</figcaption>",
            "          </figure>",
        ]
    )


def render_strategy_blockquote(data: dict[str, str]) -> str:
    text = (
        f"{data['title']} 페이지는 하나의 문장보다 {data['scope']}과 내부 링크의 방향을 함께 볼 때 의미가 또렷해집니다. "
        f"{data['guideline']} 이 기준을 놓치지 않으면 {data['slug_source']}에서 다음 페이지로 이동할 때 필요한 범위를 더 정확히 고를 수 있습니다."
    )
    return f"          <blockquote>{html.escape(text)}</blockquote>"


def render_strategy_table(data: dict[str, str]) -> str:
    return render_table(data)


def render_strategy_aside(data: dict[str, str]) -> str:
    text = (
        f"{data['slug_source']} 페이지는 {data['title_suffix']} 흐름과 페이지 깊이, 하위 연결 수를 함께 볼 때 구조를 더 쉽게 파악할 수 있습니다. "
        f"요약하면 {data['slug_source']}의 {data['focus']}을 기준으로 {sentence_fragment(data['routine'])}는 흐름과 "
        f"{sentence_fragment(data['exam'])}는 흐름을 함께 확인하는 것이 좋습니다."
    )
    return f'          <aside class="content-note">{html.escape(text)}</aside>'


def sentence_fragment(text: str) -> str:
    return text.rstrip(" .")


def rotate_items(items: list[str], data: dict[str, str], slot: str) -> list[str]:
    start = deterministic_index(data, slot, len(items))
    return items[start:] + items[:start]


def rotate_pairs(items: list[tuple[str, str]], data: dict[str, str], slot: str) -> list[tuple[str, str]]:
    start = deterministic_index(data, slot, len(items))
    return items[start:] + items[:start]


def build_page(page: dict[str, str]) -> str:
    canonical = page_url_from_path(page["path"])
    json_ld = json_ld_script(
        [
            website_schema(),
            webpage_schema(page["title"], page["description"], canonical),
            breadcrumb_schema(default_breadcrumb_items(page["title"], canonical)),
        ]
    )
    html_output = render_template(
        page["template"],
        {
            **static_context(page["path"]),
            "site_name": SITE_NAME,
            "title": page["title"],
            "description": page["description"],
            "canonical": canonical,
            "home_image_url": absolute_static_url("/static/images/classnova-main-hero.png"),
            "json_ld": json_ld,
            "year": str(date.today().year),
        },
    )

    output_path = OUTPUT_DIR / page["path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_output, encoding="utf-8", newline="\n")
    return page["path"]


def build_data_page(page: dict[str, Any], pages_by_slug: dict[str, dict[str, Any]]) -> str:
    slug = page["slug"]
    path = data_page_path(slug)
    thumbnail_src = select_thumbnail_path(slug)
    page_thumbnail_src = relative_static_path(thumbnail_src, path)
    page_fixed_image_src = relative_static_path(FIXED_PAGE_IMAGE, path)
    page["_parent_depth"] = parent_depth(page, pages_by_slug)
    page["_children_count"] = sum(1 for child in pages_by_slug.values() if child.get("parent") == slug)
    if not str(page.get("content") or "").strip():
        page["content"] = build_default_content(page)

    parent_slug = str(page.get("parent") or "")
    parent_page = pages_by_slug.get(parent_slug)

    parent_links = [page_link(parent_page)] if parent_page else []
    child_links = sort_links(
        [
            page_link(child)
            for child in pages_by_slug.values()
            if child.get("parent") == slug
        ]
    )
    sibling_links = sort_links(
        [
            page_link(sibling)
            for sibling in pages_by_slug.values()
            if parent_slug and sibling.get("parent") == parent_slug and sibling["slug"] != slug
        ]
    )

    explicit_related = page.get("related") or page.get("links", {}).get("related", [])
    related_links = [
        {"title": link["title"], "url": link["url"]}
        for link in explicit_related
        if isinstance(link, dict) and link.get("title") and link.get("url")
    ]
    canonical = page_url_from_path(path)
    description = page_description(page)
    page_seo_title = seo_title(str(page["title"]))
    json_ld = json_ld_script(
        [
            website_schema(),
            webpage_schema(page_seo_title, description, canonical),
            breadcrumb_schema(breadcrumb_items_from_parent(page, pages_by_slug)),
        ]
    )

    html_output = render_template(
        "page.html",
        {
            **static_context(path),
            "site_name": SITE_NAME,
            "title": page_seo_title,
            "description": description,
            "canonical": canonical,
            "json_ld": json_ld,
            "thumbnail_url": absolute_static_url(thumbnail_src),
            "thumbnail_src": page_thumbnail_src,
            "thumbnail_alt": f"{page['title']} 대표 이미지",
            "fixed_image_src": page_fixed_image_src,
            "fixed_image_alt": f"{page['title']} 학습 이미지",
            "h1": page["title"],
            "summary": page_summary(page),
            "content": str(page["content"]),
            "breadcrumb": build_breadcrumb_from_parent(page, pages_by_slug),
            "parent_section": build_link_section(
                "지역 상위 흐름",
                "현재 페이지가 속한 더 넓은 지역과 학습 범위를 확인할 수 있습니다.",
                parent_links,
            ),
            "child_section": build_link_section(
                "이 지역의 세부 학습 페이지",
                "현재 지역에서 이어지는 세부 지역, 과목, 학년별 학습 페이지입니다.",
                child_links,
            ),
            "sibling_section": build_link_section(
                "주변 지역 학습 페이지",
                "현재 지역과 같은 상위 범위에 있는 주변 지역 페이지입니다.",
                sibling_links,
            ),
            "related_section": build_link_section(
                "함께 볼 만한 학습 페이지",
                "지역, 과목, 학년 흐름을 함께 비교해 보기 좋은 연결 페이지입니다.",
                related_links,
            ),
            "year": str(date.today().year),
        },
    )

    output_path = OUTPUT_DIR / path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_output, encoding="utf-8", newline="\n")
    return path


def parent_depth(page: dict[str, Any], pages_by_slug: dict[str, dict[str, Any]]) -> int:
    depth = 0
    seen: set[str] = set()
    current = page
    while current.get("parent"):
        parent_slug = str(current["parent"])
        if parent_slug in seen or parent_slug not in pages_by_slug:
            break
        seen.add(parent_slug)
        depth += 1
        current = pages_by_slug[parent_slug]
    return depth


def build_robots() -> None:
    robots = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {SITE_URL}/sitemap.xml",
            "",
        ]
    )
    (OUTPUT_DIR / "robots.txt").write_text(robots, encoding="utf-8", newline="\n")


def build_sitemap(paths: list[str]) -> None:
    today = date.today().isoformat()
    urls = []
    for path in paths:
        priority = "1.0" if path == "index.html" else "0.8"
        urls.append(
            "\n".join(
                [
                    "  <url>",
                    f"    <loc>{html.escape(page_url_from_path(path))}</loc>",
                    f"    <lastmod>{today}</lastmod>",
                    "    <changefreq>weekly</changefreq>",
                    f"    <priority>{priority}</priority>",
                    "  </url>",
                ]
            )
        )

    sitemap = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *urls,
            "</urlset>",
            "",
        ]
    )
    (OUTPUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8", newline="\n")


def build_manifest() -> None:
    manifest = {
        "name": SITE_NAME,
        "short_name": SITE_NAME,
        "description": "강원, 인천, 충청 지역 과외 정보 사이트",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "icons": [
            {
                "src": "static/images/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "static/images/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_404_page() -> None:
    canonical = f"{SITE_URL}/404.html"
    json_ld = json_ld_script(
        [
            website_schema(),
            webpage_schema("페이지를 찾을 수 없습니다 | CLASSNOVA", "요청한 페이지를 찾을 수 없습니다.", canonical),
            breadcrumb_schema(default_breadcrumb_items("페이지를 찾을 수 없습니다", canonical)),
        ]
    )
    html_output = render_template(
        "404.html",
        {
            **static_context("404.html"),
            "canonical": canonical,
            "json_ld": json_ld,
            "year": str(date.today().year),
        },
    )
    (OUTPUT_DIR / "404.html").write_text(html_output, encoding="utf-8", newline="\n")


def load_json_pages(path: Any, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"{label} must contain a list of page objects.")
    return data


def load_data_pages() -> list[dict[str, Any]]:
    generated_pages = load_json_pages(GENERATED_PAGES_PATH, "pages_generated.json")
    if generated_pages:
        return generated_pages
    return load_json_pages(SAMPLE_PAGES_PATH, "pages_sample.json")


def find_duplicate_slugs(pages: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for page in pages:
        slug = str(page.get("slug", "")).strip()
        if slug in seen:
            duplicates.add(slug)
        seen.add(slug)
    return sorted(duplicates)


def validate_data(pages: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    slugs = {str(page.get("slug", "")).strip() for page in pages if str(page.get("slug", "")).strip()}

    for index, page in enumerate(pages, start=1):
        title = str(page.get("title", "")).strip()
        slug = str(page.get("slug", "")).strip()
        parent = str(page.get("parent", "")).strip()
        title_suffix = str(page.get("title_suffix", "")).replace(" ", "")

        if not title:
            errors.append(f"row {index}: title is required.")
        if not slug:
            errors.append(f"row {index}: slug is required.")
        if parent == slug:
            errors.append(f"row {index}: parent must not equal slug '{slug}'.")
        if parent and parent not in slugs:
            errors.append(f"row {index}: parent '{parent}' does not match any slug.")
        if title_suffix and slug.endswith(title_suffix):
            errors.append(f"row {index}: slug must not include title_suffix '{page.get('title_suffix')}'.")

    for slug in find_duplicate_slugs(pages):
        errors.append(f"duplicate slug: {slug}")

    if GENERATED_PAGES_PATH.exists():
        parentless = {page["slug"] for page in pages if not str(page.get("parent", "")).strip()}
        unexpected = sorted(parentless - ROOT_SLUGS)
        missing_roots = sorted(ROOT_SLUGS - parentless)
        if unexpected:
            errors.append(f"unexpected root pages: {', '.join(unexpected)}")
        if missing_roots:
            errors.append(f"missing root pages: {', '.join(missing_roots)}")

    if errors:
        joined = "\n- ".join(errors)
        raise ValueError(f"Data validation failed:\n- {joined}")


def build_site() -> None:
    data_pages = load_data_pages()
    validate_data(data_pages)

    reset_output_directory()
    ensure_directories()
    copy_static_assets()

    generated_paths = []
    for page in DEFAULT_PAGES:
        generated_paths.append(build_page(page))

    pages_by_slug = {page["slug"]: page for page in data_pages}
    for page in data_pages:
        generated_paths.append(build_data_page(page, pages_by_slug))

    build_robots()
    build_sitemap(generated_paths)
    build_manifest()
    build_404_page()


if __name__ == "__main__":
    build_site()
    print(f"{SITE_NAME} static site generated at {OUTPUT_DIR}")
