#!/usr/bin/env python3
"""Validate casting before video assembly; Python 3.10+, standard library only.

`confirm` records a user's explicit selection, but cannot prove human consent.
Agents must invoke it ONLY after the actual user explicitly selects the images.
All paths in the project are relative to its JSON file unless absolute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    def invalid_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")
    return json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_object, parse_constant=invalid_constant)


def write_json(path, value):
    """Replace atomically, with no partially written approval or project file."""
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as stream:
            temp_name = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def inspect(project, source, require_confirmation=True):
    errors, images = [], []
    if not isinstance(project, dict):
        return ["Project must be a JSON object."], None, images
    if type(project.get("schema_version")) is not int or project["schema_version"] != 1:
        errors.append("schema_version must be 1.")
    if not nonempty(project.get("project_id")):
        errors.append("project_id must be a nonempty string.")
    if not isinstance(project.get("style"), dict):
        errors.append("style must be an object.")
    characters = project.get("characters")
    if not isinstance(characters, list) or not characters:
        return errors + ["characters must be a nonempty array."], None, images
    bound = {key: project.get(key) for key in ("schema_version", "project_id", "style")}
    bound["characters"] = []
    character_ids = set()
    for index, character in enumerate(characters):
        label = f"characters[{index}]"
        if not isinstance(character, dict):
            errors.append(f"{label} must be an object.")
            continue
        for key in ("id", "name"):
            if not nonempty(character.get(key)):
                errors.append(f"{label}.{key} must be a nonempty string.")
        identifier = character.get("id")
        if isinstance(identifier, str):
            if identifier in character_ids:
                errors.append(f"{label}.id is duplicated.")
            character_ids.add(identifier)
        if not isinstance(character.get("appearance"), dict):
            errors.append(f"{label}.appearance must be an object.")
        candidates = character.get("candidates")
        if not isinstance(candidates, list):
            errors.append(f"{label}.candidates must be an array.")
            continue
        if len(candidates) < 3:
            errors.append(f"{label} requires at least 3 distinct candidates.")
        selected = character.get("selected_candidate_id")
        if not nonempty(selected):
            errors.append(f"{label}.selected_candidate_id is required.")
        ids, paths, hashes, bound_candidates = set(), set(), set(), []
        for offset, candidate in enumerate(candidates):
            prefix = f"{label}.candidates[{offset}]"
            if not isinstance(candidate, dict):
                errors.append(f"{prefix} must be an object.")
                continue
            bound_candidates.append({key: candidate.get(key) for key in ("id", "path", "sha256")})
            cid = candidate.get("id")
            if not nonempty(cid):
                errors.append(f"{prefix}.id must be a nonempty string.")
            elif cid in ids:
                errors.append(f"{prefix}.id is duplicated.")
            else:
                ids.add(cid)
            if not nonempty(candidate.get("path")):
                errors.append(f"{prefix}.path must be a nonempty string.")
                continue
            try:
                path = (source.parent / candidate["path"]).resolve()
                path_key = os.path.normcase(str(path))
                if path_key in paths:
                    errors.append(f"{prefix}.path is duplicated.")
                paths.add(path_key)
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError("must be a readable, nonempty file")
                actual = sha256(path)
                if actual in hashes:
                    errors.append(f"{prefix} duplicates another candidate's file content.")
                hashes.add(actual)
                if candidate.get("sha256") != actual:
                    errors.append(f"{prefix}.sha256 does not match file bytes (use lowercase SHA256).")
                if cid == selected:
                    images.append({"character_id": identifier, "candidate_id": cid,
                                   "path": str(path), "sha256": actual})
            except (OSError, ValueError, RuntimeError) as exc:
                errors.append(f"{prefix}.path: {exc}")
        if isinstance(selected, str) and selected not in ids:
            errors.append(f"{label}.selected_candidate_id does not identify a candidate.")
        entry = {key: character.get(key) for key in ("id", "name", "appearance", "selected_candidate_id")}
        entry["candidates"] = bound_candidates
        bound["characters"].append(entry)
    digest = hashlib.sha256(json.dumps(bound, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    if require_confirmation:
        confirmation = project.get("selection_confirmation")
        if not isinstance(confirmation, dict):
            errors.append("selection_confirmation is missing; explicit user selection is required.")
        else:
            if confirmation.get("confirmed_by") != "user":
                errors.append("selection_confirmation.confirmed_by must be 'user'.")
            if not nonempty(confirmation.get("user_message")):
                errors.append("selection_confirmation.user_message must contain the exact user confirmation.")
            try:
                stamp = confirmation.get("confirmed_at")
                stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if isinstance(stamp, str) else None
                if stamp is None or stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
                    raise ValueError()
            except ValueError:
                errors.append("selection_confirmation.confirmed_at must be an ISO8601 UTC timestamp.")
            if confirmation.get("selection_digest") != digest:
                errors.append("Selection digest changed; the user must explicitly confirm the updated selection.")
    return errors, digest, images


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Validate every candidate, selection and user confirmation.")
    check.add_argument("project", type=Path)
    check.add_argument("--write-approved", type=Path, help="Atomically write the approved image mapping only on success.")
    confirm = commands.add_parser("confirm", help="Record actual explicit user selection; cannot prove human consent.",
                                  description="Agents MUST use this only after the actual user's explicit image selection. This command cannot prove human consent.")
    confirm.add_argument("project", type=Path)
    confirm.add_argument("--message-file", required=True, type=Path, help="UTF-8 file containing the exact user's confirmation (preserved verbatim).")
    digest_cmd = commands.add_parser("digest", help="Validate candidates and selections; print their current digest.")
    digest_cmd.add_argument("project", type=Path)
    hash_cmd = commands.add_parser("sha256", help="Print a file's SHA256 for the candidate manifest.")
    hash_cmd.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    result = {"ok": False, "errors": []}
    output = getattr(args, "write_approved", None)
    try:
        if args.command == "sha256":
            result.update(ok=True, sha256=sha256(args.file))
        else:
            source = args.project.resolve()
            project = read_json(source)
            errors, digest, images = inspect(project, source, args.command == "check")
            result.update(errors=errors, selection_digest=digest)
            if not errors and args.command == "confirm":
                with args.message_file.open("r", encoding="utf-8", newline="") as stream:
                    message = stream.read()
                if not nonempty(message):
                    errors.append("The confirmation message file must contain the exact, nonempty user's confirmation.")
                else:
                    project["selection_confirmation"] = {"confirmed_by": "user", "confirmed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                                         "user_message": message, "selection_digest": digest}
                    write_json(source, project)
                    result["selection_confirmation"] = project["selection_confirmation"]
            if not errors and output:
                output = output.resolve()
                if output == source:
                    raise ValueError("Approved output must not replace the source project.")
                if any(output == (source.parent / candidate["path"]).resolve()
                       for character in project["characters"] for candidate in character["candidates"]):
                    raise ValueError("Approved output must not replace any candidate file.")
                if output.exists():
                    previous = read_json(output)
                    if not isinstance(previous, dict) or previous.get("source_project") != str(source) or previous.get("kind") != "approved-image-selection":
                        raise ValueError("Refusing to overwrite an unrelated existing output file.")
                write_json(output, {"schema_version": 1, "kind": "approved-image-selection", "source_project": str(source),
                                    "selection_digest": digest, "selection_confirmation": project["selection_confirmation"], "images": images})
                result["approved_output"] = {"path": str(output), "written": True}
            result["ok"] = not errors
    except (OSError, ValueError, RuntimeError) as exc:
        result["errors"].append(str(exc))
    if output and not result["ok"]:
        result["approved_output"] = {"path": str(output.absolute()), "written": False,
                                     "exists": output.exists(), "stale": output.exists(),
                                     "warning": "No output written. Any existing output is untrusted until check succeeds."}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
