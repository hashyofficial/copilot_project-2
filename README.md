# Redmi Pad (yunluo) — HyperOS 1 Global, Build 1

Experimental firmware workflow for **Xiaomi Redmi Pad (yunluo, Wi-Fi-only)**.

## Status
**Testing / inventory only.** No modified firmware, patched vbmeta, or GitHub Release exists yet. Device boot is untested.

## Stock source (Global MIXM)
- HyperOS 1 / Android 14: **OS1.0.9.0.ULYMIXM**
- Fastboot: `yunluo_global_images_OS1.0.9.0.ULYMIXM_20250416.0000.00_14.0_global_f8dbb84a10.tgz`
- Published MD5: `f8dbb84a10dc96a9d3ce9e78883e87f3`
- Official Xiaomi OTA servers, source listed at https://mirom.ezbox.idv.tw/en/phone/yunluo/
- Never mix Global (MIXM) with EEA (EUXM), India (INXM), or another regional image.

## Workflow stages
1. `download` (first run): check OTA mirrors; download complete stock fastboot archive; validate published MD5, compute SHA-256; upload **small reports only** as GitHub Actions artifacts.
2. `inventory` (later, after successful download): repeat checksum-verified download on a fresh runner; unpack super.img; inspect dynamic partitions and read-only APK paths and package IDs; upload TXT/TSV/CSV reports. No removals.
3. `debloat` and `package` are **not enabled**. They require a reviewed HyperOS-specific app removal list and safe rebuild logic adapted from MIUI Build 10.
4. `release` is intentionally absent until requested after physical device testing.

### Source reference
Read-only reference: https://github.com/hashyofficial/copilot_workflow/tree/build10/fresh-stock-final

MIUI 14 Build 10 Final remains unchanged. No unverified MIUI partition offsets or app-removal lists carry over.

### Rules
Preserve stock filesystem types in initial experiments. Determine HyperOS-specific super size, partition metadata and logical extents from the stock images. No blanket removals or automatic publishing. Keep the original official fastboot firmware for recovery. Never relock a bootloader with modified firmware.
