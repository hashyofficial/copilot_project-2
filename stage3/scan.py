#!/usr/bin/env python3
"""Stage 3: read-only, exhaustive on-disk APK inventory of yunluo HyperOS 1 Global super.img.

Does not edit firmware. Reuses verified Stage 2 download, checksum, unpack
and LP geometry code. Includes APKs in any populated logical partition.
"""
import collections
import csv
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow" / "hyperos"))
import geometry
from firmware import NAME, VERSION, MD5

REPORT = Path(os.environ.get("HYPEROS_REPORTS", ROOT / "reports-stage3"))
ROOTDIR = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "hyperos-stage3-mounts"

COLUMNS = (
    "partition", "apk_location", "apk_filename", "application_folder",
    "android_package_id", "application_label", "version_name",
    "required_uses_libraries", "uid", "gid", "mode", "bytes", "selinux",
)

def write(name, value):
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT/name).write_text(value, encoding="utf-8")

def tool(*args, timeout=None):
    print("+", " ".join(map(str, args)), flush=True)
    proc = subprocess.run([str(x) for x in args], text=True,
                          capture_output=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f"{args[0]} failed: " + (proc.stderr or proc.stdout)[-1800:])
    return proc

def select_aapt():
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "/usr/local/lib/android/sdk")
    candidates = list((sdk/"build-tools").glob("*/aapt2")) + list((sdk/"build-tools").glob("*/aapt"))
    candidates.sort(key=lambda p: (tuple(int(x) for x in re.findall(r"\d+", p.parent.name)), p.name=="aapt2"),reverse=True)
    for p in candidates:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    for n in ("aapt2", "aapt"):
        p = shutil.which(n)
        if p:
            return p
    raise RuntimeError("Android aapt2/aapt not found; cannot produce package identity column")

def badging(aapt, apk):
    p = subprocess.run([aapt, "dump", "badging", str(apk)], text=True,
                       capture_output=True, timeout=90)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-300:])
    raw = p.stdout
    pkg = re.search(r"(?m)^package:\s+name='([^']+)'",raw)
    if not pkg:
        raise RuntimeError("No package ID in aapt badging")
    version = re.search(r"(?m)^package:.*?\bversionName='([^']*)'",raw)
    label = re.search(r"(?m)^application-label:'([^']*)'",raw)
    label_en = re.search(r"(?m)^application-label-en(?:-US)?:'([^']*)'",raw)
    uses = sorted(set(re.findall(r"(?m)^uses-library:'([^']+)'",raw)))
    return pkg.group(1), (label_en or label).group(1) if (label_en or label) else "", version.group(1) if version else "", ",".join(uses)

def entry_info(file, base, part, aapt, errors):
    st=file.lstat()
    if not stat.S_ISREG(st.st_mode):
        return None
    relative="/"+file.relative_to(base).as_posix()
    location=f"{part}:{relative}"
    try:
        ctx=os.getxattr(file,"security.selinux",follow_symlinks=False).decode("utf-8","replace").strip("\0")
    except OSError:
        ctx="xattr-not-present-or-policy-derived"
    package=label=version=uses=""
    try:
        package,label,version,uses=badging(aapt,file)
    except Exception as exc:
        # Continue collecting file/path info, but flag missing ID explicitly.
        errors.append(f"{location} => {type(exc).__name__}: {str(exc)[:250]}")
    parent="/"+file.parent.relative_to(base).as_posix()
    return (part, location, file.name, f"{part}:{parent}", package, label, version,
            uses, st.st_uid, st.st_gid, oct(stat.S_IMODE(st.st_mode)), st.st_size, ctx)

def scan(raw, partitions, aapt):
    ROOTDIR.mkdir(parents=True,exist_ok=True)
    rows=[]
    errors=[]
    scan_errors=[]
    stats=[]
    try:
        for part in partitions:
            name=part["partition"]
            image_dir=ROOTDIR/"images"
            mnt=ROOTDIR/"mounted"
            image_dir.mkdir(exist_ok=True);mnt.mkdir(exist_ok=True)
            mounted=False
            try:
                print(f"Stage 3: scanning {name} ({part['filesystem']})",flush=True)
                tool(geometry.TOOLS/"lpunpack",
                     f"--slot={part['metadata_slot']}", f"--partition={name}",
                     raw, image_dir)
                image=image_dir/(name+".img")
                if not image.is_file():
                    raise RuntimeError("Partition image is missing after lpunpack")
                fs=geometry.identify_filesystem(image)
                if fs not in ("erofs","ext4"):
                    raise RuntimeError(f"Unsupported filesystem {fs}")
                mount_options = "ro,loop" if fs=="erofs" else "ro,loop,noload"
                tool("mount","-t",fs,"-o",mount_options,image,mnt)
                mounted=True
                found=0
                for current,_,files in os.walk(mnt,followlinks=False):
                    for name_in_dir in files:
                        if not name_in_dir.lower().endswith(".apk"):
                            continue
                        path=Path(current)/name_in_dir
                        record=entry_info(path,mnt,name,aapt,errors)
                        if record:
                            rows.append(record)
                            found+=1
                stats.append({"partition":name,"filesystem":fs,"apks":found,
                              "source_image_bytes":image.stat().st_size})
                print(f"  {name}: {found} APKs, {sum(1 for x in rows if x[0]==name and not x[4])} unparsed package IDs",flush=True)
            except Exception as exc:
                scan_errors.append(f"{name}: {type(exc).__name__}: {exc}")
                print(f"ERROR in {name}: {exc}",flush=True)
            finally:
                if mounted:
                    p=subprocess.run(["umount",str(mnt)],capture_output=True,text=True)
                    if p.returncode:
                        scan_errors.append(f"{name}: umount failed: {p.stderr}")
                shutil.rmtree(image_dir,ignore_errors=True)
        return rows, errors, scan_errors, stats
    finally:
        shutil.rmtree(ROOTDIR,ignore_errors=True)

def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    try:
        aapt=select_aapt()
        print("Selected Android package parser:",aapt,flush=True)
        checksums=geometry.check_archive()
        sparse=geometry.extract_super()
        raw=geometry.get_raw_super(sparse)
        partitions=geometry.audit_partitions(raw)
        rows,errors,scan_errors,stats=scan(raw,partitions,aapt)
        rows.sort(key=lambda r:(r[0],r[1].lower()))
        with (REPORT/"APK_DETAILS.csv").open("w",newline="",encoding="utf-8") as out:
            w=csv.writer(out);w.writerow(COLUMNS);w.writerows(rows)
        with (REPORT/"APK_DETAILS.tsv").open("w",newline="",encoding="utf-8") as out:
            w=csv.writer(out,delimiter="\t");w.writerow(COLUMNS);w.writerows(rows)
        write("APK_LIST.txt","\n".join(r[1] for r in rows)+"\n")
        write("APK_DETAILS.json",json.dumps([dict(zip(COLUMNS,r)) for r in rows],indent=2,ensure_ascii=False)+"\n")
        by_part=collections.defaultdict(list)
        for r in rows:by_part[r[0]].append(r)
        write("APK_BY_PARTITION.txt","".join(f"==== {part} ({len(entries)} APKs) ====\n" +
                 "".join(f"{r[4] or '[UNPARSED]'}\t{r[1]}\t{r[5]}\n" for r in entries)+"\n"
                 for part,entries in sorted(by_part.items())))
        write("APK_PACKAGE_ERRORS.txt","\n".join(errors)+"\n" if errors else "All APK package IDs parsed.\n")
        write("PARTITION_SCAN_ERRORS.txt","\n".join(scan_errors)+"\n" if scan_errors else "All populated partitions scanned successfully.\n")
        summary={
            "device":"yunluo","region":"Global MIXM","version":VERSION,
            "source_archive":NAME,"source_md5_verified":checksums["md5"]==MD5,
            "source_md5":checksums["md5"],"source_sha256":checksums["sha256"],
            "partitions_expected":len(partitions),"partitions_scanned":len(stats),
            "total_apk_files":len(rows),"total_parsed_package_ids":sum(bool(r[4]) for r in rows),
            "distinct_android_package_ids":len({r[4] for r in rows if r[4]}),
            "package_id_parse_errors":len(errors),"partition_scan_errors":len(scan_errors),
            "per_partition":stats,
            "filesystem_source":"unmodified original stock Xiaomi super.img",
            "changes_to_firmware":False,
        }
        write("APK_SUMMARY.json",json.dumps(summary,indent=2)+"\n")
        table="\n".join(f"| {s['partition']} | {s['filesystem']} | {s['apks']} |" for s in stats)
        status="PASS" if not scan_errors and not errors and len(stats)==len(partitions) and len(rows)>0 else "REVIEW REQUIRED"
        md=f"""# Redmi Pad yunluo — HyperOS Build 1, Stage 3 APK inventory

**{status}** — source firmware OS1.0.9.0.ULYMIXM (Global MIXM), read-only.

- Verified stock archive MD5: {checksums['md5']}
- Stock archive SHA256: {checksums['sha256']}
- Populated logical partitions scanned: {len(stats)} / {len(partitions)}
- APK files found: **{len(rows)}**
- Package IDs parsed: **{sum(bool(r[4]) for r in rows)}**; parse failures: **{len(errors)}**
- Distinct package IDs: **{summary['distinct_android_package_ids']}**
- Changes: **none** (no removals, patching, or firmware re-packaging).

| Partition | FS | APK files |
|---|---|---:|
{table}

Files: APK_LIST.txt (every original path), APK_DETAILS.csv/tsv/json (full details),
APK_BY_PARTITION.txt, APK_PACKAGE_ERRORS.txt, APK_SUMMARY.json,
partition geometry and source verification. APEX/CAPEX-contained APK files are
not enumerated as independent APKs unless visible in the mounted filesystem.
"""
        write("STAGE3_RESULTS.md",md)
        write("status.txt",f"{status}: {len(rows)} APK paths, {len(errors)} package identity errors, {len(scan_errors)} partition scan errors, {time.monotonic()-start:.1f}s\n")
        print(md,flush=True)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write(md)
        if scan_errors or not rows or len(stats)!=len(partitions):
            raise RuntimeError("Incomplete Stage 3 partition inventory; see reports")
        # Missing package IDs require manual review before any debloat decisions, but paths remain intact.
    except Exception as exc:
        if not (REPORT/"status.txt").exists():
            write("status.txt",f"FAILED: {type(exc).__name__}: {exc}\n")
        raise
    finally:
        # geometry.get_raw_super creates an independent temporary tree.
        shutil.rmtree(geometry.TEMP,ignore_errors=True)

if __name__=="__main__":
    main()
