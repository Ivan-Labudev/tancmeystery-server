"""Offline gate for a client mods.zip (Fabric 1.20.1).

Checks, without starting anything:
  1. every `depends` entry of every mod (top-level AND jar-in-jar nested) is satisfied by a mod in the set
     (counting `id` and `provides`), except minecraft / java / fabricloader;
  2. the Fabric Loader the players actually run is new enough for the WHOLE set, nested modules included.

Why nested modules matter: Farmer's Delight 2.5.x declares `fabricloader >= 0.16` on the top-level mod, but the
Porting Lib modules bundled inside need >= 0.18.2. A 0.17.2 client silently drops those nested modules and crashes
at launch. Booting the server (loader 0.19.5) never shows this.

Usage:  python tools/check_client_deps.py <mods.zip> [--player-loader 0.17.2]
Exit code 0 = ok, 1 = missing dependency or loader too old for some jar.
"""
import argparse
import io
import json
import re
import sys
import zipfile

BUILTIN = {"minecraft", "java", "fabricloader"}


def parse_version(text):
    m = re.match(r"^\s*(?:>=|>|\^|~|=)?\s*(\d+(?:\.\d+)*)", str(text))
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def lower_bound(constraint):
    """Lowest loader version that satisfies the constraint. A list means OR (any predicate), so the
    effective floor is the smallest bound in it."""
    vals = constraint if isinstance(constraint, list) else [constraint]
    bounds = [b for b in (parse_version(v) for v in vals) if b]
    return min(bounds) if bounds else None


def fmt(version):
    return ".".join(str(x) for x in version)


def collect(jar_bytes, top, mods, depth=0):
    zf = zipfile.ZipFile(io.BytesIO(jar_bytes))
    try:
        meta = json.loads(zf.read("fabric.mod.json").decode("utf-8-sig"), strict=False)
    except KeyError:
        return  # not a Fabric mod (plain library jar)
    mods.append({
        "id": meta["id"], "top": top, "depth": depth,
        "provides": meta.get("provides", []), "depends": meta.get("depends", {}),
    })
    for nested in meta.get("jars", []):
        try:
            collect(zf.read(nested["file"]), top, mods, depth + 1)
        except KeyError:
            pass


def check(zip_path, player_loader):
    """Returns (ok, report_lines)."""
    mods = []
    with zipfile.ZipFile(zip_path) as z:
        jars = [n for n in sorted(z.namelist()) if n.endswith(".jar")]
        for name in jars:
            collect(z.read(name), name, mods)

    provided = set()
    for m in mods:
        provided.add(m["id"])
        provided.update(m["provides"])

    missing = {}
    worst_per_jar = {}  # top-level jar -> (bound, module id, nested?)
    for m in mods:
        for dep, constraint in m["depends"].items():
            if dep == "fabricloader":
                bound = lower_bound(constraint)
                cur = worst_per_jar.get(m["top"])
                if bound and (cur is None or bound > cur[0]):
                    worst_per_jar[m["top"]] = (bound, m["id"], m["depth"] > 0)
            elif dep not in BUILTIN and dep not in provided:
                missing.setdefault(dep, set()).add(m["top"])

    report = [f"{len(jars)} jars, {len(mods)} mods counting nested modules"]
    ok = True

    if missing:
        ok = False
        report.append("MISSING dependencies:")
        for dep, who in sorted(missing.items()):
            report.append(f"  {dep}  <- required by: {', '.join(sorted(who))}")
    else:
        report.append("all `depends` satisfied")

    if worst_per_jar:
        top_jar, (bound, mid, nested) = max(worst_per_jar.items(), key=lambda kv: kv[1][0])
        report.append(f"highest Fabric Loader requirement in the set: {fmt(bound)} "
                      f"({top_jar}{' > nested ' + mid if nested else ''})")
    too_new = {j: v for j, v in worst_per_jar.items() if v[0] > player_loader}
    if too_new:
        ok = False
        report.append(f"TOO NEW for players' Fabric Loader {fmt(player_loader)} "
                      "(Fabric refuses to start the game / drops nested modules):")
        for j, (bound, mid, nested) in sorted(too_new.items()):
            report.append(f"  >= {fmt(bound)}  {j}  [{'nested ' if nested else ''}{mid}]")
    else:
        report.append(f"every jar (nested modules included) works on Fabric Loader {fmt(player_loader)}")
    return ok, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("--player-loader", default="0.17.2",
                    help="oldest Fabric Loader players run (default: 0.17.2, TLauncher's bundled Fabric)")
    args = ap.parse_args()
    ok, report = check(args.zip, parse_version(args.player_loader))
    print("\n".join(report))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
