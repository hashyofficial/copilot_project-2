#!/usr/bin/env python3
"""Download checksum-pinned yunluo HyperOS 1 Global fastboot ROM from healthy CDNs.

Every candidate uses the identical Xiaomi OTA path; the inventory script
checks the full archive's published MD5 before opening it.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from firmware import VERSION, NAME

VERSION = VERSION
FILENAME = NAME
CDNS = [
    ("Azure CDN", "cdn-ota.azureedge.net"),
    ("Singapore Alibaba OSS", "bkt-sgp-miui-ota-update-alisgp.oss-ap-southeast-1.aliyuncs.com"),
    ("Xiaomi CDNORG", "cdnorg.d.miui.com"),
    ("Xiaomi BN", "bn.d.miui.com"),
    ("Xiaomi BIGOTA", "bigota.d.miui.com"),
]
PROBE_SIZE = 262144   # 256 KiB, only to confirm range support and approximate responsiveness
PROBE_TIMEOUT = 9
MIN_FULL_RATE = 3 * 1024 * 1024  # 3 MiB/s measured after parallel transfer starts

def url(host):
    return f"https://{host}/{VERSION}/{FILENAME}"

def probe(source):
    label, host = source
    with tempfile.TemporaryDirectory(prefix="yunluo-probe-") as tmp:
        out = Path(tmp)/"range"
        headers = Path(tmp)/"headers"
        start = time.monotonic()
        try:
            p = subprocess.run([
                "curl", "--location", "--silent", "--show-error", "--fail",
                "--connect-timeout", "8", "--max-time", str(PROBE_TIMEOUT),
                "--max-filesize", str(PROBE_SIZE * 2),
                "--range", f"0-{PROBE_SIZE - 1}",
                "--dump-header", str(headers), "--output", str(out),
                "--write-out", "%{http_code}",
                url(host)
            ], text=True, capture_output=True, timeout=PROBE_TIMEOUT+5)
            duration = max(time.monotonic()-start, .001)
            size = out.stat().st_size if out.exists() else 0
            status = p.stdout.strip()[-3:]
            header_text = headers.read_text(errors="replace") if headers.exists() else ""
            # A successful 206 with Content-Range is required. Reject 200
            # full files masquerading as range probes.
            valid = (p.returncode == 0 and status == "206" and
                     size == PROBE_SIZE and
                     "content-range:" in header_text.lower() and
                     "bytes 0-" in header_text.lower())
            rate = int(size/duration) if valid else 0
            return {"label": label, "host": host, "status": status,
                    "ok": valid, "rate_bytes_sec": rate,
                    "probe_seconds": round(duration,2),
                    "error": "" if valid else (p.stderr.strip()[-300:] or "Invalid HTTP range response")}
        except Exception as exc:
            return {"label":label,"host":host,"status":"error","ok":False,
                    "rate_bytes_sec":0,"probe_seconds":round(time.monotonic()-start,2),
                    "error":str(exc)[:300]}

def written_bytes(pid, output):
    """Track actual process writes, not sparse file size/high-offset range writes."""
    try:
        for line in Path(f"/proc/{pid}/io").read_text().splitlines():
            if line.startswith("write_bytes:"):
                return int(line.partition(":")[2].strip())
    except OSError:
        pass
    return output.stat().st_size if output.exists() else 0

def download_one(source, output):
    url_string = url(source["host"])
    output.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "aria2c", "--enable-color=false", "--file-allocation=none",
        "--allow-overwrite=true", "--auto-file-renaming=false",
        "--max-connection-per-server=8", "--split=8",
        "--min-split-size=1M", "--piece-length=4M",
        "--max-tries=2", "--retry-wait=4", "--connect-timeout=12",
        "--timeout=30", "--summary-interval=20",
        "--dir", str(output.parent), "--out", output.name,
        url_string,
    ]
    print(f"Downloading via {source['label']} ({source['host']})",flush=True)
    proc = subprocess.Popen(args)
    try:
        started = time.monotonic()
        last_bytes = 0
        last_progress = started
        rate_window_start = started
        rate_window_bytes = 0
        while proc.poll() is None:
            time.sleep(10)
            written = written_bytes(proc.pid, output)
            now = time.monotonic()
            if written > last_bytes:
                last_bytes = written
                last_progress = now
            if now - rate_window_start >= 30:
                sustained_rate = max(0, written - rate_window_bytes) / (now - rate_window_start)
                print(f"Parallel transfer measured at {sustained_rate / 1048576:.1f} MiB/s",flush=True)
                if sustained_rate < MIN_FULL_RATE:
                    print("Full-transfer speed below 3 MiB/s: switching CDN.",flush=True)
                    proc.terminate()
                    try:proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()
                    return False
                rate_window_start = now
                rate_window_bytes = written
            if now - last_progress > 90:
                print("No disk writes in 90s: switching CDN.",flush=True)
                proc.terminate()
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
                return False
            if now - started > 2700:
                print("Download exceeded 45-minute limit: switching CDN.",flush=True)
                proc.terminate()
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
                return False
        return proc.returncode == 0 and output.is_file()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--report",required=True,type=Path)
    args=ap.parse_args()
    args.report.parent.mkdir(parents=True,exist_ok=True)
    print("Testing 256-KiB HTTP range support against 5 CDNs...",flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(CDNS)) as ex:
        tests=list(ex.map(probe,CDNS))
    tests.sort(key=lambda t:t["rate_bytes_sec"],reverse=True)
    for t in tests:
        print(f"{t['label']}: {t['status']}, {t['rate_bytes_sec']/1048576:.2f} MiB/s, "
              f"{t['probe_seconds']}s; {t['error']}",flush=True)
    args.report.write_text(json.dumps({"probe_results":tests},indent=2)+"\n")
    healthy=[t for t in tests if t["ok"]]
    if not healthy:
        raise RuntimeError("No CDN supported a valid HTTP byte-range probe; "
                           "no multi-gigabyte download attempted. See download-sources.json.")
    # Historical full-ROM downloads on this runner succeeded at 53-323 MiB/s
    # on CDNORG even when tiny probes reported <0.2 MiB/s.
    healthy.sort(key=lambda t:(t["host"]=="cdnorg.d.miui.com",t["rate_bytes_sec"]),reverse=True)
    for candidate in healthy:
        # Never trust a partial archive from a different server.
        args.output.unlink(missing_ok=True)
        (args.output.parent/(args.output.name+".aria2")).unlink(missing_ok=True)
        try:
            if download_one(candidate,args.output):
                print(f"Firmware archive downloaded via {candidate['label']}",flush=True)
                args.report.write_text(json.dumps({"probe_results":tests,
                    "selected_host":candidate["host"],
                    "url":url(candidate["host"])},indent=2)+"\n")
                return
        except Exception as exc:
            print(f"Download failed from {candidate['host']}: {exc}",flush=True)
        print(f"Trying next CDN after {candidate['label']}",flush=True)
    raise RuntimeError("All healthy CDN downloads failed or stalled; see download-sources.json.")

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr,flush=True)
        sys.exit(1)
