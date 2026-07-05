from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
REPORTS_DIR = ROOT_DIR / "reports"
TXT_REPORT = REPORTS_DIR / "final_index_audit.txt"
CSV_REPORT = REPORTS_DIR / "final_index_audit.csv"
SITE_URL = "https://classnova.kr"
SITE_HOST = urlparse(SITE_URL).netloc

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
IGNORED_HTML = {"404.html"}
BODY_MIN_CRITICAL = 500
BODY_MIN_MEDIUM = 800
SIMILARITY_THRESHOLD = 0.75


@dataclass
class Issue:
    severity: str
    category: str
    file: str
    message: str


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.start_tags: Counter[str] = Counter()
        self.end_tags: Counter[str] = Counter()
        self.title_texts: list[str] = []
        self.meta: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.anchors: list[dict[str, str]] = []
        self.h1_texts: list[str] = []
        self.json_ld_blocks: list[str] = []
        self.body_text: list[str] = []
        self.page_content_text: list[str] = []
        self._stack: list[str] = []
        self._in_title = False
        self._in_body = False
        self._in_json_ld = False
        self._json_buffer: list[str] = []
        self._in_page_content = False
        self._page_content_depth = 0
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {name.lower(): value or "" for name, value in attrs}
        self.start_tags[tag] += 1
        self._stack.append(tag)

        if tag == "title":
            self._in_title = True
        elif tag == "body":
            self._in_body = True
        elif tag == "meta":
            self.meta.append(values)
        elif tag == "link":
            self.links.append(values)
        elif tag == "img":
            self.images.append(values)
        elif tag == "script":
            self.scripts.append(values)
            if values.get("type", "").lower() == "application/ld+json":
                self._in_json_ld = True
                self._json_buffer = []
        elif tag == "a":
            self.anchors.append(values)
        elif tag == "h1":
            self._in_h1 = True

        classes = set(values.get("class", "").split())
        if "page-content" in classes:
            self._in_page_content = True
            self._page_content_depth = 1
        elif self._in_page_content:
            self._page_content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        self.end_tags[tag] += 1
        if tag == "title":
            self._in_title = False
        elif tag == "body":
            self._in_body = False
        elif tag == "script" and self._in_json_ld:
            self.json_ld_blocks.append("".join(self._json_buffer))
            self._in_json_ld = False
        elif tag == "h1":
            self._in_h1 = False

        if self._in_page_content:
            self._page_content_depth -= 1
            if self._page_content_depth <= 0:
                self._in_page_content = False

        if tag in self._stack:
            index = len(self._stack) - 1 - self._stack[::-1].index(tag)
            del self._stack[index:]

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_texts.append(text)
        if self._in_h1:
            self.h1_texts.append(text)
        if self._in_body:
            self.body_text.append(text)
        if self._in_page_content:
            self.page_content_text.append(text)
        if self._in_json_ld:
            self._json_buffer.append(data)


def add(issues: list[Issue], severity: str, category: str, file: str, message: str) -> None:
    issues.append(Issue(severity, category, file, message))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path) -> str:
    return path.relative_to(OUTPUT_DIR).as_posix()


def parse(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(read_text(path))
    return parser


def html_files() -> list[Path]:
    return sorted(OUTPUT_DIR.rglob("*.html"))


def index_html_files() -> list[Path]:
    return sorted(OUTPUT_DIR.rglob("index.html"))


def important_html_files() -> list[Path]:
    return [path for path in html_files() if rel(path) not in IGNORED_HTML]


def url_to_output_file(url: str, source_file: Path | None = None) -> Path | None:
    if not url or url.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in {"http", "https", "file"}:
        return None
    if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.netloc != SITE_HOST:
        return None

    path = unquote(parsed.path)
    if parsed.scheme == "file":
        return None
    if url.startswith("/") or parsed.scheme in {"http", "https"}:
        if path in {"", "/"}:
            return OUTPUT_DIR / "index.html"
        clean = path.lstrip("/")
        if clean.endswith("/"):
            return OUTPUT_DIR / clean / "index.html"
        if clean.endswith(".html"):
            return OUTPUT_DIR / clean
        return OUTPUT_DIR / clean / "index.html"
    if source_file is not None:
        return (source_file.parent / path).resolve()
    return None


def asset_path(url: str, source_file: Path) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc == SITE_HOST:
        return OUTPUT_DIR / unquote(parsed.path).lstrip("/")
    if parsed.scheme and parsed.scheme not in {"file"}:
        return None
    if url.startswith(("data:", "mailto:", "tel:", "javascript:")):
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    if path.startswith("/"):
        return OUTPUT_DIR / path.lstrip("/")
    return (source_file.parent / path).resolve()


def canonical_for_file(path: Path) -> str:
    relative = rel(path)
    if relative == "index.html":
        return f"{SITE_URL}/"
    if relative.endswith("/index.html"):
        return f"{SITE_URL}/{relative.removesuffix('index.html')}"
    return f"{SITE_URL}/{relative}"


def extract_meta(parser: PageParser, name: str) -> list[str]:
    values = []
    for meta in parser.meta:
        if meta.get("name", "").lower() == name.lower() or meta.get("property", "").lower() == name.lower():
            values.append(meta.get("content", ""))
    return values


def extract_links(parser: PageParser, rel_name: str) -> list[str]:
    values = []
    for link in parser.links:
        rels = {part.lower() for part in link.get("rel", "").split()}
        if rel_name.lower() in rels:
            values.append(link.get("href", ""))
    return values


def json_ld_objects(parser: PageParser) -> tuple[list[dict[str, object]], int]:
    objects: list[dict[str, object]] = []
    errors = 0
    for block in parser.json_ld_blocks:
        try:
            loaded = json.loads(block)
        except json.JSONDecodeError:
            errors += 1
            continue
        items = loaded if isinstance(loaded, list) else [loaded]
        for item in items:
            if isinstance(item, dict):
                objects.append(item)
    return objects, errors


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def shingle_set(text: str, n: int = 5) -> set[str]:
    normalized = re.sub(r"\s+", "", text)
    if len(normalized) <= n:
        return {normalized} if normalized else set()
    return {normalized[index : index + n] for index in range(len(normalized) - n + 1)}


def sitemap_urls() -> tuple[list[str], list[str]]:
    path = OUTPUT_DIR / "sitemap.xml"
    if not path.exists():
        return [], ["sitemap.xml missing"]
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [], [f"sitemap.xml parse error: {exc}"]
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text or "" for loc in root.findall("sm:url/sm:loc", namespace)]
    errors = []
    for lastmod in root.findall("sm:url/sm:lastmod", namespace):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", lastmod.text or ""):
            errors.append(f"invalid lastmod: {lastmod.text}")
    return urls, errors


def check_html_structure(path: Path, parser: PageParser, text: str, issues: list[Issue]) -> None:
    file = rel(path)
    if not text.lower().lstrip().startswith("<!doctype html>"):
        add(issues, "CRITICAL", "html", file, "missing <!doctype html>")
    for tag in ["html", "head", "body"]:
        if parser.start_tags[tag] != 1:
            add(issues, "CRITICAL", "html", file, f"{tag} tag count is {parser.start_tags[tag]}")
    if parser.start_tags["title"] != 1:
        add(issues, "CRITICAL", "html", file, f"title tag count is {parser.start_tags['title']}")
    descriptions = extract_meta(parser, "description")
    if len(descriptions) != 1:
        add(issues, "CRITICAL", "html", file, f"meta description count is {len(descriptions)}")
    canonicals = extract_links(parser, "canonical")
    if len(canonicals) != 1:
        add(issues, "CRITICAL", "html", file, f"canonical count is {len(canonicals)}")
    if parser.start_tags["h1"] != 1:
        add(issues, "HIGH", "seo", file, f"h1 count is {parser.start_tags['h1']}")
    title = normalize_text(" ".join(parser.title_texts))
    if not title:
        add(issues, "CRITICAL", "html", file, "empty title")
    if descriptions and not descriptions[0].strip():
        add(issues, "CRITICAL", "html", file, "empty meta description")
    for tag in ["html", "head", "body", "title", "script", "section", "article", "main", "nav", "footer", "figure"]:
        if parser.end_tags[tag] and parser.start_tags[tag] < parser.end_tags[tag]:
            add(issues, "CRITICAL", "html", file, f"more closing {tag} tags than opening tags")
    head_match = re.search(r"<head\b[^>]*>(?P<head>.*?)</head>", text, flags=re.IGNORECASE | re.DOTALL)
    if head_match and re.search(r"<(main|section|article|footer|h1|p|img|body)\b", head_match.group("head"), re.IGNORECASE):
        add(issues, "CRITICAL", "html", file, "body content appears inside head")


def check_indexing(path: Path, parser: PageParser, text: str, issues: list[Issue]) -> None:
    file = rel(path)
    lower = text.lower()
    if "noindex" in lower:
        add(issues, "CRITICAL", "indexing", file, "contains noindex")
    if "nofollow" in lower:
        add(issues, "CRITICAL", "indexing", file, "contains nofollow")
    canonicals = extract_links(parser, "canonical")
    if canonicals:
        canonical = canonicals[0]
        parsed = urlparse(canonical)
        if parsed.netloc != SITE_HOST:
            add(issues, "HIGH", "canonical", file, f"canonical host mismatch: {canonical}")
        target = url_to_output_file(canonical)
        if target is None or not target.exists():
            add(issues, "HIGH", "canonical", file, f"canonical target missing: {canonical}")
        expected = canonical_for_file(path)
        if canonical != expected:
            add(issues, "HIGH", "canonical", file, f"canonical mismatch: {canonical} != {expected}")
    if "c:\\" in lower or "file://" in lower:
        add(issues, "CRITICAL", "path", file, "local filesystem path exposed")
    if re.search(r"""(?:href|src)=["']/static/""", text):
        add(issues, "HIGH", "path", file, "root absolute static asset path used")


def check_assets(path: Path, parser: PageParser, issues: list[Issue]) -> None:
    file = rel(path)
    if not extract_links(parser, "stylesheet"):
        add(issues, "CRITICAL", "asset", file, "stylesheet missing")
    if not parser.scripts:
        add(issues, "CRITICAL", "asset", file, "script missing")
    for rel_name in ["manifest", "icon"]:
        refs = extract_links(parser, rel_name)
        if not refs:
            add(issues, "CRITICAL", "asset", file, f"{rel_name} missing")
        for href in refs:
            target = asset_path(href, path)
            if target is not None and not target.exists():
                add(issues, "CRITICAL", "asset", file, f"{rel_name} file missing: {href}")
    for href in extract_links(parser, "stylesheet"):
        target = asset_path(href, path)
        if target is not None and not target.exists():
            add(issues, "CRITICAL", "asset", file, f"CSS missing: {href}")
    for script in parser.scripts:
        src = script.get("src", "")
        if src:
            target = asset_path(src, path)
            if target is not None and not target.exists():
                add(issues, "CRITICAL", "asset", file, f"JS missing: {src}")
    for image in parser.images:
        src = image.get("src", "")
        if not src:
            add(issues, "CRITICAL", "asset", file, "image src missing")
            continue
        target = asset_path(src, path)
        if target is not None and not target.exists():
            add(issues, "CRITICAL", "asset", file, f"image missing: {src}")
        alt = image.get("alt", "").strip()
        if not alt:
            add(issues, "MEDIUM", "image", file, f"image alt missing: {src}")
        elif len(alt) < 6:
            add(issues, "MEDIUM", "image", file, f"image alt too short: {src}")
        if not image.get("width") or not image.get("height"):
            add(issues, "LOW", "image", file, f"image width/height missing: {src}")
    for key in ["og:image", "twitter:image"]:
        values = extract_meta(parser, key)
        if rel(path) not in IGNORED_HTML and not values:
            add(issues, "MEDIUM", "seo", file, f"{key} missing")
        for value in values:
            target = asset_path(value, path)
            if target is not None and not target.exists():
                add(issues, "CRITICAL", "asset", file, f"{key} file missing: {value}")


def check_links(path: Path, parser: PageParser, issues: list[Issue]) -> None:
    file = rel(path)
    self_links = 0
    for anchor in parser.anchors:
        href = anchor.get("href", "")
        if not href:
            add(issues, "HIGH", "link", file, "empty href")
            continue
        if href == "#" or href.lower() == "javascript:void(0)":
            add(issues, "HIGH", "link", file, f"invalid href: {href}")
            continue
        if "index.html" in href:
            add(issues, "LOW", "link", file, f"direct index.html link: {href}")
        if " " in href:
            add(issues, "HIGH", "link", file, f"space in href: {href}")
        target = url_to_output_file(href, path)
        if target is not None and not target.exists():
            add(issues, "CRITICAL", "link", file, f"broken internal link: {href}")
        current_canonical = canonical_for_file(path)
        if href in {current_canonical, urlparse(current_canonical).path}:
            self_links += 1
    if parser.anchors and self_links == len(parser.anchors):
        add(issues, "LOW", "link", file, "all links point to the same page")


def check_seo(path: Path, parser: PageParser, issues: list[Issue]) -> tuple[str, str, str]:
    file = rel(path)
    title = normalize_text(" ".join(parser.title_texts))
    description = extract_meta(parser, "description")
    desc = description[0].strip() if description else ""
    h1 = normalize_text(" ".join(parser.h1_texts))
    if len(title) < 12:
        add(issues, "HIGH", "seo", file, f"title too short: {len(title)} chars")
    if len(title) > 75:
        add(issues, "HIGH", "seo", file, f"title too long: {len(title)} chars")
    if len(desc) < 40:
        add(issues, "HIGH", "seo", file, f"meta description too short: {len(desc)} chars")
    if len(desc) > 170:
        add(issues, "HIGH", "seo", file, f"meta description too long: {len(desc)} chars")
    if rel(path) not in IGNORED_HTML:
        for key in ["og:title", "og:description", "twitter:title", "twitter:description"]:
            if not extract_meta(parser, key):
                add(issues, "MEDIUM", "seo", file, f"{key} missing")
    if title and h1 and title == h1:
        add(issues, "LOW", "seo", file, "title and h1 are identical")

    objects, json_errors = json_ld_objects(parser)
    if json_errors:
        add(issues, "MEDIUM", "jsonld", file, f"JSON-LD parse errors: {json_errors}")
    types = {str(item.get("@type")) for item in objects}
    if rel(path) not in IGNORED_HTML:
        for expected in ["WebSite", "WebPage", "BreadcrumbList"]:
            if expected not in types:
                add(issues, "MEDIUM", "jsonld", file, f"{expected} missing")
    for item in objects:
        if item.get("@type") == "WebPage":
            url = str(item.get("url", ""))
            canonical = extract_links(parser, "canonical")
            if canonical and url != canonical[0]:
                add(issues, "MEDIUM", "jsonld", file, f"WebPage url mismatch: {url}")
        if item.get("@type") == "BreadcrumbList":
            elements = item.get("itemListElement")
            if not isinstance(elements, list) or not elements:
                add(issues, "MEDIUM", "jsonld", file, "BreadcrumbList is empty")
    return title, desc, normalize_text(" ".join(parser.page_content_text or parser.body_text))


def check_body_quality(path: Path, body: str, issues: list[Issue]) -> None:
    file = rel(path)
    if rel(path) in IGNORED_HTML:
        return
    length = len(body)
    if length < BODY_MIN_CRITICAL:
        add(issues, "CRITICAL", "content", file, f"body under 500 chars: {length}")
    elif length < BODY_MIN_MEDIUM:
        add(issues, "MEDIUM", "content", file, f"body under 800 chars: {length}")
    if "<p></p>" in read_text(path) or re.search(r"<p\b[^>]*>\s*</p>", read_text(path), re.IGNORECASE):
        add(issues, "LOW", "content", file, "empty paragraph")
    for phrase in ["정적 사이트", "아직 연결된 페이지가 없습니다", "studyroute.co.kr"]:
        if phrase.lower() in read_text(path).lower():
            add(issues, "CRITICAL", "content", file, f"forbidden phrase remains: {phrase}")
    for phrase in ["상담시간", "전화번호", "가격", "비용"]:
        if phrase in read_text(path):
            add(issues, "LOW", "content", file, f"commercial phrase found: {phrase}")


def check_sitemap_robots(issues: list[Issue]) -> tuple[int, int]:
    sitemap, sitemap_errors = sitemap_urls()
    for error in sitemap_errors:
        add(issues, "HIGH", "sitemap", "sitemap.xml", error)
    sitemap_set = set(sitemap)
    html_set = {canonical_for_file(path) for path in index_html_files()}
    if f"{SITE_URL}/404.html" in sitemap_set:
        add(issues, "HIGH", "sitemap", "sitemap.xml", "404 page is in sitemap")
    for url in sitemap:
        if any(part in url.lower() for part in ["report", "script", "test", "robots.txt", "sitemap.xml"]):
            add(issues, "HIGH", "sitemap", "sitemap.xml", f"non-index URL in sitemap: {url}")
        target = url_to_output_file(url)
        if target is None or not target.exists():
            add(issues, "CRITICAL", "sitemap", "sitemap.xml", f"sitemap target missing: {url}")
    missing_from_sitemap = sorted(html_set - sitemap_set - {f"{SITE_URL}/404.html"})
    extra_in_sitemap = sorted(sitemap_set - html_set)
    for url in missing_from_sitemap[:50]:
        add(issues, "HIGH", "sitemap", "sitemap.xml", f"HTML missing from sitemap: {url}")
    if len(missing_from_sitemap) > 50:
        add(issues, "HIGH", "sitemap", "sitemap.xml", f"additional HTML missing from sitemap: {len(missing_from_sitemap) - 50}")
    for url in extra_in_sitemap:
        if url != f"{SITE_URL}/404.html":
            add(issues, "HIGH", "sitemap", "sitemap.xml", f"sitemap URL not output HTML: {url}")

    robots_path = OUTPUT_DIR / "robots.txt"
    if not robots_path.exists():
        add(issues, "CRITICAL", "robots", "robots.txt", "robots.txt missing")
    else:
        robots = read_text(robots_path)
        if re.search(r"(?im)^Disallow:\s*/\s*$", robots):
            add(issues, "CRITICAL", "robots", "robots.txt", "Disallow: / blocks indexing")
        if not re.search(r"(?im)^Allow:\s*/\s*$", robots):
            add(issues, "HIGH", "robots", "robots.txt", "Allow: / missing")
        if f"Sitemap: {SITE_URL}/sitemap.xml" not in robots:
            add(issues, "HIGH", "robots", "robots.txt", "Sitemap line missing or wrong")
    return len(html_set), len(sitemap)


def check_file_cleanup(issues: list[Issue]) -> None:
    bad_suffixes = {".log", ".tmp", ".bak", ".backup"}
    bad_names = {"thumbs.db", ".ds_store"}
    for path in OUTPUT_DIR.rglob("*"):
        lower = path.name.lower()
        if "__pycache__" in path.parts or lower in bad_names or path.suffix.lower() in bad_suffixes:
            add(issues, "LOW", "cleanup", rel(path), "unnecessary output file")
        if path.is_file() and path.suffix.lower() == ".html" and any(part in lower for part in ["test", "report"]):
            add(issues, "HIGH", "cleanup", rel(path), "test/report HTML in output")


def check_duplicates_and_similarity(
    titles: dict[str, str],
    descriptions: dict[str, str],
    bodies: dict[str, str],
    issues: list[Issue],
) -> tuple[int, int, int, int, int, int]:
    title_counts = Counter(titles.values())
    desc_counts = Counter(descriptions.values())
    title_dupes = sum(count - 1 for title, count in title_counts.items() if title and count > 1)
    desc_dupes = sum(count - 1 for desc, count in desc_counts.items() if desc and count > 1)
    for title, count in title_counts.items():
        if title and count > 1:
            add(issues, "HIGH", "seo", "*", f"duplicate title {count}x: {title[:90]}")
    for desc, count in desc_counts.items():
        if desc and count > 1:
            add(issues, "HIGH", "seo", "*", f"duplicate meta description {count}x: {desc[:90]}")

    body_counts = Counter(bodies.values())
    identical = sum(count - 1 for body, count in body_counts.items() if body and count > 1)
    for body, count in body_counts.items():
        if body and count > 1:
            examples = [file for file, text in bodies.items() if text == body][:3]
            add(issues, "CRITICAL", "content", "*", f"identical body {count}x: {', '.join(examples)}")

    short_500 = sum(1 for body in bodies.values() if len(body) < BODY_MIN_CRITICAL)
    short_800 = sum(1 for body in bodies.values() if len(body) < BODY_MIN_MEDIUM)

    buckets: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for file, body in bodies.items():
        shingles = shingle_set(body)
        if not shingles:
            continue
        signature = sorted(shingles)[:20]
        for token in signature[:6]:
            buckets[token].append((file, shingles))
    candidates: set[tuple[str, str]] = set()
    for bucket in buckets.values():
        if len(bucket) > 80:
            continue
        for left_index, (left_file, _left_set) in enumerate(bucket):
            for right_file, _right_set in bucket[left_index + 1 :]:
                if left_file < right_file:
                    candidates.add((left_file, right_file))
                else:
                    candidates.add((right_file, left_file))
    similar_count = 0
    checked = 0
    shingle_cache = {file: shingle_set(body) for file, body in bodies.items()}
    for left, right in sorted(candidates):
        left_set = shingle_cache[left]
        right_set = shingle_cache[right]
        if not left_set or not right_set:
            continue
        smaller = min(len(left_set), len(right_set))
        larger = max(len(left_set), len(right_set))
        if smaller / larger < SIMILARITY_THRESHOLD:
            continue
        score = len(left_set & right_set) / len(left_set | right_set)
        checked += 1
        if score >= SIMILARITY_THRESHOLD:
            similar_count += 1
            if similar_count <= 50:
                add(issues, "MEDIUM", "content", "*", f"similar body {score:.2f}: {left} <-> {right}")
    if similar_count > 50:
        add(issues, "MEDIUM", "content", "*", f"additional similar body pairs: {similar_count - 50}")
    return title_dupes, desc_dupes, identical, short_500, short_800, similar_count


def write_reports(issues: list[Issue], metrics: dict[str, int | str]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    severity_counts = Counter(issue.severity for issue in issues)
    lines = [
        "# CLASSNOVA Final Index Audit",
        "",
        "## Metrics",
    ]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Severity Counts"])
    for severity in SEVERITIES:
        lines.append(f"- {severity}: {severity_counts.get(severity, 0)}")
    lines.extend(["", "## Issues"])
    if issues:
        for issue in issues:
            lines.append(f"- [{issue.severity}] {issue.category} | {issue.file} | {issue.message}")
    else:
        lines.append("- No issues found.")
    TXT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with CSV_REPORT.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["severity", "category", "file", "message"])
        for issue in issues:
            writer.writerow([issue.severity, issue.category, issue.file, issue.message])


def main() -> None:
    issues: list[Issue] = []
    titles: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    bodies: dict[str, str] = {}
    jsonld_error_count = 0

    for path in html_files():
        parser = parse(path)
        text = read_text(path)
        check_html_structure(path, parser, text, issues)
        check_indexing(path, parser, text, issues)
        check_assets(path, parser, issues)
        check_links(path, parser, issues)
        title, desc, body = check_seo(path, parser, issues)
        _objects, json_errors = json_ld_objects(parser)
        jsonld_error_count += json_errors
        if rel(path) not in IGNORED_HTML:
            titles[rel(path)] = title
            descriptions[rel(path)] = desc
            bodies[rel(path)] = body
            check_body_quality(path, body, issues)

    html_index_count, sitemap_count = check_sitemap_robots(issues)
    check_file_cleanup(issues)
    title_dupes, desc_dupes, identical_bodies, short_500, short_800, similar_count = check_duplicates_and_similarity(
        titles, descriptions, bodies, issues
    )

    severity_counts = Counter(issue.severity for issue in issues)
    message_text = "\n".join(issue.message.lower() for issue in issues)
    category_counts = Counter(issue.category for issue in issues)
    metrics: dict[str, int | str] = {
        "total_html_pages": len(html_files()),
        "index_html_pages": html_index_count,
        "sitemap_url_count": sitemap_count,
        "robots_status": "OK" if not any(issue.category == "robots" for issue in issues) else "ISSUES",
        "head_duplicate_count": sum(1 for issue in issues if "head tag count" in issue.message),
        "body_duplicate_count": sum(1 for issue in issues if "body tag count" in issue.message),
        "title_tag_duplicate_count": sum(1 for issue in issues if "title tag count" in issue.message),
        "meta_description_tag_duplicate_count": sum(
            1 for issue in issues if "meta description count" in issue.message
        ),
        "canonical_duplicate_count": sum(1 for issue in issues if "canonical count" in issue.message),
        "noindex_count": message_text.count("contains noindex"),
        "nofollow_count": message_text.count("contains nofollow"),
        "asset_issue_count": category_counts.get("asset", 0),
        "internal_link_issue_count": category_counts.get("link", 0),
        "sitemap_issue_count": category_counts.get("sitemap", 0),
        "critical": severity_counts.get("CRITICAL", 0),
        "high": severity_counts.get("HIGH", 0),
        "medium": severity_counts.get("MEDIUM", 0),
        "low": severity_counts.get("LOW", 0),
        "title_duplicate_count": title_dupes,
        "meta_description_duplicate_count": desc_dupes,
        "body_under_500_count": short_500,
        "body_under_800_count": short_800,
        "identical_body_count": identical_bodies,
        "similar_body_pair_count_0_75": similar_count,
        "jsonld_error_count": jsonld_error_count,
        "base_url_location": "config.py SITE_URL",
    }
    write_reports(issues, metrics)

    print("CLASSNOVA final index audit complete")
    for key, value in metrics.items():
        print(f"- {key}: {value}")
    for severity in SEVERITIES:
        print(f"- {severity}: {severity_counts.get(severity, 0)}")

    if severity_counts.get("CRITICAL", 0) or severity_counts.get("HIGH", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
