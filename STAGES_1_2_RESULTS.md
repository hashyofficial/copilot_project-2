# HyperOS Build 1 — Verified Stage 1 & Stage 2 Results

**Result: PASS** — GitHub Actions run [40719541065](https://github.com/hashyofficial/copilot_project-2/actions/runs/40719541065), 28 October 2026.

## Stock fastboot source (unchanged)

- Device: Redmi Pad, `yunluo` (Wi-Fi only)
- Region: Global (`MIXM`) / Malaysia-compatible
- HyperOS 1: `OS1.0.9.0.ULYMIXM`, Android 14
- Fastboot archive: `yunluo_global_images_OS1.0.9.0.ULYMIXM_20250416.0000.00_14.0_global_f8dbb84a10.tgz`
- Downloaded archive: **4,771,445,636 bytes**
- Verified published MD5: `f8dbb84a10dc96a9d3ce9e78883e87f3`
- Independently calculated stock SHA256: `90562e6f369bb17cdaf67a86f2b72b16492fb1a63c86f7e389cf2ba306942530`
- Fastest successful server: **Xiaomi CDNORG** (`cdnorg.d.miui.com`), aria2 reported **238 MiB/s average**, sampled sustained rate **151.7 MiB/s**. Current mirror-selection approach performed very well; no optimization necessary.

## Stock super image geometry

- Original sparse `super.img`: **5,726,631,416 bytes**
- Converted raw `super.img`: **9,126,805,504 bytes**
- Populated logical partitions found: **7**
- Filesystem: **EROFS for all seven**
- Stage 2 read-only audit checked the logical image size against the allocated extent size for every populated partition. No partition read errors.

| Partition | Allocated capacity (bytes) | Filesystem |
|---|---:|---|
| odm_dlkm_a | 348,160 | EROFS |
| product_a | 2,592,829,440 | EROFS |
| system_a | 866,062,336 | EROFS |
| system_ext_a | 689,496,064 | EROFS |
| vendor_a | 1,041,645,568 | EROFS |
| vendor_dlkm_a | 11,292,672 | EROFS |
| mi_ext_a | 555,696,128 | EROFS |

Each extracted partition image occupied its reported allocated extent size. This **does not** mean zero filesystem free space or that a future rebuilt partition can grow arbitrarily. Determine the LP group free-space constraints and expected rebuilt image sizes before modifying `super.img`.

## Artifact

[Stage 1 + Stage 2 reports](https://github.com/hashyofficial/copilot_project-2/actions/runs/40719541065/artifacts/12830027396)

Artifact ID: `12830027396`. GitHub Actions artifacts expire; this report artifact was created on 28 October 2026 with a 30-day retention period.

Includes source download mirror report, original archive checksum, sparse header, full `lpdump` for LP metadata slots, partition geometry tables (TSV/CSV/JSON), source flash script clues, AVB image SHA256 and a read-only inspection summary.

## Safety and next steps

- No stock partition images were changed.
- No `vbmeta.img` was patched.
- No firmware ZIP was repacked, flashed, or published.
- No applications were removed.
- **Stage 3** (APK names, package IDs and paths) is not yet executed.
- Use fresh, verified HyperOS partition sizes; never reuse MIUI Build 10's fixed raw offsets or outdated lists.
- MIUI Build 10 source remains in the previous repository, read-only.
