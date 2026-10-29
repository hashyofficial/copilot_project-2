#!/usr/bin/env python3
"""EXPERIMENTAL HyperOS 1 yunluo Build 1: 101 user-selected APK packages removed.

Read only the pinned, MD5-verified Xiaomi Global stock. Preserve LP metadata,
unmodified EROFS images, retained APK checksums and labels. Rebuild only affected
EROFS partitions, using verified first-party partition offsets (not MIUI offsets).
No vbmeta/ZIP/release here; packaging is separate and requires full validation.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"workflow"/"hyperos"))
import geometry
from firmware import MD5, NAME, VERSION
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage3"))
from scan import select_aapt, badging

ROOT=Path(__file__).resolve().parents[1]
REPORT=Path(os.environ["BUILD1_REPORTS"])
STAGING=Path(os.environ["BUILD1_PRIVATE"])
ARCHIVE=Path(os.environ["HYPEROS_ARCHIVE"])
WORK=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"yunluo-hyperos-test-build"
RAW_BYTES=9126805504
RAW_SHA="965f791ef796d4346b4abf95fad216a90084ed869ef2b6fbae1993d5683c686c"
PARTITIONS={"product_a","system_a","system_ext_a","mi_ext_a"}
PROTECT={
    "android","com.google.android.gms","com.google.android.gsf",
    "com.android.vending","com.google.android.webview","com.google.android.trichromelibrary",
    "com.miui.securitycenter","com.miui.cleaner","com.google.android.setupwizard",
    "com.google.android.partnersetup","com.miui.home","com.android.systemui",
    "com.android.settings","com.android.provision","com.lbe.security.miui",
    "com.android.providers.settings","com.android.providers.downloads","com.android.providers.contacts",
    "com.google.android.packageinstaller","com.miui.gallery",
}

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(8*1024*1024),b""):h.update(part)
    return h.hexdigest()

def run(*parts):
    cmd=list(map(str,parts))
    print("+", " ".join(cmd),flush=True)
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(f"{cmd[0]} failed [{p.returncode}]: {(p.stderr or p.stdout)[-2000:]}")
    return p.stdout

def write(name,value):
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/name).write_text(value,encoding="utf-8")

def selected():
    file=ROOT/"config/hyperos-build1-test-selected.txt"
    result={}
    for line in file.read_text().splitlines():
        if line.startswith("#") or not line.strip():continue
        m=re.fullmatch(r"\s*(\d+)\s+([A-Za-z0-9_.]+)\s*",line)
        if not m:raise RuntimeError("Invalid selected package entry: "+line)
        id=int(m.group(1));pkg=m.group(2)
        if pkg in result:raise RuntimeError("Repeated package: "+pkg)
        result[pkg]=id
    if len(result)!=101 or PROTECT & result.keys():
        raise RuntimeError("Expected exactly 101 selected packages, with critical keeps intact")
    if result.get("com.android.stk") != 158:
        raise RuntimeError("Selection fingerprint mismatch: SIM Toolkit")
    return result

def super_regions(raw):
    layout=run(geometry.TOOLS/"lpdump","-s",0,raw)
    if "Metadata version: 10.2" not in layout or "Header flags: virtual_ab_device" not in layout:
        raise RuntimeError("HyperOS source LP metadata changed")
    matches={}
    for start,end,name,sectors in re.findall(
        r"(?m)^super:\s+(\d+)\s+\.\.\s+(\d+):\s+([a-z0-9_]+)\s+\((\d+)\s+sectors\)\s*$",layout
    ):
        first,last,count=map(int,(start,end,sectors))
        if last-first!=count or name in matches:raise RuntimeError("Invalid LP mapping "+name)
        matches[name]=(first*512,count*512)
    expected={"odm_dlkm_a":348160,"product_a":2592829440,"system_a":866062336,
              "system_ext_a":689496064,"vendor_a":1041645568,"vendor_dlkm_a":11292672,
              "mi_ext_a":555696128}
    if {k:v[1] for k,v in matches.items()}!=expected:
        raise RuntimeError("HyperOS stock partition geometry changed, refusing hardcoded layout")
    for name,(start,length) in matches.items():
        if start%4096 or length%4096 or start+length>RAW_BYTES:
            raise RuntimeError("Misaligned/out-of-bounds LP extent: "+name)
    return matches

def file_fingerprint(path):
    st=path.lstat()
    try:selinux=os.getxattr(path,"security.selinux",follow_symlinks=False)
    except OSError:selinux=b""
    return (st.st_size,st.st_uid,st.st_gid,st.st_mode&0o7777,selinux,sha(path))

def scan_apks(mount,aapt):
    # Package-ID verification is against the mounted original EROFS (no trusting labels).
    entries=[]
    for base,_,files in os.walk(mount,followlinks=False):
        for name in files:
            if not name.lower().endswith(".apk"):continue
            apk=Path(base)/name
            if not apk.is_file() or apk.is_symlink() or apk.stat().st_size==0:continue
            ident,_,_,_=badging(aapt,apk)
            entries.append((ident,apk,"/"+apk.relative_to(mount).as_posix()))
    return entries

def erofs_uuid(path):
    output=run("dump.erofs","-s",path)
    m=re.search(r"(?m)^Filesystem UUID:\s*([0-9a-fA-F-]{36})\s*$",output)
    if not m:raise RuntimeError("Missing source EROFS UUID")
    return m.group(1)

def wipe_segment(target,start,capacity,source):
    if source.stat().st_size>capacity or source.stat().st_size%4096:
        raise RuntimeError("Rebuilt image exceeds original allocated partition extent")
    with target.open("r+b") as out,source.open("rb") as f:
        out.seek(start)
        shutil.copyfileobj(f,out,8*1024*1024)
        remaining=capacity-source.stat().st_size
        zero=b"\0"*(8*1024*1024)
        while remaining:
            size=min(remaining,len(zero));out.write(zero[:size]);remaining-=size

def build_one(raw,candidate,name,region,selected_ids,aapt):
    start,cap=region
    unpack=WORK/("unpack-"+name)
    unpack.mkdir()
    run(geometry.TOOLS/"lpunpack","--slot=0","--partition="+name,raw,unpack)
    src=unpack/(name+".img")
    if geometry.identify_filesystem(src)!="erofs" or src.stat().st_size!=cap:
        raise RuntimeError("Unexpected source EROFS partition "+name)
    run("fsck.erofs",src)
    mnt=WORK/("mnt-"+name);mnt.mkdir()
    run("mount","-t","erofs","-o","ro,loop",src,mnt)
    try:
        all_apps=scan_apks(mnt,aapt)
        found=[(pkg,apk,rel) for pkg,apk,rel in all_apps if pkg in selected_ids]
        if not found:
            raise RuntimeError("Expected selected APKs in "+name)
        # Avoid deleting shared overlay directories. Every directory exclusion must
        # contain only selected APKs; otherwise exclude just the selected APK file.
        by_parent={}
        for pkg,apk,rel in all_apps:
            by_parent.setdefault(apk.parent,[]).append(pkg)
        exclusions=[]
        checked=[]
        seen=set()
        for pkg,apk,rel in found:
            parent=apk.parent
            same=by_parent[parent]
            owned=(len(same)==1 and same[0]==pkg and
                   parent.relative_to(mnt).parts[0] not in ("overlay","product")
                   and len(parent.relative_to(mnt).parts)>=2)
            # /product/app/<app> is safe; /product/overlay (shared) is not.
            if parent.relative_to(mnt).parts[:2] in (("product","app"),("product","priv-app")):
                owned=len(same)==1 and len(parent.relative_to(mnt).parts)>=3
            # /system/app/<app> or /app/<app>, etc. The parent must not be
            # a shared package container with another APK.
            if len(parent.relative_to(mnt).parts)<2:
                owned=False
            removal="/"+parent.relative_to(mnt).as_posix() if owned else rel
            if removal in seen:raise RuntimeError("Duplicated exclusion "+removal)
            seen.add(removal);exclusions.append(removal)
            checked.append({"package_id":pkg,"source_apk":f"{name}:{rel}",
                            "exclude":removal,"method":"folder" if owned else "file"})
        # Verify all unselected APKs stay present after rebuild.
        retained={rel:(pkg,file_fingerprint(apk)) for pkg,apk,rel in all_apps if pkg not in selected_ids}
        retained_count=len(retained)
        uuid=erofs_uuid(src)
        built=WORK/(name+"-rebuilt.erofs")
        cmd=["mkfs.erofs","-z","lz4hc,9","-T","1230768000","-U",uuid]
        for item in exclusions:cmd.append("--exclude-path="+item.lstrip("/"))
        cmd.extend([str(built),str(mnt)])
        output=run(*cmd)
        write("mkfs-"+name+".log",output)
        run("fsck.erofs",built)
        if built.stat().st_size>cap:
            raise RuntimeError(f"EROFS size overflow {name}: {built.stat().st_size} > {cap}")
        verified=WORK/("verify-"+name);verified.mkdir()
        run("mount","-t","erofs","-o","ro,loop",built,verified)
        try:
            changed=scan_apks(verified,aapt)
            after={rel:(pkg,file_fingerprint(apk)) for pkg,apk,rel in changed}
            unexpected=sorted(set(after)-set(retained))
            missing=sorted(set(retained)-set(after))
            altered=sorted(rel for rel in set(after)&set(retained) if after[rel]!=retained[rel])
            surviving=[rel for pkg,apk,rel in changed if pkg in selected_ids]
            if unexpected or missing or altered or surviving:
                write("validation-"+name+".json",json.dumps({
                    "unexpected":unexpected,"missing":missing,"altered":altered,
                    "selected_surviving":surviving},indent=2))
                raise RuntimeError(f"Partition {name} retained APK validation failed: "
                                   f"{len(unexpected)} unexpected / {len(missing)} missing / "
                                   f"{len(altered)} altered / {len(surviving)} selected present")
        finally:
            run("umount",verified)
        wipe_segment(candidate,start,cap,built)
        return {"partition":name,"source_bytes":cap,"new_erofs_bytes":built.stat().st_size,
                "selected_apks":len(checked),"retained_apks":retained_count,
                "excluded":checked,"rebuild_uuid":uuid,
                "retained_apks_verified":True}
    finally:
        run("umount",mnt)
        shutil.rmtree(unpack,ignore_errors=True)

def main():
    REPORT.mkdir(parents=True,exist_ok=True);STAGING.mkdir(parents=True,exist_ok=True)
    begin=time.monotonic()
    try:
        expected=selected()
        check=geometry.check_archive()
        if check["sha256"]!="90562e6f369bb17cdaf67a86f2b72b16492fb1a63c86f7e389cf2ba306942530":
            raise RuntimeError("Unexpected stock archive SHA256")
        WORK.mkdir(parents=True,exist_ok=True)
        source=geometry.extract_super() # IMPORTANT: keeps stock archive for packaging
        original=WORK/"source-super.raw.img"
        run(geometry.TOOLS/"simg2img",source,original)
        if original.stat().st_size!=RAW_BYTES or sha(original)!=RAW_SHA:
            raise RuntimeError("Source raw super SHA256 mismatch")
        regions=super_regions(original)
        aapt=select_aapt()
        candidate=WORK/"candidate-super.raw.img"
        run("cp","--reflink=auto","--sparse=always",original,candidate)
        reports=[]
        for name in sorted(PARTITIONS):
            print("Rebuilding HyperOS partition:",name,flush=True)
            reports.append(build_one(original,candidate,name,regions[name],expected,aapt))
        observed=[x["package_id"] for p in reports for x in p["excluded"]]
        if len(observed)!=102 or set(observed)!=set(expected) or len(observed)-len(set(observed))!=1:
            raise RuntimeError("Removal mapping mismatch: expected 101 packages, 102 APKs")
        modified=set(PARTITIONS)
        with original.open("rb") as before,candidate.open("rb") as after:
            for name,(start,length) in regions.items():
                if name in modified:continue
                before.seek(start);after.seek(start);remaining=length
                while remaining:
                    n=min(8*1024*1024,remaining)
                    if before.read(n)!=after.read(n):
                        raise RuntimeError("Untouched LP region differs: "+name)
                    remaining-=n
        for slot in (0,1):
            before=run(geometry.TOOLS/"lpdump","-s",slot,original)
            after=run(geometry.TOOLS/"lpdump","-s",slot,candidate)
            if before!=after:raise RuntimeError("LP metadata changed in slot "+str(slot))
        private=STAGING/"super.sparse.img"
        run(geometry.TOOLS/"img2simg",candidate,private)
        # Independently test sparse decoding roundtrip for the complete 9.1GB super.
        verify=WORK/"verify-super.raw.img"
        run(geometry.TOOLS/"simg2img",private,verify)
        if sha(verify)!=sha(candidate) or verify.stat().st_size!=RAW_BYTES:
            raise RuntimeError("Sparse encode-decode super checksum mismatch")
        del verify
        manifest={"build":"HyperOS 1 Global Build 1 TEST","status":"offline_checked_not_device_tested",
                  "source_firmware":VERSION,"source_md5":MD5,
                  "source_sha256":check["sha256"],"source_super_sha256":RAW_SHA,
                  "new_super_sparse_sha256":sha(private),"new_super_sparse_bytes":private.stat().st_size,
                  "source_raw_super_size":RAW_BYTES,
                  "selected_package_ids":sorted(expected),
                  "selected_package_count":101,"removed_apk_count":102,
                  "rebuilt_partitions":sorted(PARTITIONS),"source_lp_metadata_preserved":True,
                  "retained_apks_same_bytes_owner_mode_selinux":True,
                  "other_lp_regions_unchanged":True,
                  "partitions":reports,
                  "warnings":["Experimental: core telephony packages removed",
                              "Boot compatibility not guaranteed",
                              "Full fastboot stock flashes may erase user data",
                              "Clean boot requires physical-device testing"]}
        (STAGING/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        write("build1-super-verification.json",json.dumps(manifest,indent=2)+"\n")
        write("status.txt",f"PASS: 101 selected packages; 102 APKs removed; {len(reports)} partitions rebuilt; source LP unchanged; {time.monotonic()-begin:.0f}s\n")
        print("HyperOS Stage 4 super image offline checked; test packaging is next",flush=True)
    except Exception as exc:
        write("status.txt",f"FAIL: {type(exc).__name__}: {exc}\n")
        raise
    finally:
        shutil.rmtree(WORK,ignore_errors=True)
        shutil.rmtree(geometry.TEMP,ignore_errors=True)
if __name__=="__main__":main()
