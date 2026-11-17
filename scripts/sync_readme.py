"""Keep both languages on the repository homepage using native HTML disclosures."""
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = "<!-- readme:english:start -->"
END = "<!-- readme:english:end -->"


def homepage():
    current = (ROOT / "README.md").read_text(encoding="utf-8")
    if START in current or END in current:
        if (current.count(START) != 1 or current.count(END) != 1
                or current.index(START) > current.index(END)):
            raise ValueError("English README section markers are incomplete")
        english = current.partition(START)[2].partition(END)[0]
    else:
        english = current
    chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    english = english.strip().replace(
        "[简体中文](README.zh-CN.md)", "[简体中文](#user-content-language-chinese)"
    )
    chinese = chinese.strip().replace(
        "[English](README.md)", "[English](#user-content-language-english)"
    )
    if "[简体中文](#user-content-language-chinese)" not in english:
        raise ValueError("English README is missing its same-page Chinese link")
    if "[English](#user-content-language-english)" not in chinese:
        raise ValueError("Chinese README is missing its English link")
    return (
        "<!-- Edit English between its markers; edit Chinese in README.zh-CN.md.\n"
        "     Run: python scripts/sync_readme.py -->\n\n"
        '<details name="readme-language" open>\n'
        "<summary><strong>English</strong></summary>\n\n"
        '<a name="language-english"></a>\n\n'
        f"{START}\n{english}\n{END}\n\n"
        "</details>\n\n"
        '<details name="readme-language">\n'
        "<summary><strong>简体中文</strong></summary>\n\n"
        '<a name="language-chinese"></a>\n\n'
        f"{chinese}\n\n"
        "</details>\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the homepage is out of sync")
    args = parser.parse_args()
    expected = homepage()
    destination = ROOT / "README.md"
    if args.check:
        if destination.read_text(encoding="utf-8") != expected:
            parser.exit(1, "README.md is out of sync; run python scripts/sync_readme.py\n")
        print("Bilingual homepage is in sync.")
    else:
        destination.write_text(expected, encoding="utf-8", newline="\n")
        print("Updated same-page English / Chinese README.")


if __name__ == "__main__":
    main()
