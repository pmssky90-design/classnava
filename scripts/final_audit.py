from __future__ import annotations

import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "pages_generated.json"
OUTPUT_DIR = ROOT_DIR / "output"
REPORTS_DIR = ROOT_DIR / "reports"
REPORT_PATH = REPORTS_DIR / "final_audit_report.txt"
SIMILARITY_REPORT_PATH = REPORTS_DIR / "content_similarity_report.txt"
SITE_URL = "https://classnova.co.kr"


class AuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.links: dict[str, list[str]] = {}
        self.images: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.json_ld_blocks: list[str] = []
        self._in_json_ld = False
        self._json_ld_buffer: list[str] = []
        self.classes: dict[str, list[str]] = {}
        self.has_page_content = False
        self.in_page_content = False
        self.page_content_depth = 0
        self.page_content_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        classes = values.get("class", "").split()
        for class_name in classes:
            self.classes.setdefault(class_name, []).append(tag)
        if tag == "section" and "page-content" in classes:
            self.has_page_content = True
            self.in_page_content = True
            self.page_content_depth = 1
            return
        if self.in_page_content:
            self.page_content_depth += 1
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key:
                self.meta[key] = values.get("content", "")
        elif tag == "link":
            rel = values.get("rel", "")
            if rel:
                self.links.setdefault(rel, []).append(values.get("href", ""))
        elif tag == "img":
            self.images.append(values)
        elif tag == "script":
            self.scripts.append(values)
            self._in_json_ld = values.get("type") == "application/ld+json"
            if self._in_json_ld:
                self._json_ld_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and getattr(self, "_in_json_ld", False):
            self.json_ld_blocks.append("".join(getattr(self, "_json_ld_buffer", [])))
            self._in_json_ld = False
        if not self.in_page_content:
            return
        self.page_content_depth -= 1
        if self.page_content_depth <= 0:
            self.in_page_content = False

    def handle_data(self, data: str) -> None:
        if getattr(self, "_in_json_ld", False):
            self._json_ld_buffer.append(data)
        if self.in_page_content:
            self.page_content_text.append(data)


def load_pages() -> list[dict[str, object]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8-sig"))


def read_html(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_html(path: Path) -> AuditParser:
    parser = AuditParser()
    parser.feed(read_html(path))
    return parser


def detail_path(slug: str) -> Path:
    return OUTPUT_DIR / slug / "index.html"


def output_path_from_url(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc and parsed.netloc != "classnova.co.kr":
        return None
    path = parsed.path if parsed.scheme else url
    path = path.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    if path.startswith("/"):
        path = path[1:]
    return OUTPUT_DIR / unquote(path)


def sitemap_urls() -> list[str]:
    root = ET.parse(OUTPUT_DIR / "sitemap.xml").getroot()
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text or "" for loc in root.findall("sm:url/sm:loc", namespace)]


def css_for_search_thumbnail() -> str:
    css_path = OUTPUT_DIR / "static" / "css" / "style.css"
    if not css_path.exists():
        return ""
    css = css_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\.search-thumbnail\s*\{(?P<body>.*?)\}", css, flags=re.DOTALL)
    return match.group("body") if match else ""


def metric_from_similarity_report(key: str) -> float | None:
    if not SIMILARITY_REPORT_PATH.exists():
        return None
    text = SIMILARITY_REPORT_PATH.read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"^- {re.escape(key)}: ([0-9.]+)", text, flags=re.MULTILINE)
    return float(match.group(1)) if match else None


def json_ld_objects(parser: AuditParser) -> list[object]:
    objects: list[object] = []
    for block in parser.json_ld_blocks:
        try:
            loaded = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, list):
            objects.extend(loaded)
        else:
            objects.append(loaded)
    return objects


def has_jsonld_type(parser: AuditParser, schema_type: str) -> bool:
    for item in json_ld_objects(parser):
        if isinstance(item, dict) and item.get("@type") == schema_type:
            return True
    return False


def has_valid_breadcrumb(parser: AuditParser) -> bool:
    for item in json_ld_objects(parser):
        if not isinstance(item, dict) or item.get("@type") != "BreadcrumbList":
            continue
        elements = item.get("itemListElement")
        if not isinstance(elements, list) or not elements:
            return False
        for position, element in enumerate(elements, start=1):
            if not isinstance(element, dict):
                return False
            if element.get("@type") != "ListItem":
                return False
            if element.get("position") != position:
                return False
            if not element.get("name") or not element.get("item"):
                return False
        return True
    return False


def result_line(name: str, passed: bool, detail: str) -> str:
    return f"- {'PASS' if passed else 'FAIL'} | {name} | {detail}"


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    pages = load_pages()
    detail_files = [detail_path(str(page["slug"])) for page in pages]
    parsed_pages = [(page, path, parse_html(path)) for page, path in zip(pages, detail_files) if path.exists()]
    main_html = OUTPUT_DIR / "index.html"
    main_text = read_html(main_html) if main_html.exists() else ""
    all_html_files = sorted(OUTPUT_DIR.rglob("*.html"))
    parsed_html = [(path, parse_html(path)) for path in all_html_files]
    sitemap_count = len(sitemap_urls())
    index_count = len(list(OUTPUT_DIR.rglob("index.html")))
    expected_count = len(pages) + 1
    css_body = css_for_search_thumbnail()
    manifest_path = OUTPUT_DIR / "manifest.json"
    not_found_path = OUTPUT_DIR / "404.html"

    fixed_pages = [
        str(page["slug"])
        for page, _path, parser in parsed_pages
        if "fixed-page-image" in parser.classes
    ]
    missing_fixed = sorted({str(page["slug"]) for page in pages} - set(fixed_pages))

    missing_meta: list[str] = []
    missing_thumbnail_body: list[str] = []
    missing_page_content: list[str] = []
    image_missing: list[str] = []
    thumbnail_counter: Counter[str] = Counter()
    content_lengths: list[int] = []
    missing_img_dimensions: list[str] = []

    for page, _path, parser in parsed_pages:
        slug = str(page["slug"])
        og_image = parser.meta.get("og:image", "")
        twitter_image = parser.meta.get("twitter:image", "")
        image_src = next(iter(parser.links.get("image_src", [])), "")
        if not og_image or not twitter_image or not image_src:
            missing_meta.append(slug)
        for image_url in [og_image, twitter_image, image_src]:
            target = output_path_from_url(image_url)
            if target is not None and not target.exists():
                image_missing.append(f"{slug}: {image_url}")
        if og_image:
            thumbnail_counter[Path(urlparse(og_image).path).name] += 1

        fixed_imgs = [img for img in parser.images if img.get("src") == "/static/images/본문이미지1.png"]
        thumb_imgs = [img for img in parser.images if "search-thumbnail" in img.get("class", "").split()]
        if not thumb_imgs:
            missing_thumbnail_body.append(slug)
        for img in fixed_imgs + thumb_imgs:
            target = output_path_from_url(img.get("src", ""))
            if target is not None and not target.exists():
                image_missing.append(f"{slug}: {img.get('src', '')}")
        if not parser.has_page_content:
            missing_page_content.append(slug)
        content_text = re.sub(r"\s+", "", "".join(parser.page_content_text))
        content_lengths.append(len(content_text))

    missing_favicon_links: list[str] = []
    missing_json_ld: list[str] = []
    invalid_breadcrumb: list[str] = []
    scripts_without_defer: list[str] = []
    for path, parser in parsed_html:
        rels = {rel for rel in parser.links}
        if "icon" not in rels or "apple-touch-icon" not in rels:
            missing_favicon_links.append(path.relative_to(OUTPUT_DIR).as_posix())
        if not (has_jsonld_type(parser, "WebSite") and has_jsonld_type(parser, "WebPage") and has_jsonld_type(parser, "BreadcrumbList")):
            missing_json_ld.append(path.relative_to(OUTPUT_DIR).as_posix())
        if not has_valid_breadcrumb(parser):
            invalid_breadcrumb.append(path.relative_to(OUTPUT_DIR).as_posix())
        for img in parser.images:
            if not img.get("width") or not img.get("height"):
                missing_img_dimensions.append(f"{path.relative_to(OUTPUT_DIR).as_posix()}: {img.get('src', '')}")
        for script in parser.scripts:
            if script.get("src") and "defer" not in script:
                scripts_without_defer.append(f"{path.relative_to(OUTPUT_DIR).as_posix()}: {script.get('src', '')}")

    max_thumb_count = max(thumbnail_counter.values(), default=0)
    max_thumb_rate = max_thumb_count / len(pages) if pages else 0.0
    average_similarity = metric_from_similarity_report("average_similarity")
    average_content_length = sum(content_lengths) / len(content_lengths) if content_lengths else 0.0

    checks = [
        (
            "404.html exists",
            not_found_path.exists(),
            "exists" if not_found_path.exists() else "missing",
        ),
        (
            "manifest.json exists",
            manifest_path.exists(),
            "exists" if manifest_path.exists() else "missing",
        ),
        (
            "favicon links exist on HTML pages",
            len(missing_favicon_links) == 0,
            f"missing_favicon_links={len(missing_favicon_links)}",
        ),
        (
            "JSON-LD WebSite/WebPage/BreadcrumbList exists",
            len(missing_json_ld) == 0,
            f"missing_json_ld={len(missing_json_ld)}",
        ),
        (
            "BreadcrumbList JSON-LD is valid",
            len(invalid_breadcrumb) == 0,
            f"invalid_breadcrumb={len(invalid_breadcrumb)}",
        ),
        (
            "image width and height attributes exist",
            len(missing_img_dimensions) == 0,
            f"missing_img_dimensions={len(missing_img_dimensions)}",
        ),
        (
            "external JS uses defer",
            len(scripts_without_defer) == 0,
            f"scripts_without_defer={len(scripts_without_defer)}",
        ),
        (
            "detail pages include fixed-page-image",
            len(missing_fixed) == 0 and len(fixed_pages) == len(pages),
            f"{len(fixed_pages)}/{len(pages)} included; missing={len(missing_fixed)}",
        ),
        (
            "main index has no fixed-page-image",
            "fixed-page-image" not in main_text,
            "not found" if "fixed-page-image" not in main_text else "found",
        ),
        (
            "detail pages include og/twitter/image_src",
            len(missing_meta) == 0 and len(parsed_pages) == len(pages),
            f"missing_meta={len(missing_meta)}",
        ),
        (
            "thumbnail distribution across 20 images",
            len(thumbnail_counter) == 20 and max_thumb_rate < 0.10,
            f"used={len(thumbnail_counter)}/20; max_count={max_thumb_count}; max_rate={max_thumb_rate:.3f}",
        ),
        (
            "search-thumbnail CSS avoids display none and visibility hidden",
            "display:none" not in css_body.replace(" ", "").lower()
            and "visibility:hidden" not in css_body.replace(" ", "").lower(),
            "display:none/visibility:hidden not found",
        ),
        (
            "all image paths exist",
            len(image_missing) == 0,
            f"missing_images={len(image_missing)}",
        ),
        (
            "sitemap URL count matches output index count",
            sitemap_count == index_count == expected_count,
            f"sitemap={sitemap_count}; output_index={index_count}; expected={expected_count}",
        ),
        (
            "internal links broken count is zero",
            (REPORTS_DIR / "link_check_report.txt").exists()
            and "깨진 내부링크 수: 0" in (REPORTS_DIR / "link_check_report.txt").read_text(encoding="utf-8-sig", errors="replace"),
            "see reports/link_check_report.txt",
        ),
        (
            "detail pages include page-content",
            len(missing_page_content) == 0 and len(parsed_pages) == len(pages),
            f"missing_page_content={len(missing_page_content)}",
        ),
        (
            "average similarity <= 0.05",
            average_similarity is not None and average_similarity <= 0.05,
            f"average_similarity={average_similarity if average_similarity is not None else 'n/a'}",
        ),
        (
            "average page-content length >= 900 chars",
            average_content_length >= 900,
            f"average_page_content_length={average_content_length:.1f}",
        ),
    ]

    passed_all = all(passed for _name, passed, _detail in checks)
    lines = [
        "# CLASSNOVA Final Audit Report",
        "",
        f"overall: {'PASS' if passed_all else 'FAIL'}",
        f"detail_pages: {len(pages)}",
        f"parsed_detail_pages: {len(parsed_pages)}",
        f"average_page_content_length: {average_content_length:.1f}",
        "",
        "## Checks",
    ]
    lines.extend(result_line(name, passed, detail) for name, passed, detail in checks)
    lines.extend(["", "## Thumbnail Distribution"])
    for name, count in sorted(thumbnail_counter.items()):
        lines.append(f"- {name}: {count}")

    if (
        missing_fixed
        or missing_meta
        or missing_thumbnail_body
        or missing_page_content
        or image_missing
        or missing_favicon_links
        or missing_json_ld
        or invalid_breadcrumb
        or missing_img_dimensions
        or scripts_without_defer
    ):
        lines.extend(["", "## Fail Details"])
        if missing_favicon_links:
            lines.append(f"- missing_favicon_links_sample: {', '.join(missing_favicon_links[:20])}")
        if missing_json_ld:
            lines.append(f"- missing_json_ld_sample: {', '.join(missing_json_ld[:20])}")
        if invalid_breadcrumb:
            lines.append(f"- invalid_breadcrumb_sample: {', '.join(invalid_breadcrumb[:20])}")
        if missing_img_dimensions:
            lines.append(f"- missing_img_dimensions_sample: {'; '.join(missing_img_dimensions[:20])}")
        if scripts_without_defer:
            lines.append(f"- scripts_without_defer_sample: {'; '.join(scripts_without_defer[:20])}")
        if missing_fixed:
            lines.append(f"- missing_fixed_sample: {', '.join(missing_fixed[:20])}")
        if missing_meta:
            lines.append(f"- missing_meta_sample: {', '.join(missing_meta[:20])}")
        if missing_thumbnail_body:
            lines.append(f"- missing_search_thumbnail_sample: {', '.join(missing_thumbnail_body[:20])}")
        if missing_page_content:
            lines.append(f"- missing_page_content_sample: {', '.join(missing_page_content[:20])}")
        if image_missing:
            lines.append(f"- missing_image_sample: {'; '.join(image_missing[:20])}")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("CLASSNOVA final audit complete")
    print(f"- overall: {'PASS' if passed_all else 'FAIL'}")
    print(f"- report: {REPORT_PATH}")
    for name, passed, detail in checks:
        print(f"- {'PASS' if passed else 'FAIL'}: {name} ({detail})")

    if not passed_all:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
