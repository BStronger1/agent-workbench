"""Trusted repository skills with deterministic routing and pinned versions.

Markdown never grants tool permissions. The graph owns tool dispatch and limits.
Only the chosen instruction body/reference enters a model prompt.
"""

import hashlib
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent / "skills"
REPAIR = "web-ui-acceptance-repair"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SkillRegistry:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.entries = {}
        if not self.root.is_dir():
            raise ValueError("Skill directory missing")
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir():
                continue
            text = self._read(folder / "SKILL.md")
            parts = text.split("---", 2)
            if len(parts) != 3 or parts[0].strip():
                raise ValueError("Skill frontmatter missing")
            meta = yaml.safe_load(parts[1])
            if not isinstance(meta, dict) or not isinstance(meta.get("metadata"), dict):
                raise ValueError("Invalid skill metadata")
            name, description = meta.get("name"), meta.get("description")
            version = meta["metadata"].get("version")
            if (
                not isinstance(name, str)
                or not NAME.fullmatch(name)
                or len(name) > 64
                or name != folder.name
                or not isinstance(description, str)
                or not 1 <= len(description) <= 1024
                or not isinstance(version, str)
                or not version
                or not parts[2].strip()
            ):
                raise ValueError("Invalid skill metadata")
            refs = {}
            for relative in re.findall(r"\]\((references/[^)]+)\)", parts[2]):
                refs[relative] = self._read(folder / relative)
            bundle = {"instructions": parts[2].strip(), "references": refs}
            checksum = digest(
                json.dumps(
                    {"metadata": meta, **bundle}, sort_keys=True, ensure_ascii=False
                )
            )
            self.entries[name] = {
                "name": name,
                "description": description,
                "version": version,
                "hash": checksum,
                **bundle,
            }
        if REPAIR not in self.entries:
            raise ValueError("Required repair skill missing")

    def _read(self, path):
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise ValueError("Skill reference escapes registry or is missing")
        raw = resolved.read_bytes()
        if len(raw) > 16384:
            raise ValueError("Skill resource too large")
        return raw.decode("utf-8").replace("\r\n", "\n")

    def manifest(self):
        return [
            {key: entry[key] for key in ("name", "description", "version", "hash")}
            for entry in self.entries.values()
        ]

    def select(self, attempt, contract, enabled=True, can_repair=True):
        base = {
            "attempt": attempt["number"],
            "name": None,
            "version": None,
            "hash": None,
            "references": [],
            "contextChars": 0,
        }
        if not enabled:
            return None, {**base, "reason": "disabled"}
        if attempt["browserStatus"] in ("ERROR", "NOT_CONFIGURED"):
            return None, {**base, "reason": "infrastructure"}
        if not attempt["errors"]:
            return None, {**base, "reason": "passed"}
        if not can_repair:
            return None, {**base, "reason": "repair_limit"}
        if not contract.get("steps"):
            return None, {**base, "reason": "no_interaction"}
        references = set()
        for error in attempt["errors"]:
            if re.match(
                r"^(Target |Step (check|fill) |Action (check|fill|click) )", error
            ):
                references.add("references/targets.md")
            if error.startswith(
                ("Assertion ", "Result not visible:", "JavaScript error:")
            ):
                references.add("references/state.md")
        if not references:
            return None, {**base, "reason": "unrelated_failure"}
        entry = self.entries[REPAIR]
        refs = sorted(references)
        context = (
            entry["instructions"]
            + "\n\n"
            + "\n\n".join(entry["references"][name] for name in refs)
        )
        selected = {
            "name": REPAIR,
            "version": entry["version"],
            "hash": entry["hash"],
            "references": refs,
            "context": context,
        }
        return selected, {
            **base,
            **{k: selected[k] for k in ("name", "version", "hash", "references")},
            "contextChars": len(context),
            "reason": "interaction_failure",
        }


def skill_instruction(state):
    active = state.get("activeSkill")
    if not active:
        return ""
    return (
        "\n\nTrusted repair skill "
        + active["name"]
        + "@"
        + active["version"]
        + ":\n"
        + active["context"]
    )
