from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
DATA_PATH = ROOT_DIR / "data" / "pages_generated.json"
REPORTS_DIR = ROOT_DIR / "reports"
REPORT_PATH = REPORTS_DIR / "content_similarity_report.txt"
BASELINE_BEFORE_STRATEGY_AVERAGE = 0.099
BASELINE_BEFORE_STRATEGY_STRUCTURE = 0.074


@dataclass
class PageContent:
    slug: str
    path: Path
    region_type: str
    title: str
    html: str
    text: str
    h2s: list[str]
    paragraphs: list[str]
    sentences: list[str]
    structure: str
    strategy_id: str


class PageContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_content = False
        self.depth = 0
        self.current_tag = ""
        self.html_parts: list[str] = []
        self.text_parts: list[str] = []
        self.h2s: list[str] = []
        self.paragraphs: list[str] = []
        self._h2_buffer: list[str] = []
        self._p_buffer: list[str] = []
        self.structure_tags: list[str] = []
        self.strategy_id = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "section" and "page-content" in attrs_dict.get("class", "").split():
            self.in_content = True
            self.depth = 1
            self.html_parts.append(self.get_starttag_text() or "")
            self.structure_tags.append("section.page-content")
            return

        if not self.in_content:
            return

        self.depth += 1
        self.current_tag = tag
        self.html_parts.append(self.get_starttag_text() or "")
        if tag in {
            "h2",
            "h3",
            "p",
            "ul",
            "ol",
            "li",
            "blockquote",
            "table",
            "tbody",
            "tr",
            "th",
            "td",
            "aside",
            "details",
            "summary",
            "figure",
            "figcaption",
            "dl",
            "dt",
            "dd",
            "section",
        }:
            self.structure_tags.append(tag)
        if tag == "h2":
            self._h2_buffer = []
        elif tag == "p":
            self._p_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_content:
            return

        if tag == "h2":
            text = normalize_text("".join(self._h2_buffer))
            if text:
                self.h2s.append(text)
        elif tag == "p":
            text = normalize_text("".join(self._p_buffer))
            if text:
                self.paragraphs.append(text)

        self.html_parts.append(f"</{tag}>")
        self.depth -= 1
        if tag in {"h2", "p"}:
            self.current_tag = ""
        if self.depth <= 0:
            self.in_content = False
            self.current_tag = ""

    def handle_data(self, data: str) -> None:
        if not self.in_content:
            return

        self.html_parts.append(data)
        self.text_parts.append(data)
        if self.current_tag == "h2":
            self._h2_buffer.append(data)
        elif self.current_tag == "p":
            self._p_buffer.append(data)

    def handle_comment(self, data: str) -> None:
        if not self.in_content:
            return
        marker = "content-strategy:"
        if marker in data:
            self.strategy_id = data.split(marker, 1)[1].strip()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def normalize_sentence(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"[0-9]+", "0", value)
    return value


def split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?。！？])\s+", normalize_text(text))
    return [normalize_sentence(piece) for piece in pieces if len(normalize_text(piece)) >= 8]


def sentence_start(sentence: str, words: int = 6) -> str:
    return " ".join(sentence.split()[:words])


def first_words(value: str, count: int) -> str:
    return " ".join(normalize_text(value).split()[:count])


def slug_from_path(path: Path) -> str:
    relative = path.relative_to(OUTPUT_DIR)
    if relative.as_posix() == "index.html":
        return ""
    return relative.parts[0]


def load_page_meta() -> dict[str, dict[str, Any]]:
    pages = json.loads(DATA_PATH.read_text(encoding="utf-8-sig"))
    return {str(page["slug"]): page for page in pages}


def parse_page(path: Path, meta: dict[str, dict[str, Any]]) -> PageContent | None:
    slug = slug_from_path(path)
    if not slug:
        return None

    parser = PageContentParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    content_html = normalize_text("".join(parser.html_parts))
    text = normalize_text(" ".join(parser.text_parts))
    page_meta = meta.get(slug, {})

    return PageContent(
        slug=slug,
        path=path,
        region_type=str(page_meta.get("region_type", "unknown")),
        title=str(page_meta.get("title", slug)),
        html=content_html,
        text=text,
        h2s=parser.h2s,
        paragraphs=parser.paragraphs,
        sentences=split_sentences(text),
        structure=" > ".join(parser.structure_tags),
        strategy_id=parser.strategy_id or "unknown",
    )


def frequency_ratio(value: str, counter: Counter[str], total: int) -> float:
    if not value or total == 0:
        return 0.0
    return counter[value] / total


def build_counters(pages: list[PageContent]) -> dict[str, Counter[str]]:
    counters: dict[str, Counter[str]] = {
        "first_sentence": Counter(),
        "first_paragraph": Counter(),
        "h2": Counter(),
        "h2_pattern": Counter(),
        "paragraph_pattern": Counter(),
        "sentence_start_pattern": Counter(),
        "sentence": Counter(),
        "structure": Counter(),
        "strategy": Counter(),
    }

    for page in pages:
        if page.sentences:
            counters["first_sentence"][page.sentences[0]] += 1
        if page.paragraphs:
            counters["first_paragraph"][page.paragraphs[0]] += 1
        for h2 in page.h2s:
            counters["h2"][h2] += 1

        h2_pattern = " | ".join(page.h2s)
        paragraph_pattern = " | ".join(first_words(paragraph, 8) for paragraph in page.paragraphs)
        start_pattern = " | ".join(sentence_start(sentence) for sentence in page.sentences[:4])
        counters["h2_pattern"][h2_pattern] += 1
        counters["paragraph_pattern"][paragraph_pattern] += 1
        counters["sentence_start_pattern"][start_pattern] += 1
        counters["structure"][page.structure] += 1
        counters["strategy"][page.strategy_id] += 1
        for sentence in page.sentences:
            counters["sentence"][sentence] += 1

    return counters


def page_similarity_scores(
    pages: list[PageContent],
    counters: dict[str, Counter[str]],
) -> list[tuple[float, PageContent]]:
    total = len(pages)
    scored: list[tuple[float, PageContent]] = []
    for page in pages:
        first_sentence = page.sentences[0] if page.sentences else ""
        first_paragraph = page.paragraphs[0] if page.paragraphs else ""
        h2_pattern = " | ".join(page.h2s)
        paragraph_pattern = " | ".join(first_words(paragraph, 8) for paragraph in page.paragraphs)
        start_pattern = " | ".join(sentence_start(sentence) for sentence in page.sentences[:4])
        repeated_sentence_ratio = max(
            [frequency_ratio(sentence, counters["sentence"], total) for sentence in page.sentences],
            default=0.0,
        )

        score = mean(
            [
                frequency_ratio(first_sentence, counters["first_sentence"], total),
                frequency_ratio(first_paragraph, counters["first_paragraph"], total),
                frequency_ratio(h2_pattern, counters["h2_pattern"], total),
                frequency_ratio(paragraph_pattern, counters["paragraph_pattern"], total),
                frequency_ratio(start_pattern, counters["sentence_start_pattern"], total),
                repeated_sentence_ratio,
                frequency_ratio(page.structure, counters["structure"], total),
            ]
        )
        scored.append((score, page))
    return sorted(scored, key=lambda item: item[0], reverse=True)


def repeated_rate(counter: Counter[str], total: int) -> float:
    if total == 0:
        return 0.0
    return sum(count for count in counter.values() if count > 1) / total


def max_ratio(counter: Counter[str], total: int) -> float:
    if total == 0 or not counter:
        return 0.0
    return counter.most_common(1)[0][1] / total


def shorten(value: str, limit: int = 180) -> str:
    value = normalize_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def top_lines(counter: Counter[str], limit: int = 10) -> list[str]:
    rows = [(value, count) for value, count in counter.most_common(limit) if value]
    if not rows:
        return ["- none"]
    return [f"- {count} pages: {shorten(value)}" for value, count in rows]


def region_type_patterns(pages: list[PageContent]) -> list[str]:
    by_region: dict[str, list[PageContent]] = defaultdict(list)
    for page in pages:
        by_region[page.region_type].append(page)

    lines: list[str] = []
    for region_type, items in sorted(by_region.items()):
        local_h2_pattern = Counter(" | ".join(page.h2s) for page in items)
        local_structure = Counter(page.structure for page in items)
        local_first_sentence = Counter(page.sentences[0] if page.sentences else "" for page in items)
        lines.extend(
            [
                f"### {region_type}",
                f"- page_count: {len(items)}",
                f"- top_first_sentence: {format_counter_one(local_first_sentence)}",
                f"- top_h2_pattern: {format_counter_one(local_h2_pattern)}",
                f"- top_html_structure: {format_counter_one(local_structure)}",
                "",
            ]
        )
    return lines


def format_counter_one(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    value, count = counter.most_common(1)[0]
    return f"{count} pages / {shorten(value, 160)}"


def format_optional_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def read_previous_metrics() -> dict[str, float]:
    if not REPORT_PATH.exists():
        return {}
    text = REPORT_PATH.read_text(encoding="utf-8", errors="replace")
    metrics: dict[str, float] = {}
    for key in ["average_similarity", "html_structure_similarity"]:
        match = re.search(rf"^- {key}: ([0-9.]+)", text, flags=re.MULTILINE)
        if match:
            metrics[key] = float(match.group(1))
    return metrics


def write_report(
    pages: list[PageContent],
    counters: dict[str, Counter[str]],
    scores: list[tuple[float, PageContent]],
    previous_metrics: dict[str, float],
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    total = len(pages)
    average_similarity = mean([score for score, _page in scores]) if scores else 0.0
    highest_similarity = scores[0][0] if scores else 0.0
    structure_count = len(counters["structure"])
    most_used_structure_rate = max_ratio(counters["structure"], total)
    strategy_count = len(counters["strategy"])
    most_used_strategy_rate = max_ratio(counters["strategy"], total)
    previous_average = previous_metrics.get("average_similarity")
    previous_structure = previous_metrics.get("html_structure_similarity")

    lines: list[str] = [
        "# CLASSNOVA Content Similarity Report",
        "",
        f"- analyzed_pages: {total}",
        f"- average_similarity: {average_similarity:.3f}",
        f"- highest_similarity: {highest_similarity:.3f}",
        f"- strategy_count: {strategy_count}",
        f"- most_used_strategy_rate: {most_used_strategy_rate:.3f}",
        f"- structure_pattern_count: {structure_count}",
        f"- most_used_structure_pattern_rate: {most_used_structure_rate:.3f}",
        f"- html_structure_similarity: {most_used_structure_rate:.3f}",
        f"- baseline_before_strategy_average_similarity: {BASELINE_BEFORE_STRATEGY_AVERAGE:.3f}",
        f"- baseline_before_strategy_html_structure_similarity: {BASELINE_BEFORE_STRATEGY_STRUCTURE:.3f}",
        f"- average_similarity_delta_from_baseline: {average_similarity - BASELINE_BEFORE_STRATEGY_AVERAGE:.3f}",
        f"- html_structure_similarity_delta_from_baseline: {most_used_structure_rate - BASELINE_BEFORE_STRATEGY_STRUCTURE:.3f}",
        f"- previous_average_similarity: {format_optional_metric(previous_average)}",
        f"- previous_html_structure_similarity: {format_optional_metric(previous_structure)}",
        "",
        "## Repetition Rates",
        f"- first_sentence_repeat_rate: {repeated_rate(counters['first_sentence'], total):.3f}",
        f"- first_paragraph_repeat_rate: {repeated_rate(counters['first_paragraph'], total):.3f}",
        f"- h2_pattern_repeat_rate: {repeated_rate(counters['h2_pattern'], total):.3f}",
        f"- paragraph_order_repeat_rate: {repeated_rate(counters['paragraph_pattern'], total):.3f}",
        f"- sentence_start_pattern_repeat_rate: {repeated_rate(counters['sentence_start_pattern'], total):.3f}",
        f"- identical_html_structure_repeat_rate: {most_used_structure_rate:.3f}",
        "",
        "## Strategy Usage",
    ]
    lines.extend(top_lines(counters["strategy"], limit=30))
    lines.extend(
        [
            "",
            "## Structure Pattern Counts",
        ]
    )
    lines.extend(top_lines(counters["structure"], limit=30))
    lines.extend(
        [
            "",
            "## Most Repeated First Sentences",
        ]
    )
    lines.extend(top_lines(counters["first_sentence"]))
    lines.extend(["", "## Most Repeated H2 Titles"])
    lines.extend(top_lines(counters["h2"]))
    lines.extend(["", "## Most Repeated Paragraph Order Patterns"])
    lines.extend(top_lines(counters["paragraph_pattern"]))
    lines.extend(["", "## Most Repeated Sentence Start Patterns"])
    lines.extend(top_lines(counters["sentence_start_pattern"]))
    lines.extend(["", "## Most Repeated Identical Sentences"])
    lines.extend(top_lines(counters["sentence"]))
    lines.extend(["", "## Most Repeated HTML Structures"])
    lines.extend(top_lines(counters["structure"], limit=5))

    lines.extend(
        [
            "",
            "## Likely Causes",
            "- The generator assigns a deterministic writing strategy from slug, region_type, title_suffix, parent depth, and children count.",
            "- Intro, development, and closing sentences are selected from separate libraries with at least 50 templates each.",
            "- Strategy counts and structure counts should be reviewed together because a strategy can still create several text-level similarities.",
            "- A high most_used_strategy_rate or most_used_structure_pattern_rate means more strategies or different hash inputs may be needed.",
            "",
            "## Region Type Patterns",
        ]
    )
    lines.extend(region_type_patterns(pages))

    lines.extend(["", "## Highest Similarity Pages"])
    for score, page in scores[:50]:
        lines.append(
            f"- {score:.3f} / {page.region_type} / {page.slug} / {page.path.relative_to(OUTPUT_DIR).as_posix()}"
        )

    lines.extend(
        [
            "",
            "## Templates Needing Improvement",
            "- generator.py default content for province/city pages",
            "- generator.py default content for district pages",
            "- generator.py default content for dong pages",
            "- generator.py default content for subject pages",
            "- generator.py default content for grade pages",
            "- generator.py default content for school pages",
            "- templates/page.html page-content structure if structural variety is required",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    previous_metrics = read_previous_metrics()
    meta = load_page_meta()
    pages = [
        parsed
        for path in sorted(OUTPUT_DIR.rglob("index.html"))
        if (parsed := parse_page(path, meta)) is not None
    ]
    pages = [page for page in pages if page.html]
    counters = build_counters(pages)
    scores = page_similarity_scores(pages, counters)
    write_report(pages, counters, scores, previous_metrics)

    total = len(pages)
    average_similarity = mean([score for score, _page in scores]) if scores else 0.0
    highest_similarity = scores[0][0] if scores else 0.0
    most_first_sentence = counters["first_sentence"].most_common(1)[0] if counters["first_sentence"] else ("", 0)
    most_h2 = counters["h2"].most_common(1)[0] if counters["h2"] else ("", 0)
    most_paragraph_pattern = counters["paragraph_pattern"].most_common(1)[0] if counters["paragraph_pattern"] else ("", 0)

    print("CLASSNOVA content similarity analysis complete")
    print(f"- analyzed_pages: {total}")
    print(f"- average_similarity: {average_similarity:.3f}")
    print(f"- highest_similarity: {highest_similarity:.3f}")
    print(f"- strategy_count: {len(counters['strategy'])}")
    print(f"- most_used_strategy_rate: {max_ratio(counters['strategy'], total):.3f}")
    print(f"- structure_pattern_count: {len(counters['structure'])}")
    print(f"- most_used_structure_pattern_rate: {max_ratio(counters['structure'], total):.3f}")
    print(f"- html_structure_similarity: {max_ratio(counters['structure'], total):.3f}")
    print(f"- previous_average_similarity: {format_optional_metric(previous_metrics.get('average_similarity'))}")
    print(f"- previous_html_structure_similarity: {format_optional_metric(previous_metrics.get('html_structure_similarity'))}")
    print(f"- most_repeated_first_sentence: {most_first_sentence[1]} / {shorten(most_first_sentence[0], 100)}")
    print(f"- most_repeated_h2: {most_h2[1]} / {shorten(most_h2[0], 100)}")
    print(f"- most_repeated_paragraph_structure: {most_paragraph_pattern[1]} / {shorten(most_paragraph_pattern[0], 100)}")
    print(f"- report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
