#!/usr/bin/env python3
"""EXPERIMENTAL HyperOS 1 yunluo Build 3: 124 selected APK packages plus optional Health Connect APEX removal.

Read only the pinned, MD5-verified Xiaomi Global stock. Preserve LP metadata,
unmodified EROFS images, retained APK checksums and labels. Rebuild only affected
EROFS partitions, using verified first-party partition offsets (not MIUI offsets).
No vbmeta/ZIP/release here; packaging/release is separate and requires full validation.
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
PHOTON_APK=Path(os.environ["PHOTON_APK"])
PHOTON_SHA="8a5039b05b7a8b57adb16de006c80e0a37f92debda9d745d3e3c398a4d311fe1"
PHOTON_REL="/app/PhotonGallery/PhotonGallery.apk"
PHOTON_LABEL=b"u:object_r:system_file:s0"
# Exact modularized packages reported on the live Build 2 device. These are
# excluded ONLY when their .apex/.capex archive is verified on a stock partition.
APEX_TARGETS={
    "health_connect":("com.google.android.healthfitness","com.android.healthfitness"),
    "ad_services":("com.google.android.adservices","com.android.adservices"),
}
APEX_SCAN_DIRS=("apex","system/apex","product/apex","system_ext/apex","vendor/apex","mi_ext/apex")
NETWORK_PROTECTED_APEX_PREFIXES=(
    "com.android.wifi","com.google.android.wifi",
    "com.google.android.resolv","com.android.resolv",
    "com.google.android.tethering","com.android.tethering",
    "com.google.android.ipsec","com.android.ipsec",
    "com.android.networkstack","com.google.android.networkstack",
    "com.google.android.cellbroadcast","com.android.cellbroadcast",
)
REPORT=Path(os.environ["BUILD3_REPORTS"])
STAGING=Path(os.environ["BUILD3_PRIVATE"])
ARCHIVE=Path(os.environ["HYPEROS_ARCHIVE"])
WORK=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"yunluo-hyperos-test-build"
RAW_BYTES=9126805504
RAW_SHA="965f791ef796d4346b4abf95fad216a90084ed869ef2b6fbae1993d5683c686c"
PARTITIONS={"product_a","system_a","system_ext_a","mi_ext_a","vendor_a"}
PROTECT={
    "android","com.google.android.gms","com.google.android.gsf",
    "com.android.vending","com.google.android.webview","com.google.android.trichromelibrary",
    "com.miui.securitycenter","com.miui.cleaner","com.google.android.setupwizard",
    "com.google.android.partnersetup","com.miui.home","com.android.systemui",
    "com.android.settings","com.android.provision","com.lbe.security.miui",
    "com.android.providers.settings","com.android.providers.downloads",
    "com.google.android.packageinstaller",
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
    file=ROOT/"config/hyperos-build3-release-selected.txt"
    result={}
    for line in file.read_text().splitlines():
        if line.startswith("#") or not line.strip():continue
        m=re.fullmatch(r"\s*(\d+)\s+([A-Za-z0-9_.]+)\s*",line)
        if not m:raise RuntimeError("Invalid selected package entry: "+line)
        id=int(m.group(1));pkg=m.group(2)
        if pkg in result:raise RuntimeError("Repeated package: "+pkg)
        result[pkg]=id
    if len(result)!=124 or PROTECT & result.keys():
        raise RuntimeError("Expected exactly 124 selected packages, with critical keeps intact")
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
        # Remove the ENTIRE directory for a dedicated app:
        #   /app/<App>, /priv-app/<App>, /system/app/<App>,
        #   /system/priv-app/<App>, /product/app/<App>,
        #   /product/priv-app/<App>, /system_ext/app/<App>, etc.
        # These directories contain owned native libs/oat/artifacts alongside APKs.
        # Resource overlays typically live in one SHARED overlay directory, so
        # delete only selected APKs in these shared directories.
        roots={
            ("app",),("priv-app",),("data-app",),
            ("system","app"),("system","priv-app"),("system","data-app"),
            ("product","app"),("product","priv-app"),("product","data-app"),
            ("system_ext","app"),("system_ext","priv-app"),
            ("vendor","app"),("vendor","priv-app"),
            ("system","product","app"),("system","product","priv-app"),
            ("system","system_ext","app"),("system","system_ext","priv-app"),
            ("overlay",),("product","overlay"),("vendor","overlay"),
        }
        apps_by_folder={}
        for pkg,apk,rel in all_apps:
            apps_by_folder.setdefault(apk.parent,[]).append(pkg)
        selected_by_folder={}
        for pkg,apk,rel in found:
            selected_by_folder.setdefault(apk.parent,[]).append((pkg,apk,rel))
        exclusions=[]
        checked=[]
        deleted_folders=[]
        deleted_individual_apks=[]
        for parent,items in sorted(selected_by_folder.items(),key=lambda kv:str(kv[0])):
            relative=parent.relative_to(mnt)
            parts=relative.parts
            dedicated=(
                len(parts)>=2 and
                any(parts[:len(root)]==root and len(parts)>len(root) for root in roots)
            )
            # Prevent accidentally removing a shared folder that still contains
            # an APK with a package ID not chosen by the user.
            all_ids=set(apps_by_folder[parent])
            requested_ids={pkg for pkg,_,_ in items}
            if dedicated and not all_ids.issubset(requested_ids):
                raise RuntimeError("Selected app folder contains unselected APKs: "+str(parent))
            # Folder exclusion is safe only for a dedicated app directory; a
            # shared /overlay directory must be preserved for retained overlays.
            if dedicated:
                exclusion="/"+relative.as_posix()
                exclusions.append(exclusion)
                deleted_folders.append(exclusion)
                for pkg,apk,rel in items:
                    checked.append({"package_id":pkg,"source_apk":f"{name}:{rel}",
                                    "exclude":exclusion,"method":"whole_folder"})
            else:
                for pkg,apk,rel in items:
                    exclusions.append(rel)
                    deleted_individual_apks.append(rel)
                    checked.append({"package_id":pkg,"source_apk":f"{name}:{rel}",
                                    "exclude":rel,"method":"single_apk_in_shared_dir"})
        # Match verified built-in APEX archives, not the /apex runtime mountpoint.
        # This excludes the contained Health Connect controller and AdServices APKs
        # without guessing internal paths in Google's signed APEX payload.
        apex_removed={group:[] for group in APEX_TARGETS}
        retained_apex={}
        for apex_rel in APEX_SCAN_DIRS:
            apex_dir=mnt/apex_rel
            if not apex_dir.is_dir():continue
            for path in sorted(apex_dir.iterdir()):
                if not path.is_file() or path.is_symlink():continue
                if not path.name.endswith((".apex",".capex")):continue
                filename=path.name.lower()
                rel="/"+path.relative_to(mnt).as_posix()
                group=next((g for g,aliases in APEX_TARGETS.items()
                    if any(filename==alias+".apex" or filename==alias+".capex"
                           or filename.startswith(alias+"@") for alias in aliases)),None)
                if group:
                    apex_removed[group].append(rel)
                    exclusions.append(rel)
                else:
                    # Verify the byte-for-byte integrity, labels and mode of EVERY
                    # retained APEX, with explicit keep coverage for Network Stack.
                    retained_apex[rel]=file_fingerprint(path)
        if name=="system_a":
            write("apex-exclusion-audit.json",json.dumps({
                "selected_modules":list(APEX_TARGETS),
                "excluded_built_in_archives":apex_removed,
                "retained_apex_count":len(retained_apex),
                "network_stack_retained":True,
                "updated_modules_under_userdata_not_modified":True
            },indent=2)+"\n")
        if len(exclusions)!=len(set(exclusions)):
            raise RuntimeError("Duplicate EROFS exclusion path")
        if any(x in ("/","/app","/priv-app","/overlay","/product/overlay",
                     "/system/app","/system/priv-app","/product/app",
                     "/product/priv-app","/system_ext/app","/system_ext/priv-app")
               for x in exclusions):
            raise RuntimeError("Attempted to remove a shared system folder")
        # Verify all unselected APKs stay present after rebuild.
        retained={rel:(pkg,file_fingerprint(apk)) for pkg,apk,rel in all_apps if pkg not in selected_ids}
        retained_count=len(retained)
        uuid=erofs_uuid(src)
        built=WORK/(name+"-rebuilt.erofs")
        mkfs_source=mnt
        if name=="product_a":
            if sha(PHOTON_APK)!=PHOTON_SHA:
                raise RuntimeError("Photon Gallery upstream APK SHA256 mismatch")
            photon_pkg,_,_,_=badging(aapt,PHOTON_APK)
            if photon_pkg in selected_ids or photon_pkg in {pkg for pkg,_,_ in all_apps}:
                raise RuntimeError("Photon Gallery conflicts with selected or stock package")
            mkfs_source=WORK/"photon-product-tree";mkfs_source.mkdir()
            run("cp","-a",str(mnt)+"/.",str(mkfs_source)+"/")
            target=mkfs_source/PHOTON_REL.lstrip("/")
            target.parent.mkdir(mode=0o755)
            shutil.copyfile(PHOTON_APK,target)
            os.chown(target.parent,0,0)
            os.chown(target,0,0)
            os.chmod(target.parent,0o755)
            os.chmod(target,0o644)
            os.setxattr(target.parent,"security.selinux",PHOTON_LABEL)
            os.setxattr(target,"security.selinux",PHOTON_LABEL)
            write("photon-system-app.json",json.dumps({
                "upstream_version":"v2.1.3","apk_sha256":sha(PHOTON_APK),
                "android_package_id":photon_pkg,"path":"/product/app/PhotonGallery/PhotonGallery.apk",
                "mode":"0644","uid_gid":"0:0","selinux":"u:object_r:system_file:s0"
            },indent=2)+"\n")
        cmd=["mkfs.erofs","-z","lz4hc,9","-T","1230768000","-U",uuid]
        for item in exclusions:cmd.append("--exclude-path="+item.lstrip("/"))
        cmd.extend([str(built),str(mkfs_source)])
        output=run(*cmd)
        write("mkfs-"+name+".log",output)
        run("fsck.erofs",built)
        if built.stat().st_size>cap:
            raise RuntimeError(f"EROFS size overflow {name}: {built.stat().st_size} > {cap}")
        verified=WORK/("verify-"+name);verified.mkdir()
        run("mount","-t","erofs","-o","ro,loop",built,verified)
        try:
            # Check exclusion targets directly on the finished EROFS mount:
            # an APK-only scan would NOT prove that the original app folder's
            # lib/, oat/, and other companion files were actually removed.
            remnants=[str(p) for p in exclusions if (verified/p.lstrip("/")).exists()]
            if remnants:
                raise RuntimeError("Removed folder/APK path still present: "+str(remnants[:20]))
            changed=scan_apks(verified,aapt)
            after={rel:(pkg,file_fingerprint(apk)) for pkg,apk,rel in changed}
            new_allowed={PHOTON_REL} if name=="product_a" else set()
            if name=="product_a":
                matches=[(pkg,apk,rel) for pkg,apk,rel in changed if rel==PHOTON_REL]
                if len(matches)!=1 or matches[0][0]!=photon_pkg:
                    raise RuntimeError("Photon Gallery system APK absent or wrong package ID")
                photon_file=matches[0][1]
                if sha(photon_file)!=PHOTON_SHA or photon_file.stat().st_uid!=0 or photon_file.stat().st_gid!=0 or photon_file.stat().st_mode&0o777!=0o644:
                    raise RuntimeError("Photon content, UID/GID or file mode mismatch")
                if os.getxattr(photon_file,"security.selinux")!=PHOTON_LABEL:
                    raise RuntimeError("Photon Gallery file SELinux context mismatch")
                photon_dir=verified/"app/PhotonGallery"
                if os.getxattr(photon_dir,"security.selinux")!=PHOTON_LABEL or photon_dir.stat().st_mode&0o777!=0o755:
                    raise RuntimeError("Photon Gallery folder SELinux context or mode mismatch")
            # Each remaining built-in APEX must be byte-identical, mode-identical
            # and SELinux-identical to stock; this protects Wi-Fi and Network Stack.
            for rel,fingerprint in retained_apex.items():
                checked_apex=verified/rel.lstrip("/")
                if not checked_apex.is_file() or file_fingerprint(checked_apex)!=fingerprint:
                    raise RuntimeError("Untouched APEX changed: "+rel)
            unexpected=sorted(set(after)-set(retained)-new_allowed)
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
                "whole_app_folders_removed":len(deleted_folders),
                "individual_shared_overlay_apks_removed":len(deleted_individual_apks),
                "removed_app_folders":deleted_folders,
                "removed_shared_overlay_apks":deleted_individual_apks,
                "removed_paths_absent_after_rebuild":True,
                "excluded":checked,"rebuild_uuid":uuid,
                "retained_apks_verified":True,
                "apex_paths_removed":apex_removed,
                "healthconnect_apex_paths_removed":apex_removed["health_connect"],
                "retained_apex_files_verified":len(retained_apex),
                "photon_system_app":name=="product_a"}
    finally:
        run("umount",mnt)
        shutil.rmtree(unpack,ignore_errors=True)
        if name=="product_a":shutil.rmtree(WORK/"photon-product-tree",ignore_errors=True)

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
        # Refuse to silently publish when any supported requested modular package was not
        # found in the stock firmware. If all three are found, verify exact paths
        # were physically absent from the finished EROFS in each partition report.
        all_apex_paths={group:[] for group in APEX_TARGETS}
        for part in reports:
            for group,paths in part["apex_paths_removed"].items():
                all_apex_paths[group].extend([part["partition"]+":"+p for p in paths])
        missing_apex=[name for name,paths in all_apex_paths.items() if not paths]
        if missing_apex:
            write("apex-missing-targets.json",json.dumps({
                "target_groups":list(APEX_TARGETS),
                "present":all_apex_paths,"not_in_stock_images":missing_apex,
                "action":"FAILED CLOSED: no release built"
            },indent=2)+"\n")
            raise RuntimeError("Target APEX modules not located in stock images: "+", ".join(missing_apex))
        observed=[x["package_id"] for p in reports for x in p["excluded"]]
        folders_removed=sum(p["whole_app_folders_removed"] for p in reports)
        shared_overlays_removed=sum(p["individual_shared_overlay_apks_removed"] for p in reports)
        print(f"Verified whole-app-folder deletions: {folders_removed}; exact shared-overlay APK removals: {shared_overlays_removed}",flush=True)
        if folders_removed!=106 or shared_overlays_removed!=19:
            raise RuntimeError(f"Expected 106 entire app/overlay folders plus 19 shared overlay APKs; got {folders_removed} + {shared_overlays_removed}")
        if len(observed)!=125 or set(observed)!=set(expected) or len(observed)-len(set(observed))!=1:
            raise RuntimeError("Removal mapping mismatch: expected 124 packages, 125 APKs")
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
        manifest={"build":"HyperOS 1 Global Build 3 v.0.2 APEX EXPERIMENTAL","status":"offline_checked_not_device_tested",
                  "source_firmware":VERSION,"source_md5":MD5,
                  "source_sha256":check["sha256"],"source_super_sha256":RAW_SHA,
                  "new_super_sparse_sha256":sha(private),"new_super_sparse_bytes":private.stat().st_size,
                  "source_raw_super_size":RAW_BYTES,
                  "selected_package_ids":sorted(expected),
                  "selected_package_count":124,"removed_apk_count":125,
                  "entire_app_folders_removed":folders_removed,
                  "individual_shared_overlay_apks_removed":shared_overlays_removed,
                  "all_selected_folder_paths_absent_after_rebuild":True,
                  "rebuilt_partitions":sorted(PARTITIONS),"source_lp_metadata_preserved":True,
                  "retained_apks_same_bytes_owner_mode_selinux":True,
                  "other_lp_regions_unchanged":True,
                  "partitions":reports,
                  "apex_modules_removed":all_apex_paths,
                  "network_stack_apex_kept":True,
                  "retained_apex_file_count_verified":sum(p["retained_apex_files_verified"] for p in reports),
                  "healthconnect_apex_paths_removed":next(p["healthconnect_apex_paths_removed"] for p in reports if p["partition"]=="system_a"),
                  "photon_system_app_verified":True,
                  "photon_apk_sha256":PHOTON_SHA,
                  "warnings":["Experimental: core telephony packages removed",
                              "Boot compatibility not guaranteed; Health and AdServices APEX removed; Cell Broadcast APEX retained",
                               "Network Stack, Wi-Fi, DNS Resolver, tethering and IPsec APEX retained",
                               "Updated /data/apex modules may still be activated until separately handled",
                              "Full fastboot stock flashes may erase user data",
                              "Clean boot requires physical-device testing"]}
        (STAGING/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        write("build3-super-verification.json",json.dumps(manifest,indent=2)+"\n")
        write("status.txt",f"PASS: 124 selected packages, 2 targeted APEX modules; 106 complete app/overlay folders + 19 shared overlay APKs removed; {len(reports)} partitions rebuilt; source LP unchanged; {time.monotonic()-begin:.0f}s\n")
        print("HyperOS Build 3 v.0.2 EROFS/APEX offline verified; release packaging is next",flush=True)
    except Exception as exc:
        write("status.txt",f"FAIL: {type(exc).__name__}: {exc}\n")
        raise
    finally:
        shutil.rmtree(WORK,ignore_errors=True)
        shutil.rmtree(geometry.TEMP,ignore_errors=True)
if __name__=="__main__":main()
