#!/usr/bin/env python3
"""Package verified HyperOS Build 3 test image as complete ORIGINAL Xiaomi fastboot ZIP.

Only super.img, main vbmeta.img, crclist.txt and sparsecrclist.txt differ.
No tag, release, flash operation, or signing. Requires unlocked bootloader.
"""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import tarfile
import zipfile
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"workflow"/"hyperos"))
from firmware import VERSION,NAME,MD5
from geometry import digest
from hyperos_crc import sparse_crc, crc_line, replace_crc

ROOT=Path(__file__).resolve().parents[1]
STAGING=Path(os.environ["BUILD3_PRIVATE"])
REPORT=Path(os.environ["BUILD3_REPORTS"])
ARCHIVE=Path(os.environ["HYPEROS_ARCHIVE"])
OUT=Path(os.environ["BUILD3_OUTPUT"])
ZIP_NAME="yunluo_HyperOS1_Global_v.0.2_Build3_Fastboot_FULL.zip"
ROOT_NAME="yunluo_global_images_OS1.0.9.0.ULYMIXM_14.0"
EXPECTED_ORIGINAL_VBMETA_SHA="cc34aa04532fc46f70558d0cd98bc4a4f008e9aa795ac9762cec220fd52c80a0"
CHANGED={"images/super.img","images/vbmeta.img","images/crclist.txt","images/sparsecrclist.txt"}
CHUNK=8*1024*1024

def fail(text):raise RuntimeError(text)
def hashfile(file):
    h=hashlib.sha256()
    with file.open("rb") as f:
        for b in iter(lambda:f.read(CHUNK),b""):h.update(b)
    return h.hexdigest()
def write(name,content):
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/name).write_text(content,encoding="utf-8")
def checksum(source):
    h=hashlib.sha256()
    with source:
        for b in iter(lambda:source.read(CHUNK),b""):h.update(b)
    return h.hexdigest()
def zinfo(name,mode,mtime,store=False):
    t=datetime.datetime.fromtimestamp(max(mtime,315532800),datetime.timezone.utc)
    info=zipfile.ZipInfo(name,(t.year,t.month,t.day,t.hour,t.minute,t.second))
    info.create_system=3
    info.external_attr=(stat.S_IFREG|(mode&0o7777))<<16
    info.compress_type=zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
    info._compresslevel=None if store else 1
    return info
def append(z,info,source):
    h=hashlib.sha256()
    with z.open(info,"w",force_zip64=True) as out:
        while b:=source.read(CHUNK):
            out.write(b);h.update(b)
    return h.hexdigest()
def patch_vbmeta(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED_ORIGINAL_VBMETA_SHA:
        fail("Source vbmeta original hash mismatch")
    if data[:4]!=b"AVB0" or len(data)<256:
        fail("Stock vbmeta AVB header invalid")
    alg=struct.unpack_from(">I",data,28)[0]
    flags=struct.unpack_from(">I",data,120)[0]
    if flags!=0 or alg not in (1,2,3,4,5,6):
        fail(f"Unexpected vbmeta algorithm/flags: {alg}, {flags}")
    out=bytearray(data)
    struct.pack_into(">I",out,120,3)
    changed=sum(a!=b for a,b in zip(data,out))
    if changed!=1:
        fail(f"VBMeta flags patch unexpectedly changed {changed} bytes")
    if struct.unpack_from(">I",out,120)[0]!=3:
        fail("AVB disabled flags missing")
    return bytes(out)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    m=json.loads((STAGING/"manifest.json").read_text())
    if (m["source_md5"]!=MD5 or m["selected_package_count"]!=124 or m["removed_apk_count"]!=125
        or m.get("entire_app_folders_removed")!=106
        or m.get("individual_shared_overlay_apks_removed")!=19
        or m.get("all_selected_folder_paths_absent_after_rebuild") is not True
        or not m["source_lp_metadata_preserved"] or not m["retained_apks_same_bytes_owner_mode_selinux"]
        or not m["photon_system_app_verified"]
        or not m["network_stack_apex_kept"]
        or any(not m["apex_modules_removed"].get(x) for x in ("health_connect","ad_services"))):
        fail("Modified super did not pass preflight")
    sparse=STAGING/"super.sparse.img"
    if hashfile(sparse)!=m["new_super_sparse_sha256"]:
        fail("Modified super SHA256 invalid")
    if digest(ARCHIVE,"md5")!=MD5:
        fail("Firmware archive MD5 mismatch")
    with sparse.open("rb") as f:new_crcs=sparse_crc(f)
    replacements={}
    original_crcs=None
    seen=set()
    unchanged={}
    keep_modes={}
    temp_zip=OUT/(ZIP_NAME+".incomplete")
    if temp_zip.exists():temp_zip.unlink()
    try:
        with zipfile.ZipFile(temp_zip,"w",allowZip64=True) as z,tarfile.open(ARCHIVE,"r|gz") as tgz:
            for entry in tgz:
                path=PurePosixPath(entry.name)
                if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0]!=ROOT_NAME:
                    fail("Unexpected stock firmware entry: "+entry.name)
                if entry.isdir():
                    continue
                if not entry.isfile() or entry.issym() or entry.islnk() or entry.isdev():
                    fail("Unexpected unsafe stock firmware type "+entry.name)
                rel=str(path.relative_to(ROOT_NAME))
                if rel in seen:fail("Duplicate stock package file "+rel)
                seen.add(rel)
                with tgz.extractfile(entry) as source:
                    if rel=="images/super.img":
                        original_crcs=sparse_crc(source)
                        keep_modes[rel]=(entry.mode,entry.mtime)
                        print("Source Xiaomi CRC segments:",len(original_crcs),flush=True)
                    elif rel in CHANGED:
                        replacements[rel]=source.read()
                        keep_modes[rel]=(entry.mode,entry.mtime)
                    else:
                        unchanged[rel]=append(z,zinfo(entry.name,entry.mode,entry.mtime),source)
                if len(seen)%10==0:print("Stock firmware files processed:",len(seen),flush=True)
            if not CHANGED.issubset(seen) or len(seen)<35 or original_crcs is None:
                fail("Original Xiaomi firmware file list incomplete")
            old_main=replacements["images/vbmeta.img"]
            new_main=patch_vbmeta(old_main)
            crclist=replacements["images/crclist.txt"].decode("utf-8")
            sparsecrclist=replacements["images/sparsecrclist.txt"].decode("utf-8")
            original_vbcrc=int(crc_line(crclist,"vbmeta_a").split()[1],16)
            if original_vbcrc!=zlib.crc32(old_main):
                fail("Cannot validate original vbmeta_a checksum")
            fields=crc_line(sparsecrclist,"super").split()
            if len(fields)!=len(original_crcs)+2 or int(fields[1])!=len(original_crcs):
                fail("Xiaomi stock super sparse CRC segments differ")
            if [int(x,16) for x in fields[2:]]!=original_crcs:
                fail("CRC calculation does not reproduce Xiaomi original super CRC values")
            new_crc=replace_crc(crclist,"vbmeta_a","vbmeta_a "+hex(zlib.crc32(new_main)))
            new_sparsecrc=replace_crc(sparsecrclist,"super",
                            "super "+str(len(new_crcs))+" "+" ".join(hex(x) for x in new_crcs))
            changed_payloads=[
                ("images/vbmeta.img",new_main),
                ("images/crclist.txt",new_crc.encode("utf-8")),
                ("images/sparsecrclist.txt",new_sparsecrc.encode("utf-8")),
            ]
            for rel,blob in changed_payloads:
                mode,mtime=keep_modes[rel]
                append(z,zinfo(ROOT_NAME+"/"+rel,mode,mtime),io.BytesIO(blob))
            mode,mtime=keep_modes["images/super.img"]
            with sparse.open("rb") as f:
                new_super_sha=append(z,zinfo(ROOT_NAME+"/images/super.img",mode,mtime,True),f)
            if new_super_sha!=m["new_super_sparse_sha256"]:
                fail("ZIP source super checksum mismatch")
        with zipfile.ZipFile(temp_zip,"r") as z:
            paths=z.namelist()
            if len(paths)!=len(seen) or {ROOT_NAME+"/"+k for k in seen}!=set(paths):
                fail("Fastboot ZIP file list differs from original Xiaomi")
            if z.testzip() is not None:fail("ZIP internal CRC failed")
            if z.read(ROOT_NAME+"/images/vbmeta.img")!=new_main:
                fail("vbmeta patch not present in ZIP")
            with z.open(ROOT_NAME+"/images/super.img") as file:
                if checksum(file)!=m["new_super_sparse_sha256"]:
                    fail("ZIP super image hash verification failed")
            if not {"flash_all.bat","flash_all.sh","flash_all_lock.bat","images/MT6789_Android_scatter.xml"}.issubset(seen):
                fail("Stock Xiaomi flashing scripts or scatter not found")
            for name in ("flash_all.bat","flash_all_lock.bat","flash_all.sh"):
                if hashlib.sha256(z.read(ROOT_NAME+"/"+name)).hexdigest()!=unchanged[name]:
                    fail("Original Xiaomi flashing script altered: "+name)
        final_zip=OUT/ZIP_NAME
        temp_zip.rename(final_zip)
        zip_sha=hashfile(final_zip)
        print("Built complete flashable fastboot test ZIP",final_zip.name,final_zip.stat().st_size,zip_sha,flush=True)
        # FULL ZIP verified; GitHub Release 2-GiB-per-file limit requires numbered asset segments.
        part_size=1_850_000_000
        parts=[]
        with final_zip.open("rb") as reader:
            idx=0
            while True:
                head=reader.read(part_size)
                if not head:break
                idx+=1
                out=OUT/(ZIP_NAME+f".part{idx:03d}")
                out.write_bytes(head)
                parts.append({"filename":out.name,"sha256":hashfile(out),"bytes":len(head)})
        if sum(x["bytes"] for x in parts)!=final_zip.stat().st_size:
            fail("Firmware split output byte count mismatch")
        overall=hashlib.sha256()
        for x in parts:
            with (OUT/x["filename"]).open("rb") as f:
                for b in iter(lambda:f.read(CHUNK),b""):overall.update(b)
        if overall.hexdigest()!=zip_sha:fail("Split reassembly checksum mismatch")
        report={"status":"offline_verified_NOT_device_boot_tested","device":"yunluo",
                "rom":"HyperOS 1 Global","source_version":VERSION,
                "source_md5":MD5,"selected_package_count":124,"removed_apk_count":125,
                "entire_app_folders_removed":m["entire_app_folders_removed"],
                "individual_shared_overlay_apks_removed":m["individual_shared_overlay_apks_removed"],
                "all_selected_folder_paths_absent_after_rebuild":m["all_selected_folder_paths_absent_after_rebuild"],
                "patched_main_vbmeta_sha256":hashlib.sha256(new_main).hexdigest(),
                "vbmeta_flags":3,"vbmeta_signature_invalid_after_patch":True,
                "other_firmware_files_unchanged":True,
                "stock_original_super_crc_segments":len(original_crcs),
                "modified_super_crc_segments":len(new_crcs),
                "modified_images":["images/super.img","images/vbmeta.img"],
                "updated_checksum_text":["images/crclist.txt","images/sparsecrclist.txt"],
                "full_zip_file":ZIP_NAME,"full_zip_bytes":final_zip.stat().st_size,
                "full_zip_sha256":zip_sha,"parts":parts,
                "flash_scripts_preserved":True,"original_flash_all_bat_sha256":unchanged["flash_all.bat"],
                "release_target":"v.0.2",
                "photon_system_app_verified":m["photon_system_app_verified"],
                "photon_apk_sha256":m["photon_apk_sha256"],
                "healthconnect_apex_paths_removed":m["healthconnect_apex_paths_removed"],
                "apex_modules_removed":m["apex_modules_removed"],
                "network_stack_apex_kept":m["network_stack_apex_kept"],
                "retained_apex_file_count_verified":m["retained_apex_file_count_verified"],
                "user_warning":"TEST firmware; unlocked bootloader required, never relock. Stock flash_all may erase userdata. Keep known-good rescue package."}
        write("FASTBOOT_TEST_VERIFICATION.json",json.dumps(report,indent=2)+"\n")
        (OUT/"ZIP_SHA256.txt").write_text(zip_sha+"  "+ZIP_NAME+"\n")
        (OUT/"PARTS_SHA256.txt").write_text("".join(x["sha256"]+"  "+x["filename"]+"\n" for x in parts))
        # Full reconstruction script for Windows users downloading GitHub Release assets.
        ps=r'''$ErrorActionPreference = "Stop"
$zip = "yunluo_HyperOS1_Global_v.0.2_Build3_Fastboot_FULL.zip"
$expected = (Get-Content "ZIP_SHA256.txt" -Raw).Split(" ")[0].Trim()
$parts = Get-ChildItem -File -Filter "$zip.part*" | Sort-Object Name
if ($parts.Count -lt 2) { throw "Missing release ZIP parts" }
$out = [System.IO.File]::Create($zip)
try {
    foreach ($part in $parts) {
        Write-Host "Joining $($part.Name)"
        $source = [System.IO.File]::OpenRead($part.FullName)
        try { $source.CopyTo($out) } finally { $source.Dispose() }
    }
} finally { $out.Dispose() }
$actual = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
if ($actual -ne $expected.ToLower()) { throw "SHA256 mismatch; do not flash" }
Write-Host "COMPLETE FASTBOOT ZIP VERIFIED: $zip"
'''
        (OUT/"WINDOWS_JOIN_FULL_FIRMWARE.ps1").write_text(ps,encoding="utf-8")
        (OUT/"DOWNLOAD_INSTRUCTIONS.txt").write_text(
            "HyperOS1 Yunluo v.0.2 Build3 FULL Xiaomi fastboot firmware\\n"
            "Release segments contain the COMPLETE firmware ZIP; download ALL .partNNN files\\n"
            "plus ZIP_SHA256.txt and WINDOWS_JOIN_FULL_FIRMWARE.ps1 into one directory.\\n"
            "PowerShell: powershell -ExecutionPolicy Bypass -File .\\\\WINDOWS_JOIN_FULL_FIRMWARE.ps1\\n"
            "Verify the complete reconstructed ZIP before extracting.\\n"
            "GitHub limits each release asset to 2 GiB; no expiring Actions artifacts used.\\n"
            "Never relock bootloader; stock flash_all.bat may erase your data.\\n")
        # GitHub release max asset size 2 GiB, omit the already-verified monolithic ZIP.
        final_zip.unlink()
        write("status.txt",f"PASS: full release ZIP verified, split into {len(parts)} release segments; SHA256 {zip_sha}\n")
    except Exception as exc:
        write("status.txt",f"FAIL: {type(exc).__name__}: {exc}\n")
        raise
    finally:
        if temp_zip.exists():temp_zip.unlink()
if __name__=="__main__":main()
