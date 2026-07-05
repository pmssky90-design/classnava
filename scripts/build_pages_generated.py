from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
STRUCTURED_PATH = DATA_DIR / "pages_structured.json"
GENERATED_PATH = DATA_DIR / "pages_generated.json"
ROOT_SLUGS = {"강원도과외", "인천과외", "충청남도과외", "충청북도과외"}


def load_pages(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a list.")
    return data


def normalize_page(page: dict[str, Any]) -> dict[str, Any]:
    title = str(page.get("title", "")).strip()
    slug = str(page.get("slug", "")).strip()
    title_suffix = str(page.get("title_suffix", "")).strip()
    region_type = str(page.get("region_type", "")).strip()
    parent = str(page.get("parent", "")).strip()
    source_sheet = str(page.get("source_sheet", "")).strip()

    return {
        "title": title,
        "slug": slug,
        "slug_source": str(page.get("slug_source") or slug).strip(),
        "title_suffix": title_suffix,
        "region_type": region_type,
        "parent": parent,
        "description": f"{title} 정보를 CLASSNOVA에서 확인하세요.",
        "h1": title,
        "summary": f"{title} 페이지입니다. 지역, 과목, 학년 기준의 과외 정보를 구조화해 연결합니다.",
        "content": str(page.get("content", "")).strip(),
        "children": page.get("children", []),
        "related": page.get("related", []),
        "source_sheet": source_sheet,
    }


def validate_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    slug_counts = Counter(page["slug"] for page in pages)
    all_slugs = set(slug_counts)
    duplicates = {slug: count for slug, count in sorted(slug_counts.items()) if count > 1}
    invalid_rows: list[str] = []
    parent_errors: list[str] = []
    slug_suffix_errors: list[str] = []

    for index, page in enumerate(pages, start=1):
        title = page["title"]
        slug = page["slug"]
        slug_source = page["slug_source"]
        title_suffix = page["title_suffix"]
        expected_title = f"{slug_source} {title_suffix}".strip()
        parent = page["parent"]

        if not slug:
            invalid_rows.append(f"row {index}: empty slug")
        if not title:
            invalid_rows.append(f"row {index}: empty title")
        if slug != slug_source:
            invalid_rows.append(f"row {index}: slug differs from slug_source ({slug} != {slug_source})")
        if title != expected_title:
            invalid_rows.append(f"row {index}: title mismatch ({title} != {expected_title})")
        if parent == slug:
            parent_errors.append(f"{slug}: parent equals slug")
        if parent and parent not in all_slugs:
            parent_errors.append(f"{slug}: parent slug does not exist ({parent})")

        suffix_no_space = title_suffix.replace(" ", "")
        if suffix_no_space and slug.endswith(suffix_no_space):
            slug_suffix_errors.append(f"{slug}: slug includes title_suffix '{title_suffix}'")

    root_pages = {page["slug"] for page in pages if not page["parent"]}
    unexpected_roots = sorted(root_pages - ROOT_SLUGS)
    missing_roots = sorted(ROOT_SLUGS - root_pages)
    for slug in unexpected_roots:
        parent_errors.append(f"{slug}: unexpected root page")
    for slug in missing_roots:
        parent_errors.append(f"{slug}: required root page missing")

    return {
        "duplicates": duplicates,
        "invalid_rows": invalid_rows,
        "parent_errors": parent_errors,
        "slug_suffix_errors": slug_suffix_errors,
        "root_pages": sorted(root_pages),
    }


def write_reports(pages: list[dict[str, Any]], validation: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sheet_counts = Counter(page["source_sheet"] for page in pages)
    region_type_counts = Counter(page["region_type"] for page in pages)
    parentless_count = sum(1 for page in pages if not page["parent"])

    duplicate_lines = ["# Duplicates Report", ""]
    if validation["duplicates"]:
        duplicate_lines.extend(f"- {slug}: {count}" for slug, count in validation["duplicates"].items())
    else:
        duplicate_lines.append("- 중복 slug 없음")
    (REPORTS_DIR / "duplicates_report.txt").write_text("\n".join(duplicate_lines) + "\n", encoding="utf-8-sig")

    invalid_lines = ["# Invalid Rows Report", ""]
    combined_invalid = [*validation["invalid_rows"], *validation["slug_suffix_errors"]]
    if combined_invalid:
        invalid_lines.extend(f"- {line}" for line in combined_invalid)
    else:
        invalid_lines.append("- invalid row 없음")
    (REPORTS_DIR / "invalid_rows_report.txt").write_text("\n".join(invalid_lines) + "\n", encoding="utf-8-sig")

    parent_lines = ["# Parent Report", ""]
    parent_lines.append(f"parent 없는 페이지 수: {parentless_count}")
    parent_lines.append("parent 없는 페이지:")
    parent_lines.extend(f"- {slug}" for slug in validation["root_pages"])
    parent_lines.append("")
    if validation["parent_errors"]:
        parent_lines.append("parent 오류:")
        parent_lines.extend(f"- {line}" for line in validation["parent_errors"])
    else:
        parent_lines.append("parent 오류 없음")
    (REPORTS_DIR / "parent_report.txt").write_text("\n".join(parent_lines) + "\n", encoding="utf-8-sig")

    summary_lines = [
        "# Structure Summary",
        "",
        f"전체 페이지 수: {len(pages)}",
        "",
        "시트별 페이지 수:",
    ]
    for sheet, count in sorted(sheet_counts.items()):
        summary_lines.append(f"- {sheet}: {count}")
    summary_lines.extend(["", "region_type별 페이지 수:"])
    for region_type, count in sorted(region_type_counts.items()):
        summary_lines.append(f"- {region_type}: {count}")
    summary_lines.extend(
        [
            "",
            f"parent 없는 페이지 수: {parentless_count}",
            f"중복 slug 수: {len(validation['duplicates'])}",
            f"invalid row 수: {len(validation['invalid_rows'])}",
            f"parent 오류 수: {len(validation['parent_errors'])}",
            f"slug에 title_suffix가 붙은 경우: {len(validation['slug_suffix_errors'])}",
        ]
    )
    (REPORTS_DIR / "structure_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8-sig")


def main() -> None:
    if not STRUCTURED_PATH.exists():
        raise FileNotFoundError(f"Missing structured pages: {STRUCTURED_PATH}")

    pages = [normalize_page(page) for page in load_pages(STRUCTURED_PATH)]
    validation = validate_pages(pages)
    write_reports(pages, validation)

    has_errors = any(
        [
            validation["duplicates"],
            validation["invalid_rows"],
            validation["parent_errors"],
            validation["slug_suffix_errors"],
        ]
    )
    if has_errors:
        raise SystemExit("Validation failed. Check reports folder.")

    GENERATED_PATH.write_text(json.dumps(pages, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print("CLASSNOVA pages_generated.json created")
    print(f"- generated: {GENERATED_PATH}")
    print(f"- total_pages: {len(pages)}")
    print("- duplicates: 0")
    print("- invalid_rows: 0")
    print("- parent_errors: 0")
    print("- slug_suffix_errors: 0")


if __name__ == "__main__":
    main()
