from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = ROOT_DIR / "reports"
DRAFT_PATH = DATA_DIR / "pages_draft.json"
STRUCTURED_PATH = DATA_DIR / "pages_structured.json"
PARENT_REVIEW_PATH = REPORTS_DIR / "parent_review_report.txt"

ROOT_REGION_SLUGS = {
    "강원도과외",
    "인천과외",
    "충청남도과외",
    "충청북도과외",
    "충청도과외",
}
BASE_SHEET_NAME = "과외 수준별 전문 학습"
SUBAREA_SUFFIXES = (
    "국제도시",
    "신도시",
    "생활권",
    "지구",
    "도시",
    "시티",
    "로",
)


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def read_review_slugs(path: Path) -> set[str]:
    if not path.exists():
        return set()

    slugs = set()
    pattern = re.compile(r":\s+(.+?)\s+\([^)]+\)\s+parent")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.search(line)
        if match:
            slugs.add(match.group(1).strip())
    return slugs


def stem(slug: str) -> str:
    return slug.removesuffix("과외")


def is_root_region(slug: str, region_type: str) -> bool:
    return slug in ROOT_REGION_SLUGS or region_type in {"city", "province"} and slug in ROOT_REGION_SLUGS


def is_primary_district(slug: str) -> bool:
    name = stem(slug)
    if any(name.endswith(suffix) for suffix in SUBAREA_SUFFIXES):
        return False
    if name.endswith(("동", "읍", "면")):
        return False
    return True


def candidate_exists(candidate: str, all_slugs: set[str], own_slug: str) -> str:
    return candidate if candidate in all_slugs and candidate != own_slug else ""


def infer_special_area_parent(slug: str, all_slugs: set[str]) -> tuple[str, str]:
    name = stem(slug)
    suffix_to_remove = ""
    for suffix in SUBAREA_SUFFIXES:
        if name.endswith(suffix):
            suffix_to_remove = suffix
            break

    if not suffix_to_remove:
        return "", ""

    base = name.removesuffix(suffix_to_remove)
    candidates = [
        f"{base}동과외",
        f"{base}읍과외",
        f"{base}면과외",
        f"{base}과외",
    ]
    for candidate in candidates:
        found = candidate_exists(candidate, all_slugs, slug)
        if found:
            return found, f"special_area_match:{suffix_to_remove}"

    return "", ""


def infer_prefixed_dong_parent(slug: str, known_primary_districts: list[str]) -> tuple[str, str]:
    name = stem(slug)
    for district in sorted(known_primary_districts, key=len, reverse=True):
        district_name = stem(district)
        if name.startswith(district_name) and slug != district:
            return district, "prefixed_district_match"
    return "", ""


def build_base_parent_map(pages: list[dict[str, Any]], review_slugs: set[str]) -> tuple[dict[str, str], list[str]]:
    all_slugs = {page["slug"] for page in pages}
    base_pages = [page for page in pages if page.get("source_sheet") == BASE_SHEET_NAME]
    parent_map: dict[str, str] = {}
    reasons: dict[str, str] = {}
    remaining: list[str] = []

    current_top = ""
    current_primary_district = ""
    known_primary_districts: list[str] = []

    for page in base_pages:
        slug = page["slug"]
        region_type = page["region_type"]

        if is_root_region(slug, region_type):
            current_top = slug
            current_primary_district = ""
            continue

        if slug not in review_slugs and page.get("parent"):
            if region_type == "district" and is_primary_district(slug):
                current_primary_district = slug
                known_primary_districts.append(slug)
            continue

        parent = ""
        reason = ""

        if region_type == "district":
            special_parent, special_reason = infer_special_area_parent(slug, all_slugs)
            if special_parent:
                parent = special_parent
                reason = special_reason
            elif stem(slug).endswith("로") and current_primary_district:
                parent = current_primary_district
                reason = "road_area_nearest_primary_district"
            elif any(stem(slug).endswith(suffix) for suffix in SUBAREA_SUFFIXES) and current_top:
                parent = current_top
                reason = "special_area_nearest_top_region"
            elif is_primary_district(slug) and current_top:
                parent = current_top
                reason = "nearest_top_region"
                current_primary_district = slug
                known_primary_districts.append(slug)
            elif current_primary_district:
                parent = current_primary_district
                reason = "nearest_primary_district"
            elif current_top:
                parent = current_top
                reason = "nearest_top_region_fallback"

        elif region_type == "dong":
            prefixed_parent, prefixed_reason = infer_prefixed_dong_parent(slug, known_primary_districts)
            if prefixed_parent:
                parent = prefixed_parent
                reason = prefixed_reason
            elif current_primary_district:
                parent = current_primary_district
                reason = "nearest_primary_district"
            elif current_top:
                parent = current_top
                reason = "nearest_top_region_fallback"

        if parent and parent != slug and parent in all_slugs:
            parent_map[slug] = parent
            reasons[slug] = reason
        elif slug in review_slugs:
            remaining.append(f"{page['source_sheet']}: {slug} ({region_type}) parent 자동 확정 불가")

    return parent_map, [f"{slug} -> {parent} ({reasons[slug]})" for slug, parent in sorted(parent_map.items())]


def apply_parent_map(pages: list[dict[str, Any]], parent_map: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    fixed_count = 0
    structured = []
    for page in pages:
        copied = dict(page)
        if not copied.get("parent") and copied["slug"] in parent_map:
            copied["parent"] = parent_map[copied["slug"]]
            fixed_count += 1
        structured.append(copied)
    return structured, fixed_count


def validate_pages(pages: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    slug_counts = Counter(page["slug"] for page in pages)
    all_slugs = set(slug_counts)

    for slug, count in sorted(slug_counts.items()):
        if count > 1:
            errors.append(f"duplicate slug: {slug} ({count})")

    for page in pages:
        slug = page["slug"]
        parent = page.get("parent", "")
        if parent == slug:
            errors.append(f"self parent: {slug}")
        if parent and parent not in all_slugs:
            errors.append(f"missing parent slug: {slug} -> {parent}")

    return errors


def write_reports(
    pages: list[dict[str, Any]],
    fixed_count: int,
    fixed_lines: list[str],
    remaining_lines: list[str],
    validation_errors: list[str],
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    parentless_count = sum(1 for page in pages if not page.get("parent"))
    region_type_counts = Counter(page["region_type"] for page in pages)
    duplicate_count = sum(1 for count in Counter(page["slug"] for page in pages).values() if count > 1)

    fix_report = [
        "# Parent Fix Report",
        "",
        f"parent 보완 수: {fixed_count}",
        f"남은 검토 수: {len(remaining_lines)}",
        f"검증 오류 수: {len(validation_errors)}",
        "",
        "보완 내역:",
    ]
    fix_report.extend(f"- {line}" for line in fixed_lines)
    if not fixed_lines:
        fix_report.append("- 보완 내역 없음")
    if validation_errors:
        fix_report.extend(["", "검증 오류:"])
        fix_report.extend(f"- {line}" for line in validation_errors)
    (REPORTS_DIR / "parent_fix_report.txt").write_text("\n".join(fix_report) + "\n", encoding="utf-8-sig")

    remaining_report = ["# Parent Review Remaining", ""]
    if remaining_lines:
        remaining_report.extend(f"- {line}" for line in remaining_lines)
    else:
        remaining_report.append("- parent 검토 필요 항목 없음")
    (REPORTS_DIR / "parent_review_remaining.txt").write_text(
        "\n".join(remaining_report) + "\n",
        encoding="utf-8-sig",
    )

    summary = [
        "# Structure Summary After Parent Fix",
        "",
        f"전체 페이지 수: {len(pages)}",
        "",
        "region_type별 페이지 수:",
    ]
    for region_type, count in sorted(region_type_counts.items()):
        summary.append(f"- {region_type}: {count}")
    summary.extend(
        [
            "",
            f"parent 없는 페이지 수: {parentless_count}",
            f"중복 slug 수: {duplicate_count}",
            f"parent 보완 수: {fixed_count}",
            f"parent 검토 남은 수: {len(remaining_lines)}",
            f"검증 오류 수: {len(validation_errors)}",
        ]
    )
    (REPORTS_DIR / "structure_summary_after_parent_fix.txt").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8-sig",
    )


def print_summary(pages: list[dict[str, Any]], fixed_count: int, remaining_count: int, validation_errors: list[str]) -> None:
    parentless_count = sum(1 for page in pages if not page.get("parent"))
    duplicate_count = sum(1 for count in Counter(page["slug"] for page in pages).values() if count > 1)
    region_type_counts = Counter(page["region_type"] for page in pages)

    print("CLASSNOVA parent structure fix complete")
    print(f"- structured: {STRUCTURED_PATH}")
    print(f"- fixed_parent_count: {fixed_count}")
    print(f"- remaining_review_count: {remaining_count}")
    print(f"- parentless_count: {parentless_count}")
    print(f"- duplicate_slug_count: {duplicate_count}")
    print(f"- validation_error_count: {len(validation_errors)}")
    print("- region_type_counts:")
    for region_type, count in sorted(region_type_counts.items()):
        print(f"  - {region_type}: {count}")


def main() -> None:
    pages = load_json(DRAFT_PATH)
    review_slugs = read_review_slugs(PARENT_REVIEW_PATH)
    parent_map, fixed_lines = build_base_parent_map(pages, review_slugs)
    structured, fixed_count = apply_parent_map(pages, parent_map)
    validation_errors = validate_pages(structured)

    unresolved_review_slugs = {
        page["slug"]
        for page in structured
        if page["slug"] in review_slugs and not page.get("parent") and page["slug"] not in ROOT_REGION_SLUGS
    }
    remaining_lines = [
        f"{page['source_sheet']}: {page['slug']} ({page['region_type']}) parent 자동 확정 불가"
        for page in structured
        if page["slug"] in unresolved_review_slugs
    ]

    write_json(STRUCTURED_PATH, structured)
    write_reports(structured, fixed_count, fixed_lines, remaining_lines, validation_errors)
    print_summary(structured, fixed_count, len(remaining_lines), validation_errors)

    if validation_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
