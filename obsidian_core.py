"""Local Markdown vault bridge. Standard library only; never scans the workbook."""
from __future__ import annotations

import hashlib
import os
import posixpath
import re
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

VERSION = "0.2.0"
LANGUAGES = ("ru", "en", "zh")
BLOCKED = {"pass", "private", "runtime", "node_modules", "__pycache__"}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
MAX_NOTE = 2 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024


class VaultError(ValueError):
    pass


def safe_path(root: Path, relative: str) -> Path:
    """Reject absolute, hidden, protected, traversal, symlink and Windows ADS paths."""
    if not isinstance(relative, str) or not relative or any(c in relative for c in '\\:\x00<>"|?*'):
        raise VaultError("invalid_path")
    parts = PurePosixPath(relative).parts
    if PurePosixPath(relative).is_absolute() or any(p in (".", "..") or p.startswith(".") or p.casefold() in BLOCKED for p in parts):
        raise VaultError("invalid_path")
    if any(p.endswith((' ', '.')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I) for p in parts):
        raise VaultError("invalid_path")
    candidate = root.joinpath(*parts)
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise VaultError("linked_path")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise VaultError("outside_vault")
    return candidate


def frontmatter(text: str) -> tuple[dict, str]:
    """Deliberately bounded YAML subset: top-level scalar keys, no executable YAML."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([\w-]+):\s*(.*?)\s*$", line)
        if match:
            meta[match[1]] = match[2].strip("\"'")
    return meta, text[end + 5:]


def without_code(text: str) -> str:
    return re.sub(r"`[^`\n]*`", "", re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text))


class Vault:
    def __init__(self, root: str | Path, created_property: str = "created", limit: int = 20000):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise VaultError("vault_not_found")
        # The project root must never be implicitly treated as a notes corpus.
        if (self.root / "Source" / "AI_MASTER.md").exists() or any(part.casefold() in BLOCKED for part in self.root.parts):
            raise VaultError("protected_vault")
        self.created_property = created_property
        self.limit = limit
        self.cache: dict[str, tuple[str, dict]] = {}

    def files(self):
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            base = Path(directory)
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.casefold() not in BLOCKED and not (base/d).is_symlink() and not getattr(base/d, "is_junction", lambda: False)())
            for name in sorted(files):
                if name.startswith(".") or name.casefold() in {"credentials.json", "secrets.json"}:
                    continue
                path = base / name
                if path.suffix.lower() != ".md":
                    continue
                try:
                    yield safe_path(self.root, path.relative_to(self.root).as_posix())
                except VaultError:
                    continue

    def read(self, relative: str) -> dict:
        path = safe_path(self.root, relative)
        if path.suffix.lower() != ".md" or not path.is_file():
            raise VaultError("note_not_found")
        if path.stat().st_size > MAX_NOTE:
            raise VaultError("note_too_large")
        with path.open('rb') as handle:
            data = handle.read(MAX_NOTE + 1)
        if len(data) > MAX_NOTE:
            raise VaultError("note_too_large")
        return {"path": relative, "content": data.decode('utf-8-sig')}

    def create(self, relative: str, content: str) -> dict:
        path = safe_path(self.root, relative)
        if path.suffix.lower() != ".md" or not isinstance(content, str):
            raise VaultError("invalid_note")
        raw = content.encode("utf-8")
        if len(raw) > MAX_NOTE:
            raise VaultError("note_too_large")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(raw)
        except FileExistsError as exc:
            raise VaultError("already_exists") from exc
        return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "created": True}

    def image(self, relative: str) -> tuple[bytes, str]:
        path = safe_path(self.root, relative)
        if path.suffix.lower() not in IMAGE_TYPES or not path.is_file():
            raise VaultError("image_not_found")
        if path.stat().st_size > MAX_IMAGE:
            raise VaultError("image_too_large")
        with path.open('rb') as handle:
            data = handle.read(MAX_IMAGE + 1)
        self.check_image(path.suffix.lower(), data)
        return data, IMAGE_TYPES[path.suffix.lower()]

    @staticmethod
    def check_image(suffix: str, data: bytes):
        valid = {".png": data.startswith(b"\x89PNG\r\n\x1a\n"), ".jpg": data.startswith(b"\xff\xd8\xff"), ".jpeg": data.startswith(b"\xff\xd8\xff"), ".gif": data.startswith((b"GIF87a", b"GIF89a")), ".webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP"}
        if len(data) > MAX_IMAGE or not valid.get(suffix, False):
            raise VaultError("invalid_image")

    def add_image(self, relative: str, data: bytes) -> dict:
        path = safe_path(self.root, relative)
        self.check_image(path.suffix.lower(), data)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(data)
        except FileExistsError as exc:
            raise VaultError("already_exists") from exc
        return {"path": relative, "embed": f"![[{relative}]]", "sha256": hashlib.sha256(data).hexdigest()}

    def graph(self) -> dict:
        notes, warnings, seen = [], [], set()
        for path in self.files():
            if len(notes) >= self.limit:
                warnings.append("note_limit_reached")
                break
            relative = path.relative_to(self.root).as_posix()
            seen.add(relative)
            try:
                if path.stat().st_size > MAX_NOTE:
                    warnings.append("note_too_large:" + relative)
                    continue
                with path.open('rb') as handle:
                    raw = handle.read(MAX_NOTE + 1)
                if len(raw) > MAX_NOTE:
                    warnings.append("note_too_large:" + relative)
                    continue
                fingerprint = hashlib.sha256(raw).hexdigest()
                if relative in self.cache and self.cache[relative][0] == fingerprint:
                    note = dict(self.cache[relative][1])
                else:
                    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
                    meta, body = frontmatter(text)
                    title = re.search(r"(?m)^#\s+(.+)$", body)
                    created = meta.get(self.created_property, "")[:10]
                    source = "property"
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", created):
                        match = re.search(r"\d{4}-\d{2}-\d{2}", path.stem)
                        created = match[0] if match else ""
                        source = "filename" if match else "unknown"
                    try:
                        if created:
                            datetime.strptime(created, "%Y-%m-%d")
                    except ValueError:
                        created, source = "", "unknown"
                    clean = without_code(body)
                    refs = [(m[1], bool(m[0])) for m in re.findall(r"(!?)\[\[([^\]]+)\]\]", clean)]
                    refs += [(m[1], bool(m[0])) for m in re.findall(r"(!?)\[[^\]]*\]\(([^)]+)\)", clean)]
                    note = {"id": relative, "title": title[1] if title else path.stem, "folder": relative.split("/")[0] if "/" in relative else "(root)", "created": created, "date_source": source, "kind": meta.get("type", "").lower(), "tags": sorted(set(re.findall(r"(?<!\w)#([\w/-]+)", clean))), "refs": refs, "headings": len(re.findall(r"(?m)^#{1,6}\s", body)), "tasks": len(re.findall(r"(?m)^\s*-\s+\[[ xX]\]", body)), "first_person": bool(re.search(r"(?iu)\b(?:я|мой|моя|I|my)\b|我", clean)), "excerpt": re.sub(r"\s+", " ", body)[:220]}
                    self.cache[relative] = (fingerprint, dict(note))
                notes.append(note)
            except (OSError, UnicodeError):
                warnings.append("unreadable_note:" + relative)
        self.cache = {k: v for k, v in self.cache.items() if k in seen}
        by_id = {n["id"]: n for n in notes}
        stems = defaultdict(list)
        by_casefold = defaultdict(list)
        for n in notes:
            stems[Path(n["id"]).stem.casefold()].append(n["id"])
            by_casefold[n["id"].casefold()].append(n["id"])
        outgoing, incoming = defaultdict(set), defaultdict(set)
        edges = []
        for note in notes:
            note["images"], note["unresolved"] = [], []
            for target, embedded in note.pop("refs"):
                target = unquote(target.split("|", 1)[0].split("#", 1)[0]).strip().strip("<>")
                if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("//"):
                    continue
                suffix = Path(target).suffix.lower()
                candidates = [posixpath.normpath(str(PurePosixPath(note["id"]).parent / target)), target]
                if suffix in IMAGE_TYPES and embedded:
                    for candidate in candidates:
                        try:
                            image_path = safe_path(self.root, candidate)
                            if image_path.is_file():
                                note["images"].append(candidate)
                                break
                        except VaultError:
                            pass
                    continue
                if suffix and suffix != ".md":
                    continue
                candidates = [p if p.lower().endswith(".md") else p + ".md" for p in candidates]
                resolved = next((p for p in candidates if p in by_id), None)
                if resolved is None:
                    resolved = next((by_casefold[p.casefold()][0] for p in candidates if len(by_casefold[p.casefold()]) == 1), None)
                if resolved is None and "/" not in target and len(stems[Path(target).stem.casefold()]) == 1:
                    resolved = stems[Path(target).stem.casefold()][0]
                if resolved and resolved != note["id"]:
                    if resolved not in outgoing[note["id"]]:
                        outgoing[note["id"]].add(resolved)
                        incoming[resolved].add(note["id"])
                        edges.append({"source": note["id"], "target": resolved})
                elif not resolved:
                    note["unresolved"].append(target)
        # Explainable local policy, intentionally distinct from upstream's scoring.
        maps = {n["id"] for n in notes if n["kind"] in {"moc", "map"} and outgoing[n["id"]]}
        maps |= {n["id"] for n in notes if len(outgoing[n["id"]]) >= 5}
        for n in notes:
            out, inc = outgoing[n["id"]], incoming[n["id"]]
            neighbors = out | inc
            if not neighbors:
                level, reason = 1, "no_links"
            elif n["kind"] in {"home", "hub"}:
                level, reason = 5, "explicit_hub"
            elif len(out & maps) >= 2:
                level, reason = 4, "links_two_maps"
            elif n["id"] in maps:
                level, reason = 3, "content_map"
            else:
                level, reason = 2, "linked_note"
            top_down = n["headings"] >= 3 or n["id"] in maps or n["kind"] in {"home", "hub"}
            expresses = n["tasks"] > 0 or n["folder"].casefold() in {"efforts", "projects", "проекты", "项目"}
            n.update(level=level, reason=reason, outgoing=sorted(out), incoming=sorted(inc), degree=len(neighbors), role=("producer" if expresses else "synthesizer") if top_down else ("creative" if expresses else "inner_guide"), role_clues={"headings": n["headings"], "tasks": n["tasks"], "first_person": n["first_person"], "top_down": top_down, "expresses": expresses})
        hubs = sorted(notes, key=lambda n: (-n["level"], -n["degree"], n["id"]))[:6]
        hubs = [h for h in hubs if h["degree"]]
        galaxies = {}
        queue = deque()
        for h in hubs:
            galaxies[h["id"]] = h["id"]
            queue.append(h["id"])
        while queue:
            here = queue.popleft()
            for nxt in sorted(outgoing[here] | incoming[here]):
                if nxt not in galaxies:
                    galaxies[nxt] = galaxies[here]
                    queue.append(nxt)
        for n in notes:
            n["galaxy"] = galaxies.get(n["id"], "folder:" + n["folder"])
        return {"schema": "c-obsidian.graph/v1", "version": VERSION, "policy": "c-obsidian-explainable-v1", "notes": notes, "edges": edges, "warnings": warnings, "summary": {"notes": len(notes), "links": len(edges), "unlinked": sum(n["level"] == 1 for n in notes), "maps": sum(n["level"] == 3 for n in notes), "images": sum(len(n["images"]) for n in notes)}, "limitations": ["scalar_frontmatter_only", "markdown_links_subset", "current_links_not_historical", "dates_unknown_without_metadata"]}
