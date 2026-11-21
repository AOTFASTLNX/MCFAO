"""Deterministic metadata merging and report-only resolution checks for MDAF."""
from __future__ import annotations

import json
import struct
import zipfile
from contextlib import ExitStack
from pathlib import Path

from mod_file_policy import is_metadata

PLATFORM_PREFIXES = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "org.graalvm.")
AGENT_FILES = frozenset({
    "reflect-config.json", "jni-config.json", "resource-config.json",
    "proxy-config.json", "serialization-config.json", "reachability-metadata.json",
})


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _list_identity(value):
    if isinstance(value, dict):
        if isinstance(value.get("name"), str):
            return ("name", value["name"], canonical(value.get("parameterTypes")),
                    canonical(value.get("condition")))
        if isinstance(value.get("type"), str):
            return ("type", value["type"], canonical(value.get("condition")))
    return canonical(value)


def _merge_tree(left, right, path, conflicts):
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        for key, value in right.items():
            merged[key] = (_merge_tree(merged[key], value, f"{path}.{key}", conflicts)
                           if key in merged else value)
        return merged
    if isinstance(left, list) and isinstance(right, list):
        merged = {_list_identity(value): value for value in left}
        for value in right:
            key = _list_identity(value)
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                label = key[0] if isinstance(key, tuple) else key
                merged[key] = _merge_tree(merged[key], value, f"{path}[{label}]", conflicts)
            else:
                merged.setdefault(key, value)
        return [merged[key] for key in sorted(merged, key=str)]
    if isinstance(left, bool) and isinstance(right, bool):
        return left or right
    if left == right:
        return left
    conflicts.append({"path": path, "kept": left, "ignored": right,
                      "reason": "conflicting scalar; earlier maintained value retained"})
    return left


def merge_config_entries(*sources):
    """Union Native Image reflection entries by type and member signature, stably.

    Source order is intentional: maintained configuration comes first, followed by static
    inference and tracing-agent observations. Conflicting scalar metadata is reported while the
    earlier value remains authoritative; true flags and member lists are unioned.
    """
    merged = {}
    conflicts = []
    for source in sources:
        for entry in source or ():
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                conflicts.append({"path": "<entry>", "kept": None, "ignored": entry,
                                  "reason": "entry has no string type name"})
                continue
            name = entry["name"]
            key = (name, canonical(entry.get("condition")))
            if key in merged:
                merged[key] = _merge_tree(merged[key], entry, name, conflicts)
            else:
                merged[key] = entry
    return ([merged[key] for key in sorted(merged)], conflicts)


def merge_json_documents(*documents):
    """Deterministically union agent metadata documents of any supported shape."""
    if not documents:
        return None, []
    conflicts = []
    result = documents[0]
    for document in documents[1:]:
        result = _merge_tree(result, document, "<root>", conflicts)
    return result, conflicts


def load_agent_metadata(directory: Path):
    """Read the files emitted by GraalVM's tracing agent without executing them."""
    files = {}
    for path in sorted(directory.glob("*.json")):
        if is_metadata(path.name) or path.name not in AGENT_FILES:
            continue
        try:
            if path.stat().st_size > 32 * 1024**2:
                raise ValueError(f"Tracing-agent file exceeds size limit: {path.name}")
            files[path.name] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid tracing-agent file {path.name}: {error}") from error
    return files


def merge_agent_metadata(directories):
    by_name = {}
    conflicts = []
    for directory in directories:
        for name, document in load_agent_metadata(Path(directory)).items():
            if name in by_name:
                by_name[name], found = merge_json_documents(by_name[name], document)
                conflicts.extend({"file": name, **item} for item in found)
            else:
                by_name[name] = document
    return {name: by_name[name] for name in sorted(by_name)}, conflicts


def build_native_image_config(maintained_reflection, inferred_reflection, agent_metadata,
                              static_metadata=None):
    """Combine reflection roots and retain every other supported agent category.

    Maintained entries are authoritative for conflicting scalar options. Agent metadata is
    appended as observations; it never replaces hand-maintained members.
    """
    # GraalVM 25's tracing agent may emit unified reachability metadata without
    # legacy reflect-config.json. Preserve that document for Native Image, while
    # still merging legacy reflection entries when present.
    traced_reflection = agent_metadata.get("reflect-config.json", [])
    if not isinstance(traced_reflection, list):
        raise ValueError("Tracing agent reflect-config.json must contain an array")
    reflection, conflicts = merge_config_entries(
        maintained_reflection, inferred_reflection, traced_reflection)
    documents = dict(static_metadata or {})
    for name, document in agent_metadata.items():
        if name in documents:
            documents[name], found = merge_json_documents(documents[name], document)
            conflicts.extend({"file": name, **item} for item in found)
        else:
            documents[name] = document
    if reflection or "reflect-config.json" in documents:
        documents["reflect-config.json"] = reflection
    return {name: documents[name] for name in sorted(documents)}, conflicts


def _entry_lookup(stack, classpath):
    from aot_compatibility import scan_archive

    roots = []
    for value in classpath:
        path = Path(value)
        if path.is_dir():
            roots.append((path, None))
        elif path.is_file() and path.suffix.lower() in (".jar", ".zip"):
            archive = stack.enter_context(zipfile.ZipFile(path))
            roots.append((archive, scan_archive(archive)[0]))

    def read(internal_name):
        for root, classes in roots:
            if classes is None:
                path = root / (internal_name + ".class")
                if path.is_file():
                    return path.read_bytes()
            elif internal_name in classes:
                return root.read(classes[internal_name][1])
        return None
    return read


def _parameter_descriptor(name):
    primitives = {"boolean": "Z", "byte": "B", "char": "C", "short": "S",
                  "int": "I", "long": "J", "float": "F", "double": "D", "void": "V"}
    if name in primitives:
        return primitives[name]
    if name.endswith("[]"):
        return "[" + _parameter_descriptor(name[:-2])
    return "L" + name.replace(".", "/") + ";"


def validate_reflection_entries(entries, classpath):
    """Check configured application types and named members against shipped bytecode.

    This is static and report-only. JDK types are recorded as outside the application archive
    check; the existing Java --verify-members probe remains the runtime class-resolution check.
    """
    with ExitStack() as stack:
        return _validate_reflection_entries(entries, _entry_lookup(stack, classpath))


def _validate_reflection_entries(entries, read_entry):
    from config_reflection import class_shape

    findings = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            findings.append({"type": None, "status": "INVALID_ENTRY",
                             "detail": "reflection entry has no string type name",
                             "members": []})
            continue
        binary_name = entry["name"]
        internal_name = binary_name.replace(".", "/")
        data = read_entry(internal_name)
        if data is None:
            platform = binary_name.startswith(PLATFORM_PREFIXES)
            findings.append({"type": binary_name,
                             "status": "PLATFORM_NOT_ARCHIVE_CHECKED" if platform else "UNRESOLVED_TYPE",
                             "members": []})
            continue
        try:
            shape = class_shape(data)
        except (ValueError, IndexError, struct.error) as error:
            findings.append({"type": binary_name, "status": "INVALID_CLASSFILE",
                             "detail": str(error), "members": []})
            continue
        missing = []
        method_signatures = set(shape.get("methodSignatures", ()))
        method_names = set(shape["methods"])
        field_names = set(shape.get("declaredFieldNames", ()))
        for key in ("methods", "fields"):
            available = method_names if key == "methods" else field_names
            for member in entry.get(key, ()):
                if not isinstance(member, dict) or not isinstance(member.get("name"), str):
                    missing.append({"kind": key[:-1], "name": None,
                                    "reason": "member entry has no string name"})
                    continue
                name = member.get("name")
                if name not in available:
                    missing.append({"kind": key[:-1], "name": name})
                    continue
                if key == "methods" and "parameterTypes" in member:
                    parameters = member["parameterTypes"]
                    if not isinstance(parameters, list) or not all(
                            isinstance(parameter, str) and parameter and parameter != "void"
                            for parameter in parameters):
                        missing.append({"kind": "method", "name": name,
                                        "reason": "invalid parameterTypes"})
                        continue
                    descriptor = name + "(" + "".join(map(_parameter_descriptor, parameters)) + ")"
                    if not any(signature.startswith(descriptor) for signature in method_signatures):
                        missing.append({"kind": "method", "name": name,
                                        "parameterTypes": member["parameterTypes"]})
        findings.append({"type": binary_name,
                         "status": "UNRESOLVED_MEMBERS" if missing else "RESOLVED",
                         "members": missing})
    unresolved = sum(item["status"] in ("UNRESOLVED_TYPE", "UNRESOLVED_MEMBERS",
                                         "INVALID_CLASSFILE", "INVALID_ENTRY") for item in findings)
    return {"status": "REPORT_ONLY_FINDINGS" if unresolved else "RESOLVED_IN_SHIPPED_ARCHIVES",
            "scope": "configured types and named members in the selected application classpath; "
                     "JDK entries are listed separately",
            "checkedTypes": len(findings), "unresolvedTypesOrMembers": unresolved,
            "findings": findings}
