#!/usr/bin/env python3
"""Retrieve and validate eval specifications. This is not a benchmark runner."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def within(root, name):
    """Only allow relative catalog paths inside this corpus, including symlinks."""
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError(f"Expected a relative corpus path: {name!r}")
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f"Path escapes corpus: {name}")
    return path


def catalog_at(root):
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("Unsupported catalog schema_version")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?", catalog.get("suite_version", "")):
        raise ValueError("suite_version must be a semantic version")
    if not isinstance(catalog.get("readiness"), dict) or not catalog["readiness"]:
        raise ValueError("Catalog requires explicit readiness metadata")
    paths = ["catalog.json"]
    for key in ("protocol", "charter", "requests"):
        paths.append(catalog[key])
    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Catalog requires scenarios")
    ids = set()
    for item in scenarios:
        slug = item["id"]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", slug) or slug in ids:
            raise ValueError(f"Invalid or duplicate scenario id: {slug}")
        ids.add(slug)
        if type(item["step_count"]) is not int or not 1 <= item["step_count"] <= 100:
            raise ValueError(f"Invalid step_count for {slug}")
        if type(item["continuation_probe_count"]) is not int or item["continuation_probe_count"] < 0:
            raise ValueError(f"Invalid continuation_probe_count for {slug}")
        for field in ("title", "focus", "status"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError(f"Missing {field} for {slug}")
        paths.extend((item["spec"], item["requests"]))
    resolved = [within(root, name) for name in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Catalog paths must be distinct")
    return catalog


def parse_prompts(root, scenario):
    source = within(root, scenario["spec"]).read_text(encoding="utf-8")
    headings = list(re.finditer(r"^### (\d{2}) — (.+)$", source, re.M))
    steps = [int(match[1]) for match in headings]
    if steps != list(range(scenario["step_count"])):
        raise ValueError(f"{scenario['id']}: numbered prompts must be contiguous from 00, in order")
    records = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        section = source[heading.end():end]
        # A prompt is the first contiguous blockquote directly after its heading.
        quote = re.match(r"\s*?(?P<quote>> [^\n]*(?:\n> [^\n]*)*)", section)
        if not quote:
            raise ValueError(f"{scenario['id']} step {heading[1]}: missing quoted prompt")
        prompt = "\n".join(line[2:] for line in quote["quote"].splitlines())
        if (prompt[:1], prompt[-1:]) not in (("“", "”"), ('"', '"')):
            raise ValueError(f"{scenario['id']} step {heading[1]}: wrap prompt in quotes")
        prompt = prompt[1:-1]
        if not prompt.strip():
            raise ValueError(f"{scenario['id']} step {heading[1]}: empty prompt")
        records.append({"scenario": scenario["id"], "step": int(heading[1]),
                        "title": heading[2], "user_prompt": prompt})
    return records


def jsonl(records):
    return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)


def generated(root, catalog):
    outputs = {}
    combined = []
    for scenario in catalog["scenarios"]:
        records = parse_prompts(root, scenario)
        combined.extend(records)
        outputs[scenario["requests"]] = jsonl(records)
    outputs[catalog["requests"]] = jsonl(combined)
    protocol = within(root, catalog["protocol"]).read_text(encoding="utf-8")
    charter = re.search(r"### Concise charter[^\n]*\n.*?```markdown\n(.*?)```", protocol, re.S)
    if not charter:
        raise ValueError("Protocol must contain the concise charter Markdown block")
    outputs[catalog["charter"]] = charter[1]
    return outputs


def markdown_errors(root):
    errors = []
    for path in sorted(root.rglob("*.md")):
        if any(part in {".git", "__pycache__", "local-runs", "exports", ".venv"}
               for part in path.relative_to(root).parts):
            continue
        if not path.resolve().is_relative_to(root):
            errors.append(f"Markdown symlink escapes corpus: {path.relative_to(root)}")
            continue
        source = path.read_text(encoding="utf-8")
        # Ignore examples/code while checking actual Markdown navigation.
        source = re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", "", source, flags=re.M | re.S)
        source = re.sub(r"`[^`\n]+`", "", source)
        if re.search(r"\[\[[^\]]+\]\]", source):
            errors.append(f"Unresolved wiki link in {path.relative_to(root)}")
        for match in re.finditer(r"\[[^\]\n]*\]\(([^)\n]+)\)", source):
            target = match[1].strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(root) or not resolved.exists():
                errors.append(f"Broken local link in {path.relative_to(root)}: {target}")
    return errors


def validate(root, catalog):
    errors = []
    for name, expected in generated(root, catalog).items():
        path = within(root, name)
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            errors.append(f"Generated file differs or is missing: {name}; run sync")
    errors.extend(markdown_errors(root))
    if errors:
        raise ValueError("\n".join(errors))


def scenario_named(catalog, name):
    for scenario in catalog["scenarios"]:
        if scenario["id"] == name:
            return scenario
    raise ValueError(f"Unknown scenario {name!r}; use list")


def revision_at(root):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    try:
        # Do not mistake the parent workspace's commit for this corpus's commit.
        if Path(git("rev-parse", "--show-toplevel")).resolve() != root:
            return {"commit": None, "dirty": None}
        commit = git("rev-parse", "HEAD")
        return {"commit": commit, "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def export_bundle(root, catalog, scenario, output):
    validate(root, catalog)
    # Reject a symlink, existing directory, or output that would modify the corpus.
    if output.exists() or output.is_symlink():
        raise ValueError(f"Export destination already exists: {output}")
    output = output.resolve()
    if output == root or root.is_relative_to(output):
        raise ValueError("Export destination cannot contain the source corpus")
    if output.is_relative_to(root) and not output.is_relative_to(root / "exports"):
        raise ValueError("Use exports/ for bundles inside the repository, or an external path")
    spec = within(root, scenario["spec"]).read_text(encoding="utf-8")
    spec = spec.replace("../../docs/protocol.md", "protocol.md")
    protocol = within(root, catalog["protocol"]).read_text(encoding="utf-8")
    protocol = protocol.replace("../README.md", "README.md").replace("provenance.md", "README.md#provenance")
    protocol = protocol.replace("../requests.jsonl", "requests.jsonl")
    for other in catalog["scenarios"]:
        old = f"[{other['title']}](../{other['spec']})"
        new = f"[{other['title']}](spec.md)" if other["id"] == scenario["id"] else f"{other['title']} (not included in this bundle)"
        protocol = protocol.replace(old, new)
    protocol = protocol.replace("at the repository root contains the 48 authored user prompts", "in this bundle contains the selected scenario's authored user prompts")
    bundled_scenario = dict(scenario, spec="spec.md", requests="requests.jsonl")
    readme = (f"# {scenario['title']} operator bundle\n\n"
              "Audience: **operator-only**. This contains future requests and evaluator criteria. "
              "Never mount it in a coding-agent workspace. Reveal only the current prompt and "
              "its separately prepared public attachments.\n\n"
              f"Suite version: {catalog['suite_version']}. Status: {scenario['status']}. "
              "This bundle does not execute a benchmark. Fixtures, acceptance oracles and runner "
              "are not included.\n\n"
              "Read [spec.md](spec.md) and [protocol.md](protocol.md). "
              "[requests.jsonl](requests.jsonl) is the operator queue; "
              "[charter.md](charter.md) is the shared B/C charter. "
              "[scenario.json](scenario.json) describes this scenario.\n\n"
              "## Provenance\n\n"
              "Exported from hcekne/anaxi_evals. The manifest records source revision, "
              "dirty status and SHA-256 of every bundled payload. Internal links were adapted "
              "for this single-scenario bundle; other scenarios are omitted. "
              "A null commit or dirty checkout is not a frozen release.\n")
    payloads = {"spec.md": spec, "protocol.md": protocol,
                "charter.md": within(root, catalog["charter"]).read_text(encoding="utf-8"),
                "requests.jsonl": within(root, scenario["requests"]).read_text(encoding="utf-8"),
                "scenario.json": dump(bundled_scenario), "README.md": readme}
    manifest = {"schema_version": 1, "suite_version": catalog["suite_version"],
                "scenario": scenario["id"], "audience": "operator-only",
                "split": catalog["split"], "readiness": catalog["readiness"],
                "source_revision": revision_at(root),
                "files": {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                          for name, content in payloads.items()}}
    output.mkdir(parents=True, exist_ok=False)
    for name, content in {**payloads, "manifest.json": dump(manifest)}.items():
        (output / name).write_text(content, encoding="utf-8")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="alternate corpus root")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list scenarios")
    listing.add_argument("--json", action="store_true")
    prompt = commands.add_parser("prompt", help="print one user prompt; no evaluator checks")
    prompt.add_argument("scenario")
    prompt.add_argument("step", type=int)
    prompt.add_argument("--json", action="store_true")
    commands.add_parser("sync", help="regenerate queues and charter from canonical Markdown")
    commands.add_parser("validate", help="check catalog, prompt consistency and local links")
    export = commands.add_parser("export", help="export an OPERATOR-ONLY scenario bundle")
    export.add_argument("scenario")
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        catalog = catalog_at(root)
        if args.command == "list":
            if args.json:
                print(dump(catalog["scenarios"]), end="")
            else:
                for item in catalog["scenarios"]:
                    print(f"{item['id']}: {item['step_count']} prompts; {item['status']} — {item['focus']}")
        elif args.command == "sync":
            outputs = generated(root, catalog)  # Parse all sources before any write.
            for name, content in outputs.items():
                path = within(root, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            print(f"Synchronized {len(outputs)} generated files.")
        elif args.command == "validate":
            validate(root, catalog)
            print(f"Valid: suite {catalog['suite_version']}, {len(catalog['scenarios'])} scenarios, "
                  f"{sum(s['step_count'] for s in catalog['scenarios'])} prompts. "
                  "Repository consistency only; no benchmark was run.")
        else:
            scenario = scenario_named(catalog, args.scenario)
            if args.command == "prompt":
                validate(root, catalog)
                if not 0 <= args.step < scenario["step_count"]:
                    raise ValueError(f"Step must be between 0 and {scenario['step_count'] - 1}")
                record = parse_prompts(root, scenario)[args.step]
                print(dump(record) if args.json else record["user_prompt"] + "\n", end="")
                print("Prompt text only. Supply current public fixture attachments separately; "
                      "they are not implemented in this package.", file=sys.stderr)
            else:
                output = export_bundle(root, catalog, scenario, args.output)
                print(f"Exported operator-only bundle: {output}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
