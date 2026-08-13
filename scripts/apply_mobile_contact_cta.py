from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
MARKER = "mobile-contact-cta"
CTA = """  <nav class="mobile-contact-cta" aria-label="빠른 연락">
    <a class="mobile-contact-cta__link" href="tel:01049479030">전화하기</a>
    <a class="mobile-contact-cta__link" href="sms:01049479030">문자하기</a>
  </nav>

"""


def main() -> None:
    paths = sorted(OUTPUT.rglob("index.html"))
    if not paths:
        raise RuntimeError("no user-facing index pages found")

    changed = 0
    existing = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        count = text.count(f'class="{MARKER}"')
        if count == 1:
            existing += 1
            continue
        if count:
            raise RuntimeError(f"duplicate CTA marker: {path.relative_to(ROOT)}")
        if "</body>" not in text:
            raise RuntimeError(f"body closing tag missing: {path.relative_to(ROOT)}")
        path.write_text(text.replace("</body>", CTA + "</body>", 1), encoding="utf-8")
        changed += 1

    print(f"Mobile contact CTA patch complete: pages={len(paths)}, changed={changed}, existing={existing}")


if __name__ == "__main__":
    main()
