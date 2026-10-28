#!/usr/bin/env python3
"""Read-only Stage 2: audit HyperOS fastboot super geometry and image filesystems.

No APK removal, patching, image rebuilding, relabeling or firmware publication.
Based on read-only source inspection techniques from MIUI Build 10.
"""
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tarfile
import time

from firmware import DEVICE, MD5, NAME, REGION, VERSION

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(os.environ.get("HYPEROS_REPORTS", ROOT / "reports-hyperos"))
ARCHIVE = Path(os.environ["HYPEROS_ARCHIVE"])
TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "hyperos-geometry"
TOOLS = ROOT / ".tools" / "android-tools-static"

def digest(path, algo="sha256"):
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for data in iter(lambda: f.read(8*1024*1024), b""):
            h.update(data)
    return h.hexdigest()

def run(*args):
    cmd = [str(x) for x in args]
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, text=True, capture_output=True)

def write(name, content):
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / name).write_text(content, encoding="utf-8")

def check_archive():
    if ARCHIVE.name != NAME:
        raise RuntimeError("Wrong Global archive filename: " + ARCHIVE.name)
    if not ARCHIVE.is_file():
        raise RuntimeError("No downloaded Xiaomi fastboot archive found")
    size = ARCHIVE.stat().st_size
    md5 = digest(ARCHIVE, "md5")
    sha = digest(ARCHIVE, "sha256")
    write("stock-checksums.txt", f"Device: {DEVICE}\nRegion: {REGION}\nVersion: {VERSION}\nArchive: {NAME}\n"
          f"Bytes: {size}\nExpected MD5: {MD5}\nActual MD5: {md5}\nSHA256: {sha}\n")
    if md5 != MD5:
        raise RuntimeError("Global HyperOS archive checksum mismatch")
    print("Stock Xiaomi fastboot archive verified (MD5); SHA256 computed", flush=True)
    return {"bytes": size, "md5": md5, "sha256": sha}

def extract_super():
    TEMP.mkdir(parents=True, exist_ok=True)
    sparse = TEMP / "super.sparse.img"
    members = []
    checksums = {}
    found = False
    clues = []
    with tarfile.open(ARCHIVE, "r|gz") as stream:
        for entry in stream:
            p = PurePosixPath(entry.name)
            if p.is_absolute() or ".." in p.parts or entry.issym() or entry.islnk() or entry.isdev():
                raise RuntimeError("Unsafe firmware archive entry " + entry.name)
            members.append((entry.name, "file" if entry.isfile() else "other", entry.size))
            if not entry.isfile():
                continue
            if p.parent.name == "images" and p.name == "super.img":
                if found:
                    raise RuntimeError("Multiple super.img entries")
                with stream.extractfile(entry) as source, sparse.open("wb") as output:
                    shutil.copyfileobj(source, output, 8*1024*1024)
                found = True
            elif p.parent.name == "images" and p.name in ("vbmeta.img","vbmeta_system.img","vbmeta_vendor.img"):
                with stream.extractfile(entry) as source:
                    h = hashlib.sha256()
                    while data := source.read(8*1024*1024):
                        h.update(data)
                    checksums[p.name] = h.hexdigest()
            elif entry.size <= 1_000_000 and (p.name.startswith("flash_") or p.name in
                     ("crclist.txt","sparsecrclist.txt","misc.txt","anti_version.txt")):
                with stream.extractfile(entry) as source:
                    clues.append("### "+entry.name+"\n"+source.read().decode("utf-8","replace")[:120_000])
    with (REPORT/"archive-members.tsv").open("w",newline="",encoding="utf8") as f:
        writer=csv.writer(f,delimiter="\t");writer.writerow(("path","type","bytes"));writer.writerows(members)
    write("source-flash-metadata.txt","\n\n".join(clues)+"\n")
    write("source-avb-sha256.json",json.dumps(checksums,indent=2)+"\n")
    if not found:
        raise RuntimeError("No images/super.img found in original fastboot archive")
    return sparse

def get_raw_super(sparse):
    with sparse.open("rb") as f:
        header=f.read(28)
    if len(header)!=28:
        raise RuntimeError("Truncated super.img header")
    magic,major,minor,header_size,chunk_header,block_size,total_blocks,total_chunks,checksum=struct.unpack("<I4H4I",header)
    if magic != 0xED26FF3A:
        raise RuntimeError("Unexpected non-sparse super.img; manual review required")
    if (major,header_size,chunk_header)!=(1,28,12) or block_size < 512 or block_size % 512:
        raise RuntimeError("Unsupported Android sparse header")
    raw_size = block_size*total_blocks
    free=shutil.disk_usage(TEMP).free
    write("super-sparse-header.json",json.dumps({
        "magic":"0xed26ff3a","major":major,"minor":minor,"block_size":block_size,
        "total_blocks":total_blocks,"total_chunks":total_chunks,"raw_bytes":raw_size,
        "sparse_bytes":sparse.stat().st_size,"disk_free_before_conversion_bytes":free
    },indent=2)+"\n")
    print(f"Super sparse {sparse.stat().st_size:,} bytes => raw {raw_size:,} bytes. Free {free:,} bytes",flush=True)
    # Stage 2 can discard the fully verified archive; only keep a small checksum report.
    ARCHIVE.unlink()
    free=shutil.disk_usage(TEMP).free
    if free < raw_size + 450_000_000:
        raise RuntimeError(f"Insufficient disk space for read-only sparse conversion: {free:,} available, {raw_size:,} needed")
    raw=TEMP/"super.raw.img"
    p=run(TOOLS/"simg2img",sparse,raw)
    if p.returncode:
        raise RuntimeError("simg2img failed: "+p.stderr[-1600:])
    if raw.stat().st_size != raw_size:
        raise RuntimeError("Converted super has wrong size")
    sparse.unlink()
    write("super-source.txt", f"Raw bytes: {raw_size}\nRaw SHA256: {digest(raw)}\n")
    return raw

def parse_partitions(layout,slot):
    if "Partition table:" not in layout or "Block device table:" not in layout:
        raise RuntimeError("Unrecognized lpdump partition layout")
    section=layout.split("Partition table:",1)[1].split("Block device table:",1)[0]
    result=[]
    for block in section.split("------------------------"):
        m=re.search(r"(?m)^\s*Name:\s*([a-zA-Z0-9_.-]+)\s*$",block)
        if not m:
            continue
        name=m.group(1)
        group=re.search(r"(?m)^\s*Group:\s*([a-zA-Z0-9_.-]+)\s*$",block)
        attributes=re.search(r"(?m)^\s*Attributes:\s*(.*?)\s*$",block)
        # LP linear and zero extents use 512-byte sectors.
        spans=[(int(a),int(b),kind) for a,b,kind in re.findall(
            r"(?m)^\s*(\d+)\s*\.\.\s*(\d+)\s+(linear|zero)\b",block)]
        if not spans:
            continue # metadata for unused A/B slot
        capacity=sum((last-first+1)*512 for first,last,_ in spans)
        result.append({"metadata_slot":slot,"partition":name,
                       "group":group.group(1) if group else "unknown",
                       "attributes":attributes.group(1) if attributes else "",
                       "extent_count":len(spans),"capacity_bytes":capacity})
    return result

def identify_filesystem(path):
    with path.open("rb") as f:
        header=f.read(4096)
    if header[1024:1028] == bytes.fromhex("e2e1f5e0"):
        return "erofs"
    if header[1080:1082] == bytes.fromhex("53ef"):
        return "ext4"
    return "unknown"

def audit_partitions(raw):
    all_parts=[]
    for slot in (0,1):
        p=run(TOOLS/"lpdump","-s",slot,raw)
        write(f"lpdump-slot{slot}.txt",p.stdout+"\nSTDERR:\n"+p.stderr+
              f"\nEXIT STATUS: {p.returncode}\n")
        if p.returncode:
            if slot==0:
                raise RuntimeError("Cannot read slot 0 LP metadata: "+p.stderr[-1000:])
            print("Slot 1 metadata unavailable; preserved output for review",flush=True)
            continue
        all_parts.extend(parse_partitions(p.stdout,slot))
    if not all_parts:
        raise RuntimeError("No populated dynamic partitions found")
    rows=[]
    seen=set()
    filesystem_errors=[]
    for item in all_parts:
        name=item["partition"]
        if name in seen:
            continue
        seen.add(name)
        out=TEMP/"one-partition"
        out.mkdir(exist_ok=True)
        try:
            p=run(TOOLS/"lpunpack",f"--slot={item['metadata_slot']}",
                  f"--partition={name}",raw,out)
            if p.returncode:
                raise RuntimeError("lpunpack failed: "+p.stderr[-1200:])
            image=out/(name+".img")
            if not image.exists():
                raise RuntimeError("Missing unpacked image")
            image_size=image.stat().st_size
            filesystem=identify_filesystem(image)
            item["filesystem"]=filesystem
            item["image_bytes"]=image_size
            if filesystem=="unknown":
                filesystem_errors.append(f"Unsupported filesystem for {name}")
            if image_size > item["capacity_bytes"]:
                filesystem_errors.append(f"{name}: image larger than LP partition extent")
            rows.append(item)
            print(f"{name}: {filesystem}; allocated {item['capacity_bytes']:,} bytes; image {image_size:,}",flush=True)
        except Exception as exc:
            item["filesystem"]="error"
            item["image_bytes"]=0
            rows.append(item)
            filesystem_errors.append(f"{name}: {exc}")
        finally:
            shutil.rmtree(out,ignore_errors=True)
    if not rows:
        raise RuntimeError("No unpacked partitions to inspect")
    headers=("metadata_slot","partition","group","attributes","extent_count",
             "capacity_bytes","filesystem","image_bytes")
    with (REPORT/"partition-geometry.tsv").open("w",newline="",encoding="utf8") as f:
        writer=csv.writer(f,delimiter="\t");writer.writerow(headers)
        writer.writerows([r.get(k,"") for k in headers] for r in rows)
    with (REPORT/"partition-geometry.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.writer(f);writer.writerow(headers)
        writer.writerows([r.get(k,"") for k in headers] for r in rows)
    write("partition-geometry.json",json.dumps(rows,indent=2)+"\n")
    write("partition-warnings.txt","\n".join(filesystem_errors)+"\n" if filesystem_errors else "No partition read errors.\n")
    if filesystem_errors:
        raise RuntimeError("Super metadata inspection incomplete; see partition-warnings.txt")
    return rows

def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    try:
        checksums=check_archive()
        sparse=extract_super()
        raw=get_raw_super(sparse)
        rows=audit_partitions(raw)
        summary=(f"# HyperOS Build 1 read-only source audit\n\n"
                 f"- Device: {DEVICE}; region: {REGION}; version: {VERSION}\n"
                 f"- Stock MD5 verified: {checksums['md5']}\n"
                 f"- Stock SHA256: {checksums['sha256']}\n"
                 f"- Raw super: {raw.stat().st_size:,} bytes\n"
                 f"- Populated logical partitions inspected: {len(rows)}\n"
                 f"- Partition details in partition-geometry.tsv/json and lpdump-slot*.txt\n"
                 f"- Actions: no modifications, no patched vbmeta, no firmware published.\n")
        write("summary.md",summary)
        write("status.txt",f"PASS: checksum verified, super geometry inspected in {time.monotonic()-started:.1f}s\n")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf8") as output:
                output.write(summary)
        print(summary,flush=True)
    except Exception as e:
        write("status.txt",f"FAIL: {e}\n")
        raise
    finally:
        shutil.rmtree(TEMP,ignore_errors=True)

if __name__=="__main__":
    main()
