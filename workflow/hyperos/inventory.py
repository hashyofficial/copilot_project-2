#!/usr/bin/env python3
"""Read-only Xiaomi fastboot archive and dynamic-partition APK inventory."""
import csv, hashlib, json, os, pathlib, re, shutil, stat, subprocess, tarfile, urllib.request

from firmware import VERSION as VER, NAME, MD5, URL

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(os.environ.get("HYPEROS_REPORTS", str(ROOT / "reports-hyperos")))
TMP = pathlib.Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "yunluo-hyperos-inventory"
TOOLS = ROOT / ".tools/android-tools-static"

def write(name,text):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(text,encoding="utf8")

def sha(path,algorithm="sha256"):
    h=hashlib.new(algorithm)
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(8*1024*1024),b""):h.update(b)
    return h.hexdigest()

def command(*args):
    return subprocess.run([str(x) for x in args],capture_output=True,text=True,check=False)

def install():
    TOOLS.parent.mkdir(parents=True,exist_ok=True)
    api="https://api.github.com/repos/meator/android-tools-static/releases/tags/36.0.1"
    req=urllib.request.Request(api,headers={"User-Agent":"yunluo-inventory","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req,timeout=60) as r:release=json.load(r)
    assets=[x for x in release["assets"] if x["name"] == "android-tools-static-linux-standardlayout-extra-x86_64.tar.gz"]
    if len(assets)!=1:raise RuntimeError("No unique pinned Linux tools asset: "+str([x["name"] for x in release["assets"]]))
    asset=assets[0];digest=asset.get("digest") or ""
    if not digest.startswith("sha256:"):raise RuntimeError("Release asset lacks verifiable SHA256")
    tarpath=TOOLS.parent/asset["name"]
    urllib.request.urlretrieve(asset["browser_download_url"],tarpath)
    got=sha(tarpath)
    if got!=digest.split(":",1)[1]:raise RuntimeError("Tools SHA256 mismatch")
    with tarfile.open(tarpath) as tf:
        for m in tf:
            p=pathlib.PurePosixPath(m.name)
            if m.issym() or m.islnk() or p.is_absolute() or ".." in p.parts:raise RuntimeError("Unsafe tools archive")
        tf.extractall(TOOLS.parent,filter="data")
    tarpath.unlink()
    for tool in ("simg2img","lpunpack","lpdump","lpmake","img2simg"):
        if not (TOOLS/tool).is_file():raise RuntimeError("Missing "+tool)
    write("tools.txt",f"{api}\n{asset['name']}\nSHA256: {got}\n")

def archive_inspect(archive):
    entries=["path\ttype\tbytes"];clues=[];superfile=None
    with tarfile.open(archive,"r:gz") as tf:
        for m in tf:
            p=pathlib.PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts or m.issym() or m.islnk() or m.isdev():raise RuntimeError("Unsafe vendor archive path "+m.name)
            entries.append(f"{m.name}\t{'file' if m.isfile() else 'other'}\t{m.size}")
            if not m.isfile():continue
            base=p.name.lower()
            if base=="super.img":
                if superfile is not None:raise RuntimeError("Multiple super.img files")
                superfile=TMP/"super.img"
                with tf.extractfile(m) as inp,open(superfile,"wb") as dest:shutil.copyfileobj(inp,dest,8*1024*1024)
            elif m.size<2_000_000 and base.endswith((".sh",".bat",".xml",".txt",".cfg",".ini",".json",".cmd")):
                clues.append(f"===== {m.name} =====\n"+tf.extractfile(m).read().decode("utf8","replace")[:120000])
    write("archive-members.tsv","\n".join(entries)+"\n")
    write("flashing-clues.txt","\n".join(clues)+"\n")
    if not superfile:raise RuntimeError("No super.img in archive")
    return superfile

def fstype(p):
    with open(p,"rb") as f:header=f.read(1100)
    if header[1024:1028]==bytes.fromhex("e2e1f5e0"):return "erofs"
    if header[1080:1082]==bytes.fromhex("53ef"):return "ext4"
    r=command("blkid","-p","-o","value","-s","TYPE",p)
    return r.stdout.strip() or "unknown"

def find_aapt():
    sdk = pathlib.Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "/usr/local/lib/android/sdk")
    candidates = sorted((sdk / "build-tools").glob("*/aapt2"), reverse=True)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    for name in ("aapt2", "aapt"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("Android aapt2/aapt is missing. Cannot map APKs to package IDs.")


def scan_mount(mount, part, paths, details, package_errors, aapt):
    for directory, _, files in os.walk(mount, followlinks=False):
        for name in files:
            if not name.lower().endswith(".apk"):
                continue
            p = pathlib.Path(directory) / name
            st = p.lstat()
            if not stat.S_ISREG(st.st_mode):
                continue
            rel = "/" + str(p.relative_to(mount))
            try:
                ctx = os.getxattr(p, "security.selinux", follow_symlinks=False).decode("utf8", "replace").strip("\\0")
            except OSError:
                ctx = "xattr-unavailable-or-policy-derived"
            package_id = ""
            try:
                result = subprocess.run([aapt, "dump", "badging", str(p)],
                                        capture_output=True, text=True, timeout=90)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip()[-300:] or "aapt returned nonzero")
                match = re.search(r"(?m)^package:\\s+name='([^']+)'", result.stdout)
                if not match:
                    raise RuntimeError("No package identity in badging")
                package_id = match.group(1)
            except Exception as exc:
                package_errors.append(f"{part}:{rel} => {exc}")
            paths.add(f"{part}:{rel}")
            details.append((part, rel, package_id, st.st_uid, st.st_gid,
                            oct(stat.S_IMODE(st.st_mode)), st.st_size, ctx))


def inspect():
    OUT.mkdir(parents=True,exist_ok=True);TMP.mkdir(parents=True,exist_ok=True)
    archive=pathlib.Path(os.environ["HYPEROS_ARCHIVE"])
    apks=set();rows=[];package_errors=[];aapt=find_aapt()
    fss=["partition\tfilesystem\timage_bytes\tmetadata_slot"];errors=[]
    try:
        if not archive.is_file():
            raise RuntimeError("Missing previously downloaded checksum-verifiable firmware: " + str(archive))
        md5=sha(archive,"md5")
        write("checksums.txt",f"URL: {URL}\nExpected MD5: {MD5}\nActual MD5: {md5}\n")
        if md5!=MD5:raise RuntimeError("Firmware MD5 mismatch")
        superfile=archive_inspect(archive)
        archive.unlink()
        with open(superfile,"rb") as f:sparse=f.read(4)==bytes.fromhex("3aff26ed")
        if sparse:
            raw=TMP/"super.raw.img"
            r=command(TOOLS/"simg2img",superfile,raw)
            if r.returncode:raise RuntimeError("simg2img failed: "+r.stderr)
            superfile.unlink();superfile=raw
        write("super-source.txt",f"Sparse source: {sparse}\nRaw size bytes: {superfile.stat().st_size}\nSHA256: {sha(superfile)}\n")
        parts=[]
        seen_layouts=set()
        for slot in (0,1):
            r=command(TOOLS/"lpdump","-s",slot,superfile)
            write(f"lpdump-slot{slot}.txt",r.stdout+"\nSTDERR:\n"+r.stderr+f"\nExit: {r.returncode}\n")
            if r.returncode!=0:
                errors.append(f"lpdump slot {slot} failed: {r.stderr.strip()}")
                continue
            layout=r.stdout.split("Metadata version:",1)[-1]
            if layout in seen_layouts:
                continue  # both metadata slots map exactly the same layout
            seen_layouts.add(layout)
            table=r.stdout.split("Partition table:",1)[-1].split("Block device table:",1)[0]
            for block in table.split("------------------------"):
                name=re.search(r"(?m)^\s*Name:\s*([A-Za-z0-9_.-]+)\s*$",block)
                if not name:
                    continue
                # Empty A/B placeholders have no mapped extents to inventory.
                if not re.search(r"(?m)^\s*\d+\s*\.\.\s*\d+\s+(linear|zero)\b",block):
                    continue
                parts.append((slot,name.group(1)))
        if not parts:raise RuntimeError("lpdump did not report populated logical partitions")
        for slot,part in parts:
            out=TMP/"unpacked";out.mkdir(exist_ok=True)
            try:
                r=command(TOOLS/"lpunpack",f"--slot={slot}",f"--partition={part}",superfile,out)
                if r.returncode:raise RuntimeError("lpunpack: "+r.stderr)
                image=out/(part+".img")
                if not image.is_file():raise RuntimeError("lpunpack did not create "+str(image))
                fs=fstype(image);fss.append(f"{part}\t{fs}\t{image.stat().st_size}\t{slot}")
                if fs not in ("ext4","erofs"):raise RuntimeError("Unsupported filesystem: "+fs)
                mnt=TMP/"mount";mnt.mkdir(exist_ok=True)
                opts="ro,loop,noload" if fs=="ext4" else "ro,loop"
                r=command("mount","-t",fs,"-o",opts,image,mnt)
                if r.returncode:raise RuntimeError("Read-only mount failed: "+r.stderr)
                try:scan_mount(mnt,part,apks,rows,package_errors,aapt)
                finally:subprocess.run(["umount",str(mnt)],check=True)
            except Exception as ex:
                errors.append(f"slot{slot} {part}: {ex}")
            finally:shutil.rmtree(out,ignore_errors=True)
        write("apks.txt","\n".join(sorted(apks))+"\n")
        headers=("partition","path","android_package_id","uid","gid","mode","bytes","selinux_xattr")
        write("apks-detailed.tsv", "\\t".join(headers)+"\\n"+"\\n".join("\\t".join(map(str,row)) for row in rows)+"\\n")
        with (OUT/"apks-detailed.csv").open("w", newline="", encoding="utf-8") as dest:
            writer=csv.writer(dest);writer.writerow(headers);writer.writerows(rows)
        write("apk-package-errors.txt", "\\n".join(package_errors)+"\\n" if package_errors else "All APK identities parsed.\\n")
        write("apk-summary.json", json.dumps({"device":"yunluo","region":"Global MIXM",
              "firmware_version":VER,"total_apks":len(rows),
              "partitions":sorted({row[0] for row in rows}),
              "package_id_parse_failures":len(package_errors)},indent=2)+"\\n")
        write("filesystems.tsv","\n".join(fss)+"\n")
        write("warnings.txt","\n".join(errors)+"\n" if errors else "No partition inventory warnings.\n")
        if errors:raise RuntimeError("Incomplete inventory: see warnings.txt")
        write("status.txt", "Inventory completed; review package ID errors separately.\n")
    finally:
        if archive.exists():archive.unlink()
        if not (OUT/"status.txt").exists():
            write("status.txt","Inventory attempted but did not complete; check warnings and Actions logs.\n")

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--install-tools",action="store_true");g.add_argument("--inspect",action="store_true")
    a=p.parse_args()
    install() if a.install_tools else inspect()
