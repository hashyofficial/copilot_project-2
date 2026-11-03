#!/usr/bin/env python3
"""Read-only extraction of unmodified vendor_dlkm_a and odm_dlkm_a from stock yunluo HyperOS 1 super.img.

Creates a two-image ZIP only: vendor_dlkm.img and odm_dlkm.img.
This is NOT a firmware rebuild, flash package, or new kernel build.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"workflow"/"hyperos"))
from firmware import MD5, NAME

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/".tools"/"android-tools-static"
ARCHIVE=Path(os.environ["HYPEROS_ARCHIVE"])
WORK=Path(os.environ["DLKM_WORK"])
OUTPUT=Path(os.environ["DLKM_OUTPUT"])
STOCK_SHA256="90562e6f369bb17cdaf67a86f2b72b16492fb1a63c86f7e389cf2ba306942530"
STOCK_RAW_SUPER_SHA256="965f791ef796d4346b4abf95fad216a90084ed869ef2b6fbae1993d5683c686c"
RAW_BYTES=9_126_805_504
PARTITIONS={
    "vendor_dlkm_a":("vendor_dlkm.img",11_292_672),
    "odm_dlkm_a":("odm_dlkm.img",348_160),
}
ZIP_NAME="yunluo_HyperOS1_Global_OS1.0.9.0_VENDOR_ODM_DLKM_IMAGES.zip"
CHUNK=8*1024*1024

def digest(p,algo="sha256"):
    h=hashlib.new(algo)
    with p.open("rb") as f:
        for b in iter(lambda:f.read(CHUNK),b""):
            h.update(b)
    return h.hexdigest()

def call(*argv):
    p=subprocess.run([str(a) for a in argv],text=True,capture_output=True)
    if p.returncode:
        raise RuntimeError("Failed command "+repr(argv)+": "+p.stderr[-2500:])
    return p.stdout

def main():
    WORK.mkdir(parents=True,exist_ok=True)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if ARCHIVE.name!=NAME or not ARCHIVE.is_file():
        raise RuntimeError("Expected checksum-pinned Xiaomi Global HyperOS stock archive "+NAME)
    actual_md5=digest(ARCHIVE,"md5")
    actual_sha256=digest(ARCHIVE)
    if actual_md5!=MD5 or actual_sha256!=STOCK_SHA256:
        raise RuntimeError("Stock firmware archive integrity mismatch: "+actual_md5+" "+actual_sha256)
    print("Verified untouched original Xiaomi HyperOS 1 Global OTA archive MD5 and SHA256",flush=True)

    sparse=WORK/"stock-super.sparse.img"
    found=0
    with tarfile.open(ARCHIVE,"r|gz") as package:
        for member in package:
            path=PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("Unsafe stock archive entry "+member.name)
            if path.name=="super.img" and path.parent.name=="images" and member.isfile():
                if found:raise RuntimeError("Duplicate super.img")
                found+=1
                with package.extractfile(member) as src,sparse.open("wb") as out:
                    shutil.copyfileobj(src,out,CHUNK)
    if found!=1 or sparse.stat().st_size<5_000_000_000:
        raise RuntimeError("Unexpected missing or incomplete original super.img")
    ARCHIVE.unlink() # only local Actions runner temp copy, never source or Release assets
    with sparse.open("rb") as f:
        header=f.read(28)
    if len(header)!=28 or struct.unpack_from("<I",header)[0]!=0xED26FF3A:
        raise RuntimeError("Source super.img is not expected Android sparse format")
    print("Stock source sparse super.img bytes:",sparse.stat().st_size,flush=True)
    raw=WORK/"stock-super.raw.img"
    call(TOOLS/"simg2img",sparse,raw)
    sparse.unlink()
    if raw.stat().st_size!=RAW_BYTES or digest(raw)!=STOCK_RAW_SUPER_SHA256:
        raise RuntimeError("Unpacked raw super.img failed immutable Build4 stock-source hash check")
    print("Verified exact original stock raw super.img hash:",STOCK_RAW_SUPER_SHA256,flush=True)
    metadata=call(TOOLS/"lpdump","-s","0",raw)
    for part in PARTITIONS:
        if ("Name: "+part) not in metadata:
            raise RuntimeError("Missing expected logical partition in super metadata: "+part)
    unpack=WORK/"unpack"
    unpack.mkdir(exist_ok=True)
    record=[]
    for partition,(filename,expected_size) in PARTITIONS.items():
        call(TOOLS/"lpunpack","--slot=0","--partition="+partition,raw,unpack)
        from_img=unpack/(partition+".img")
        if not from_img.is_file() or from_img.stat().st_size!=expected_size:
            raise RuntimeError("Wrong image or capacity after lpunpack: "+partition)
        with from_img.open("rb") as f:
            f.seek(1024)
            magic=f.read(4)
        if magic!=bytes.fromhex("e2e1f5e0"):
            raise RuntimeError("Extracted partition must be intact EROFS: "+partition)
        dst=OUTPUT/filename
        from_img.rename(dst)
        info={"stock_partition":partition,"zip_filename":filename,
              "size_bytes":dst.stat().st_size,"filesystem":"EROFS",
              "sha256":digest(dst),"source_metadata_slot":0}
        record.append(info)
        print("Extracted:",json.dumps(info),flush=True)
    raw.unlink()
    target=OUTPUT/ZIP_NAME
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
        for info in record:
            archive.write(OUTPUT/info["zip_filename"],arcname=info["zip_filename"])
    with zipfile.ZipFile(target) as z:
        if sorted(z.namelist())!=sorted([x["zip_filename"] for x in record]):
            raise RuntimeError("ZIP does not contain exactly two requested images")
        if z.testzip():
            raise RuntimeError("ZIP CRC check failed")
        for info in record:
            if hashlib.sha256(z.read(info["zip_filename"])).hexdigest()!=info["sha256"]:
                raise RuntimeError("ZIP extracted image hash mismatch: "+info["zip_filename"])
    manifest={
        "device":"Xiaomi Redmi Pad Wi-Fi","codename":"yunluo","source_firmware":"HyperOS 1 Global OS1.0.9.0.ULYMIXM",
        "source_original_stock_archive":NAME,"source_archive_md5":actual_md5,
        "source_archive_sha256":actual_sha256,"source_original_raw_super_sha256":STOCK_RAW_SUPER_SHA256,
        "note":"Unmodified stock logical partition image contents; Build 4 preserves these original regions. Extraction only, not a kernel or firmware build.",
        "images":record,"zip_filename":ZIP_NAME,"zip_bytes":target.stat().st_size,
        "zip_sha256":digest(target)}
    (OUTPUT/"DLKM_VERIFICATION.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (OUTPUT/"DLKM_SHA256.txt").write_text(
        "".join(x["sha256"]+"  "+x["zip_filename"]+"\n" for x in record)+
        manifest["zip_sha256"]+"  "+ZIP_NAME+"\n",encoding="utf-8")
    for info in record:
        (OUTPUT/info["zip_filename"]).unlink() # keep ONLY two-image ZIP + checksums/manifest for upload
    print("PASS: extracted 2 complete raw EROFS logical images, validated ZIP CRC and SHA256",flush=True)
    print("ZIP",target.name,"bytes",target.stat().st_size,flush=True)

if __name__=="__main__":
    main()
