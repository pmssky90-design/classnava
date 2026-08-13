from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "expansion_20260813_files.txt"
GENERATOR = ROOT / "generator.py"
OUTPUT = ROOT / "output"
EXPECTED_FILES = 4934
EXPECTED_NEW_HTML = 4932
EXPECTED_TOTAL_HTML = 7178
EXPECTED_SITEMAP_URLS = 4932
EXPANSION_SITEMAP = OUTPUT / "sitemap-classnova-expansion-20260813.xml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest() -> list[Path]:
    if not MANIFEST.is_file():
        raise RuntimeError(f"manifest not found: {MANIFEST}")
    raw = [line.strip() for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(raw) != EXPECTED_FILES:
        raise RuntimeError(f"manifest count mismatch: {len(raw)} != {EXPECTED_FILES}")
    if len(set(raw)) != len(raw):
        raise RuntimeError("manifest contains duplicate paths")

    paths: list[Path] = []
    for value in raw:
        # Manifest entries must be normalized repository-relative output paths.
        if value.startswith(("/", "\\")) or ".." in Path(value).parts or not value.startswith("output/"):
            raise RuntimeError(f"unsafe manifest path: {value}")
        path = ROOT / Path(value)
        if not path.is_file():
            raise RuntimeError(f"manifest source missing: {value}")
        paths.append(Path(value))
    if sum(path.suffix.lower() == ".html" for path in paths) != EXPECTED_NEW_HTML:
        raise RuntimeError("manifest new HTML count mismatch")
    if Path("output/sitemap-classnova-expansion-20260813.xml") not in paths:
        raise RuntimeError("expansion sitemap missing from manifest")
    return paths


def copy_with_hashes(paths: list[Path], backup: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in paths:
        source = ROOT / relative
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hash = sha256(source)
        if sha256(target) != source_hash:
            raise RuntimeError(f"backup SHA256 mismatch: {relative.as_posix()}")
        hashes[relative.as_posix()] = source_hash
    return hashes


def restore(paths: list[Path], backup: Path, hashes: dict[str, str]) -> None:
    for relative in paths:
        source = backup / relative
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256(target) != hashes[relative.as_posix()]:
            raise RuntimeError(f"restore SHA256 mismatch: {relative.as_posix()}")


def sitemap_url_count() -> int:
    if not EXPANSION_SITEMAP.is_file():
        raise RuntimeError("restored expansion sitemap is missing")
    root = ET.parse(EXPANSION_SITEMAP).getroot()
    locations = [element.text or "" for element in root.iter() if element.tag.endswith("loc")]
    if len(locations) != EXPECTED_SITEMAP_URLS:
        raise RuntimeError(f"expansion sitemap count mismatch: {len(locations)}")
    if len(locations) != len(set(locations)) or any(not value for value in locations):
        raise RuntimeError("expansion sitemap contains duplicate or empty URLs")
    return len(locations)


def validate_final(paths: list[Path], hashes: dict[str, str]) -> None:
    for relative in paths:
        target = ROOT / relative
        if not target.is_file() or sha256(target) != hashes[relative.as_posix()]:
            raise RuntimeError(f"final expansion file mismatch: {relative.as_posix()}")
    total_html = sum(1 for path in OUTPUT.rglob("*.html") if path.is_file())
    if total_html != EXPECTED_TOTAL_HTML:
        raise RuntimeError(f"final HTML count mismatch: {total_html} != {EXPECTED_TOTAL_HTML}")
    sitemap_url_count()


def main() -> None:
    paths = load_manifest()
    with tempfile.TemporaryDirectory(prefix=".vercel_expansion_backup_20260813_", dir=ROOT) as temporary:
        backup = Path(temporary)
        hashes = copy_with_hashes(paths, backup)
        result = subprocess.run([sys.executable, str(GENERATOR)], cwd=ROOT, check=False)
        generator_failed = result.returncode != 0
        restore_error: Exception | None = None
        try:
            restore(paths, backup, hashes)
            validate_final(paths, hashes)
            patch_result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'apply_region_school_navigation.py')], cwd=ROOT, check=False)
            if patch_result.returncode != 0:
                raise RuntimeError(f'region navigation patch failed with exit code {patch_result.returncode}')
            region_expansion_result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "apply_region_expansion_navigation.py")],
                cwd=ROOT,
                check=False,
            )
            if region_expansion_result.returncode != 0:
                raise RuntimeError(
                    f"region expansion navigation patch failed with exit code {region_expansion_result.returncode}"
                )
            mobile_cta_result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "apply_mobile_contact_cta.py")],
                cwd=ROOT,
                check=False,
            )
            if mobile_cta_result.returncode != 0:
                raise RuntimeError(f"mobile contact CTA patch failed with exit code {mobile_cta_result.returncode}")
        except Exception as error:
            restore_error = error
        if generator_failed:
            raise RuntimeError(f"generator.py failed with exit code {result.returncode}")
        if restore_error is not None:
            raise restore_error
    print(
        "Vercel expansion build complete: "
        f"{EXPECTED_TOTAL_HTML} HTML, {EXPECTED_NEW_HTML} expansion HTML, "
        f"{EXPECTED_SITEMAP_URLS} expansion sitemap URLs"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Vercel expansion build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
