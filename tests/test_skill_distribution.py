"""Offline packaging invariants; real upstream discovery is a separate smoke check."""

import hashlib
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SKILLS = {
    "app-icon-design",
    "apple-signing-workflow",
    "keep-calm-and-yolo-on",
    "mcp-secrets-and-local-config",
    "node-npm-workflow",
    "project-memory",
    "python-workflow",
    "review-and-merge-branch",
}


def frontmatter(path: Path) -> dict:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    assert len(parts) == 3 and not parts[0].strip(), path
    data = yaml.safe_load(parts[1])
    assert isinstance(data, dict), path
    return data


def test_public_skill_metadata() -> None:
    entrypoints = sorted((ROOT / "skills").glob("*/SKILL.md"))
    names = []
    for entrypoint in entrypoints:
        data = frontmatter(entrypoint)
        name = data["name"]
        assert isinstance(name, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        assert len(name) < 64 and name == entrypoint.parent.name
        assert isinstance(data["description"], str) and data["description"].strip()
        metadata = data.get("metadata", {})
        assert isinstance(metadata, dict)
        assert type(metadata.get("internal", False)) is bool
        assert not metadata.get("internal", False)
        names.append(name)
    assert len(names) == len(set(names))
    assert set(names) == PUBLIC_SKILLS


def test_maintenance_skill_is_internal() -> None:
    data = frontmatter(ROOT / ".agents/skills/maintain-codex-agents/SKILL.md")
    assert data.get("metadata", {}).get("internal") is True


def test_catalog_covers_public_skills_with_valid_links() -> None:
    catalog = ROOT / "skills/README.md"
    links = re.findall(r"\[([^\]]+)\]\(([^)]+/SKILL\.md)\)", catalog.read_text(encoding="utf-8"))
    assert len(links) == len(PUBLIC_SKILLS)
    assert {name for name, _ in links} == PUBLIC_SKILLS
    for name, target in links:
        assert (catalog.parent / target).resolve() == (ROOT / "skills" / name / "SKILL.md")
        assert (catalog.parent / target).is_file()


@pytest.mark.parametrize("name", sorted(PUBLIC_SKILLS))
def test_skill_payload_is_self_contained(name: str) -> None:
    directory = ROOT / "skills" / name
    # Reject links, including directory links and dangling links, so copies never
    # depend on a source checkout or omit linked supporting resources.
    for path in directory.rglob("*"):
        assert not path.is_symlink(), path
        assert path.is_file() or path.is_dir(), path
    ui = yaml.safe_load((directory / "agents/openai.yaml").read_text(encoding="utf-8"))
    assert isinstance(ui, dict) and isinstance(ui.get("interface"), dict)
    for field in ("display_name", "short_description", "default_prompt"):
        assert isinstance(ui["interface"][field], str) and ui["interface"][field].strip()
    for field in ("icon_small", "icon_large"):
        if field in ui["interface"]:
            resource = (directory / ui["interface"][field]).resolve()
            assert resource.is_relative_to(directory.resolve()) and resource.is_file()


def assert_mit_licenses(root: Path) -> None:
    license_text = (root / "LICENSE").read_bytes()
    # Pin all words of the canonical MIT text from https://opensource.org/license/mit
    # and the accepted copyright line, while allowing whitespace-only formatting.
    assert (
        hashlib.sha256(b" ".join(license_text.split())).hexdigest()
        == "766dc6c993b160af476f70bb12bb4c7206130cee91a4291ad1fe6167fd44cb96"
    )
    for name in PUBLIC_SKILLS:
        assert (root / "skills" / name / "LICENSE").read_bytes() == license_text


def test_mit_license_is_complete_and_bundled() -> None:
    assert_mit_licenses(ROOT)


@pytest.mark.parametrize("change", ["whitespace", "truncated", "changed-word", "mismatched-copy"])
def test_license_validation_rejects_content_loss_not_formatting(
    tmp_path: Path, change: str
) -> None:
    original = (ROOT / "LICENSE").read_bytes()
    if change == "whitespace":
        modified = original.replace(b"\n", b"\r\n\r\n")
    elif change == "truncated":
        modified = b"\n".join(original.splitlines()[:3]) + b"\n"
    elif change == "changed-word":
        modified = original.replace(b"free of charge", b"for a fee")
    else:
        modified = original + b"\n"
    assert modified != original

    # Mutate all copies together except when testing a single divergent payload.
    root_text = original if change == "mismatched-copy" else modified
    (tmp_path / "LICENSE").write_bytes(root_text)
    for name in PUBLIC_SKILLS:
        directory = tmp_path / "skills" / name
        directory.mkdir(parents=True)
        text = modified if change == "mismatched-copy" and name == "app-icon-design" else root_text
        (directory / "LICENSE").write_bytes(text)

    if change == "whitespace":
        assert_mit_licenses(tmp_path)
    else:
        with pytest.raises(AssertionError):
            assert_mit_licenses(tmp_path)
