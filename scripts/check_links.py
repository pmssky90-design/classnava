from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "pages_generated.json"
OUTPUT_DIR = ROOT_DIR / "output"
REPORTS_DIR = ROOT_DIR / "reports"
SITE_URL = "https://classnova.kr"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.links.append(value)


def load_pages() -> list[dict[str, object]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8-sig"))


def sitemap_urls() -> list[str]:
    root = ET.parse(OUTPUT_DIR / "sitemap.xml").getroot()
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text or "" for loc in root.findall("sm:url/sm:loc", namespace)]


def html_files() -> list[Path]:
    return sorted(OUTPUT_DIR.rglob("index.html"))


def href_to_output_path(href: str) -> Path | None:
    parsed = urlparse(href)
    if parsed.scheme and parsed.netloc != "classnova.kr":
        return None
    if parsed.scheme and parsed.netloc == "classnova.kr":
        href_path = parsed.path
    else:
        href_path = href.split("#", 1)[0].split("?", 1)[0]

    if not href_path or href_path.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    if href_path.startswith("/static/"):
        return OUTPUT_DIR / unquote(href_path.lstrip("/"))
    if not href_path.startswith("/"):
        return None
    if href_path == "/":
        return OUTPUT_DIR / "index.html"

    clean = unquote(href_path.strip("/"))
    if clean.endswith("/"):
        return OUTPUT_DIR / clean / "index.html"
    if clean.endswith(".html"):
        return OUTPUT_DIR / clean
    return OUTPUT_DIR / clean / "index.html"


def check_internal_links(files: list[Path]) -> list[str]:
    broken: list[str] = []
    for file_path in files:
        parser = LinkParser()
        parser.feed(file_path.read_text(encoding="utf-8"))
        for href in parser.links:
            target = href_to_output_path(href)
            if target is not None and not target.exists():
                relative_source = file_path.relative_to(OUTPUT_DIR).as_posix()
                broken.append(f"{relative_source}: {href} -> missing {target.relative_to(OUTPUT_DIR).as_posix()}")
    return broken


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    pages = load_pages()
    urls = sitemap_urls()
    files = html_files()
    broken_links = check_internal_links(files)

    expected_count = len(pages) + 1
    errors: list[str] = []
    if len(urls) != expected_count:
        errors.append(f"sitemap URL count mismatch: {len(urls)} != {expected_count}")
    if len(files) != expected_count:
        errors.append(f"HTML index file count mismatch: {len(files)} != {expected_count}")
    errors.extend(broken_links)

    report_lines = [
        "# Link Check Report",
        "",
        f"pages_generated 페이지 수: {len(pages)}",
        f"예상 URL/HTML 수: {expected_count}",
        f"sitemap URL 수: {len(urls)}",
        f"output index.html 수: {len(files)}",
        f"깨진 내부링크 수: {len(broken_links)}",
        f"전체 오류 수: {len(errors)}",
        "",
    ]
    if errors:
        report_lines.append("오류:")
        report_lines.extend(f"- {error}" for error in errors)
    else:
        report_lines.append("오류 없음")

    (REPORTS_DIR / "link_check_report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8-sig")

    print("CLASSNOVA link check complete")
    print(f"- pages_generated: {len(pages)}")
    print(f"- expected_url_count: {expected_count}")
    print(f"- sitemap_url_count: {len(urls)}")
    print(f"- output_index_count: {len(files)}")
    print(f"- broken_internal_links: {len(broken_links)}")
    print(f"- errors: {len(errors)}")

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
