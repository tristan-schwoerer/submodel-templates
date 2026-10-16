#! /usr/bin/env python3
"""Validate published template JSON with the public, version-specific AAS SDK.

Checks JSON structure and the SDK's local metamodel constraints, including
IEC 61360 content. This is not an IDTA template-specific conformance engine.
"""

import importlib
import json
import os
import pathlib
import sys
from typing import Tuple

AAS_VERSION = os.environ.get("AAS_VERSION", "3.1")
_SDK_MODULES = {"3.0": "aas_core3", "3.1": "aas_core3_1"}
if AAS_VERSION not in _SDK_MODULES:
    raise ValueError(f"Unsupported AAS metamodel version: {AAS_VERSION}")
_sdk = _SDK_MODULES[AAS_VERSION]
aas_jsonization = importlib.import_module(f"{_sdk}.jsonization")
aas_verification = importlib.import_module(f"{_sdk}.verification")

# Existing exact-filename exclusions that still fail the public SDK. Former
# exclusions which pass metamodel verification are checked again; this is not
# proof of external concept-dictionary or IDTA template-specific conformance.
# Exclusions are reported, never silently skipped.
# Future release names are not implicitly excluded.
_SKIP = frozenset({
    "IDTA_02018_Template_MaintenanceInstructions.json",

    # Hierarchical Structures, IEC 81346 extension: 1.1.1, and its 1.1.2
    "IDTA 02011-1-1-1 _Template_BoM_ExtensionbasedonIEC81346.json",
    "IDTA 02011-1-1-1 _Template_BoM_ExtensionbasedonIEC81346_forAASMetamodelV3.1.json",
    "IDTA 02011-1-1-2 _Template_BoM_ExtensionbasedonIEC81346.json",
    "IDTA 02011-1-1-2 _Template_BoM_ExtensionbasedonIEC81346_forAASMetamodelV3.1.json",

    "IDTA 02020_Template_Capability_Description.json",
})


def print_red(msg: str):
    print(f"\033[91m{msg}\033[0m")


def print_green(msg: str):
    print(f"\033[92m{msg}\033[0m")


def parse_version(rel: pathlib.Path) -> Tuple[str, Tuple[int, int, int]]:
    parts = rel.parts
    if len(parts) >= 3 and parts[-3].isdigit() and parts[-2].isdigit() and parts[-1].isdigit():
        key = pathlib.PurePath(*parts[:-3])
        ver = (int(parts[-3]), int(parts[-2]), int(parts[-1]))
        return str(key), ver
    if len(parts) >= 2 and parts[-2].isdigit() and parts[-1].isdigit():
        key = pathlib.PurePath(*parts[:-2])
        ver = (int(parts[-2]), int(parts[-1]), 0)
        return str(key), ver
    return "", (0, 0, 0)


def find_latest_per_submodel(base_path: pathlib.Path, root: pathlib.Path) -> list:
    latest = {}
    for root_dir, _dirs, files in os.walk(base_path):
        if not any(name.endswith(".json") for name in files):
            continue
        path = pathlib.Path(root_dir)
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        key, ver = parse_version(rel)
        if key and ver != (0, 0, 0):
            if key not in latest or ver > latest[key][1]:
                latest[key] = (path, ver)
    return [path for path, _ in latest.values()]


def check_template(path: pathlib.Path, root: pathlib.Path) -> bool:
    print(f"Checking {path.relative_to(root)}:")
    json_files = sorted(path.glob("*.json"))
    if not json_files:
        print_green("- (no JSON files)")
        return True
    ok = True
    for i in json_files:
        if i.name in _SKIP:
            print(f"- {i.relative_to(root)} SKIPPED (existing known legacy exclusion)")
            continue
        try:
            with open(i, encoding="utf-8-sig") as f:
                environment = aas_jsonization.environment_from_jsonable(json.load(f))
            if not environment.submodels:
                raise ValueError("No submodels defined in template JSON")
            errors = list(aas_verification.verify(environment))
            if not errors:
                print_green(f"- {i.relative_to(root)} is ok")
            else:
                print_red(f"- {i.relative_to(root)} is invalid")
                for error in errors:
                    print_red(f"    {error.path}: {error.cause}")
                ok = False
        except Exception as e:
            print_red(f"- {i.relative_to(root)} check failed: {e}")
            ok = False
    return ok


def main() -> int:
    script_dir = pathlib.Path(os.path.dirname(os.path.realpath(__file__)))
    root_dir = script_dir.parent / "published"
    if not root_dir.is_dir():
        print_red(f"Published root not found: {root_dir}")
        return 1
    folders = find_latest_per_submodel(root_dir, root_dir)
    if not folders:
        print_red(f"No template JSON found under {root_dir}")
        return 1
    files = [path for folder in folders for path in folder.glob("*.json")]
    checked = sum(path.name not in _SKIP for path in files)
    skipped = len(files) - checked
    if not checked:
        print_red(f"No template JSON eligible for validation ({skipped} existing exclusions)")
        return 1
    folders.sort(key=lambda p: str(p.relative_to(root_dir)))
    print(f"Checking latest version of {len(folders)} submodel(s) under published/ "
          f"with public {_sdk} (AAS metamodel {AAS_VERSION})\n")
    ok = True
    for path in folders:
        if not check_template(path, root_dir):
            ok = False
    print(f"\nLatest releases of {len(folders)} submodel(s): {checked} JSON file(s) checked, "
          f"{skipped} existing exclusion(s). Result: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
