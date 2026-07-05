from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
EXCEL_PATH = Path("C:/gptwp/자료/강원_인천_충청_12개메인허브_키워드.xlsx")
DRAFT_PATH = DATA_DIR / "pages_draft.json"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

KEYWORD_HEADERS = ("키워드", "검색어", "keyword", "slug_source", "slug source")
TITLE_SUFFIX_HEADERS = ("제목 문구", "제목문구", "타이틀 문구", "타이틀문구", "title_suffix", "title suffix")
SUBJECT_TOKENS = (
    "수학",
    "영어",
    "국어",
    "과학",
    "사회",
    "물리",
    "화학",
    "생명",
    "지구과학",
    "중국어",
    "일본어",
)
GRADE_TOKENS = ("초등", "중등", "고등", "초등학생", "중학생", "고등학생", "고1", "고2", "고3", "중1", "중2", "중3")
BROAD_REGION_PARENTS = {
    "강원": "강원도과외",
    "강원도": "강원도과외",
    "인천": "인천과외",
    "인천광역시": "인천과외",
    "충청": "충청도과외",
    "충청도": "충청도과외",
    "충북": "충청도과외",
    "충남": "충청도과외",
    "대전": "충청도과외",
    "세종": "충청도과외",
}
BROAD_REGION_SLUGS = {"강원도과외", "강원과외", "인천과외", "충청도과외", "충청과외"}


def qname(tag: str) -> str:
    return f"{{{NS_MAIN}}}{tag}"


def column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref)
    if not letters:
        return 0

    value = 0
    for char in letters.group(0):
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def normalize_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def sanitize_text(value: Any) -> str:
    text = str(value) if value is not None else ""
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("C"):
            continue
        cleaned.append(char)
    return "".join(cleaned).strip()


def hangul_count(value: str) -> int:
    return len(re.findall(r"[가-힣]", value))


def mojibake_score(value: str) -> int:
    return len(re.findall(r"[媛怨쇱섑곸異珥以묐벑]", value)) + value.count("?")


def repair_mojibake(value: str) -> str:
    text = sanitize_text(value)
    if not text:
        return ""

    best = text
    best_score = hangul_count(text) * 3 - mojibake_score(text)
    for encoding in ("cp949", "euc-kr"):
        try:
            candidate = text.encode(encoding, errors="strict").decode("utf-8", errors="replace")
        except UnicodeError:
            continue

        candidate_score = hangul_count(candidate) * 3 - mojibake_score(candidate)
        if candidate_score > best_score:
            best = candidate
            best_score = candidate_score

    return sanitize_text(best)


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        source = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(source)
    strings = []
    for item in root.findall(qname("si")):
        parts = [node.text or "" for node in item.iter(qname("t"))]
        strings.append("".join(parts))
    return strings


def read_workbook_sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f"{{{NS_PACKAGE_REL}}}Relationship")
    }

    sheets = []
    for sheet in workbook.findall(f"{qname('sheets')}/{qname('sheet')}"):
        rel_id = sheet.attrib[f"{{{NS_REL}}}id"]
        target = rel_targets[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        sheets.append((repair_mojibake(sheet.attrib["name"]), target))
    return sheets


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find(qname("v"))

    if cell_type == "inlineStr":
        return repair_mojibake("".join(node.text or "" for node in cell.iter(qname("t"))))

    if value_node is None or value_node.text is None:
        return ""

    raw = value_node.text
    if cell_type == "s":
        index = int(raw)
        return repair_mojibake(shared_strings[index]) if 0 <= index < len(shared_strings) else ""

    return repair_mojibake(raw)


def read_sheet_rows(archive: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows = []
    for row in root.findall(f"{qname('sheetData')}/{qname('row')}"):
        values_by_col: dict[int, str] = {}
        for cell in row.findall(qname("c")):
            ref = cell.attrib.get("r", "")
            values_by_col[column_index(ref)] = cell_value(cell, shared_strings)

        width = max(values_by_col.keys(), default=-1) + 1
        rows.append([values_by_col.get(index, "") for index in range(width)])
    return rows


def read_xlsx(path: Path) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = read_shared_strings(archive)
        sheets = read_workbook_sheets(archive)
        return {
            sheet_name: read_sheet_rows(archive, sheet_path, shared_strings)
            for sheet_name, sheet_path in sheets
        }


def is_keyword_candidate(value: str) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    if normalize_header(text) in KEYWORD_HEADERS + TITLE_SUFFIX_HEADERS:
        return False
    if len(text) > 40:
        return False
    if re.search(r"\s", text):
        return False
    if not re.search(r"[가-힣A-Za-z0-9]", text):
        return False
    return "과외" in text or "학교" in text


def find_keyword_column(rows: list[list[str]]) -> tuple[int | None, int | None, str]:
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            if normalize_header(value) in KEYWORD_HEADERS:
                return col_index, row_index, "header"

    scores: dict[int, int] = defaultdict(int)
    for row in rows:
        for col_index, value in enumerate(row):
            text = normalize_text(value)
            if is_keyword_candidate(text):
                scores[col_index] += 3 if "과외" in text else 1

    if not scores:
        return None, None, "not_found"

    column = max(scores, key=scores.get)
    return column, None, "inferred"


def find_title_suffix(rows: list[list[str]], sheet_name: str) -> tuple[str, str]:
    sheet_name = normalize_text(sheet_name)
    first_token, _, rest = sheet_name.partition(" ")
    if first_token.endswith("과외") and rest.strip():
        return rest.strip(), "sheet_name_without_hub_keyword"
    return sheet_name, "sheet_name_fallback"

    # The explicit-cell detection below is intentionally disabled for now.
    # This draft stage needs a sheet-level title phrase, and some source sheets
    # contain long HTML body cells with heading text that look like title labels.
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            if normalize_header(value) in TITLE_SUFFIX_HEADERS:
                for next_col in range(col_index + 1, len(row)):
                    candidate = normalize_text(row[next_col])
                    if candidate:
                        return candidate, f"header_neighbor R{row_index + 1}C{next_col + 1}"

                for next_row in range(row_index + 1, min(row_index + 6, len(rows))):
                    if col_index < len(rows[next_row]):
                        candidate = normalize_text(rows[next_row][col_index])
                        if candidate:
                            return candidate, f"header_below R{next_row + 1}C{col_index + 1}"

    for row_index, row in enumerate(rows[:10]):
        for col_index, value in enumerate(row):
            text = normalize_text(value)
            if "제목" not in text and "타이틀" not in text:
                continue

            neighbors = []
            if col_index + 1 < len(row):
                neighbors.append((row_index, col_index + 1, row[col_index + 1]))
            if row_index + 1 < len(rows) and col_index < len(rows[row_index + 1]):
                neighbors.append((row_index + 1, col_index, rows[row_index + 1][col_index]))

            for neighbor_row, neighbor_col, candidate in neighbors:
                candidate = normalize_text(candidate)
                if candidate and not is_keyword_candidate(candidate):
                    return candidate, f"label_neighbor R{neighbor_row + 1}C{neighbor_col + 1}"

    return sheet_name.strip(), "sheet_name_fallback"


def classify_region_type(slug_source: str) -> str:
    if "학교" in slug_source:
        return "school"
    if any(token in slug_source for token in SUBJECT_TOKENS):
        return "subject"
    if any(token in slug_source for token in GRADE_TOKENS):
        return "grade"
    if slug_source in BROAD_REGION_SLUGS:
        return "city" if slug_source.startswith("인천") else "province"

    stem = slug_source.removesuffix("과외")
    if re.search(r"(동|읍|면)$", stem):
        return "dong"
    if re.search(r"(시|군|구)$", stem):
        return "district"
    if slug_source.endswith(("도과외", "광역시과외", "특별자치도과외")):
        return "province"
    return "district"


def remove_subject_or_grade(slug_source: str) -> str | None:
    for token in SUBJECT_TOKENS + GRADE_TOKENS:
        candidate = slug_source.replace(token, "", 1)
        if candidate != slug_source and candidate.endswith("과외"):
            return candidate
    return None


def broad_parent_for(slug_source: str, all_slugs: set[str]) -> str | None:
    for prefix, parent in sorted(BROAD_REGION_PARENTS.items(), key=lambda item: len(item[0]), reverse=True):
        if slug_source.startswith(prefix) and parent in all_slugs and slug_source != parent:
            return parent
    return None


def local_parent_for(slug_source: str, all_slugs: set[str]) -> str | None:
    stem = slug_source.removesuffix("과외")

    dong_match = re.match(r"(.+(?:시|군|구)).+(?:동|읍|면)$", stem)
    if dong_match:
        candidate = f"{dong_match.group(1)}과외"
        if candidate in all_slugs:
            return candidate

    district_match = re.match(r"(.+?)(?:시|군|구)$", stem)
    if district_match:
        parent = broad_parent_for(slug_source, all_slugs)
        if parent:
            return parent

    return None


def infer_parent(slug_source: str, region_type: str, all_slugs: set[str]) -> tuple[str, str]:
    if slug_source in BROAD_REGION_SLUGS:
        return "", "top_level_region"

    base_parent = remove_subject_or_grade(slug_source)
    if base_parent and base_parent in all_slugs:
        return base_parent, "subject_or_grade_base"

    local_parent = local_parent_for(slug_source, all_slugs)
    if local_parent:
        return local_parent, "locality_parent"

    broad_parent = broad_parent_for(slug_source, all_slugs)
    if broad_parent:
        return broad_parent, "broad_region_parent"

    if region_type in {"city", "province"}:
        return "", "top_level_region"

    return "", "needs_review"


def row_has_data(row: list[str]) -> bool:
    return any(normalize_text(value) for value in row)


def collect_pages(sheets: dict[str, list[list[str]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    draft_rows: list[dict[str, Any]] = []
    invalid_rows: list[str] = []
    sheet_title_suffixes: list[dict[str, str]] = []
    sheet_counts: Counter[str] = Counter()

    for sheet_name, rows in sheets.items():
        title_suffix, title_suffix_source = find_title_suffix(rows, sheet_name)
        keyword_col, header_row, keyword_col_source = find_keyword_column(rows)
        sheet_title_suffixes.append(
            {
                "sheet": sheet_name,
                "title_suffix": title_suffix,
                "source": title_suffix_source,
                "keyword_column": "" if keyword_col is None else str(keyword_col + 1),
                "keyword_column_source": keyword_col_source,
            }
        )

        if keyword_col is None:
            invalid_rows.append(f"{sheet_name}: 키워드 열을 찾지 못했습니다.")
            continue

        start_row = (header_row + 1) if header_row is not None else 0
        for row_index, row in enumerate(rows[start_row:], start=start_row + 1):
            keyword = normalize_text(row[keyword_col]) if keyword_col < len(row) else ""
            if not keyword:
                if row_has_data(row):
                    invalid_rows.append(f"{sheet_name} R{row_index}: 빈 키워드")
                continue

            if not is_keyword_candidate(keyword):
                continue

            title = f"{keyword} {title_suffix}".strip()
            if not title:
                invalid_rows.append(f"{sheet_name} R{row_index}: 빈 title")
                continue

            draft_rows.append(
                {
                    "title": title,
                    "slug": keyword,
                    "slug_source": keyword,
                    "title_suffix": title_suffix,
                    "region_type": classify_region_type(keyword),
                    "parent": "",
                    "content": "",
                    "children": [],
                    "related": [],
                    "source_sheet": sheet_name,
                }
            )
            sheet_counts[sheet_name] += 1

    all_slugs = {page["slug"] for page in draft_rows}
    parent_reviews: list[str] = []
    for page in draft_rows:
        parent, reason = infer_parent(page["slug_source"], page["region_type"], all_slugs)
        page["parent"] = parent
        if reason == "needs_review":
            parent_reviews.append(
                f"{page['source_sheet']}: {page['slug']} ({page['region_type']}) parent 자동 확정 불가"
            )

    slug_counts = Counter(page["slug"] for page in draft_rows)
    duplicates = {slug: count for slug, count in sorted(slug_counts.items()) if count > 1}

    reports = {
        "invalid_rows": invalid_rows,
        "sheet_title_suffixes": sheet_title_suffixes,
        "sheet_counts": sheet_counts,
        "parent_reviews": parent_reviews,
        "duplicates": duplicates,
    }
    return draft_rows, reports


def write_reports(pages: list[dict[str, Any]], reports: dict[str, Any]) -> dict[str, int]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    title_lines = ["# Sheet Title Suffix Report", ""]
    for item in reports["sheet_title_suffixes"]:
        title_lines.append(
            f"- {item['sheet']}: title_suffix='{item['title_suffix']}', "
            f"source={item['source']}, keyword_column={item['keyword_column'] or 'N/A'} "
            f"({item['keyword_column_source']})"
        )
    (REPORTS_DIR / "sheet_title_suffix_report.txt").write_text("\n".join(title_lines) + "\n", encoding="utf-8-sig")

    duplicate_lines = ["# Duplicates Report", ""]
    if reports["duplicates"]:
        for slug, count in reports["duplicates"].items():
            duplicate_lines.append(f"- {slug}: {count}")
    else:
        duplicate_lines.append("- 중복 slug 없음")
    (REPORTS_DIR / "duplicates_report.txt").write_text("\n".join(duplicate_lines) + "\n", encoding="utf-8-sig")

    invalid_lines = ["# Invalid Rows Report", "", *[f"- {line}" for line in reports["invalid_rows"]]]
    if not reports["invalid_rows"]:
        invalid_lines.append("- invalid row 없음")
    (REPORTS_DIR / "invalid_rows_report.txt").write_text("\n".join(invalid_lines) + "\n", encoding="utf-8-sig")

    parent_lines = ["# Parent Review Report", "", *[f"- {line}" for line in reports["parent_reviews"]]]
    if not reports["parent_reviews"]:
        parent_lines.append("- parent 검토 필요 항목 없음")
    (REPORTS_DIR / "parent_review_report.txt").write_text("\n".join(parent_lines) + "\n", encoding="utf-8-sig")

    region_type_counts = Counter(page["region_type"] for page in pages)
    parentless_count = sum(1 for page in pages if not page["parent"])
    summary = {
        "total_pages": len(pages),
        "parentless_count": parentless_count,
        "duplicate_slug_count": len(reports["duplicates"]),
    }

    summary_lines = [
        "# Structure Summary",
        "",
        f"전체 페이지 수: {len(pages)}",
        "",
        "시트별 페이지 수:",
    ]
    for sheet, count in sorted(reports["sheet_counts"].items()):
        summary_lines.append(f"- {sheet}: {count}")

    summary_lines.extend(["", "region_type별 페이지 수:"])
    for region_type, count in sorted(region_type_counts.items()):
        summary_lines.append(f"- {region_type}: {count}")

    summary_lines.extend(
        [
            "",
            f"parent 없는 페이지 수: {parentless_count}",
            f"중복 slug 수: {len(reports['duplicates'])}",
        ]
    )
    (REPORTS_DIR / "structure_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8-sig")

    return summary


def print_terminal_summary(summary: dict[str, int]) -> None:
    print("CLASSNOVA Excel structure analysis complete")
    print(f"- draft: {DRAFT_PATH}")
    print(f"- reports: {REPORTS_DIR}")
    print(f"- total_pages: {summary['total_pages']}")
    print(f"- parentless_count: {summary['parentless_count']}")
    print(f"- duplicate_slug_count: {summary['duplicate_slug_count']}")


def main() -> None:
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel file not found: {EXCEL_PATH}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sheets = read_xlsx(EXCEL_PATH)
    pages, reports = collect_pages(sheets)

    DRAFT_PATH.write_text(
        json.dumps(pages, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = write_reports(pages, reports)
    print_terminal_summary(summary)


if __name__ == "__main__":
    main()
