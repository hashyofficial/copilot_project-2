# HyperOS1 Yunluo — Build 5 Official Custom ROM v1.1.0

**Device:** Xiaomi Redmi Pad Wi-Fi, codename `yunluo`  
**Base:** Original checksum-pinned Xiaomi HyperOS 1 Global OS1.0.9.0.ULYMIXM (Android 14)  
**Release type:** Official **project** release, not Xiaomi-signed official firmware  
**Status:** Offline-validated test firmware; on-device flash and boot still require validation.

## Why Build 5?

Build 4 failed during the first sparse super.img write on the user's physical device:

```text
Sending sparse 'super' 1/19 ... OKAY
Writing 'super' ... FAILED (remote: 'failed to check sparse crc')
```

The user's local super.img SHA256 was:
`aa6b2bc95ddb068232e0b772069468b0827b25c71b651ec1d63bff78df5138c1`

The independently published Build 4 image report declared:
`3514b80e43ab410098ea96fa35acff6a24d98d0bf83944bf400c4b14d06c0a98`

**These differ**, so the failed device flash used different super.img bytes from the verified release. The original stock-firmware sparse CRC count was 22 and Build 4's rebuilt count was 19, but differing counts alone do not establish an invalid sparse format. The user's supplied sparsecrclist listed 19 entries, matching the 19 Fastboot transfers. The precise cause of the local image mismatch is **unconfirmed**: possible stale/wrong local image, damaged extraction, or local modification.

## Comparison against previous builds

- **Build 2:** The user physically booted it. It used `img2simg` for rebuilt super and the Xiaomi-compatible `hyperos_crc.sparse_crc` checksum calculation.
- **Build 3:** Reused the same sparse-image and CRC-generation pipeline; the later v0.2 had an Android boot issue due to further system modifications. No confirmed evidence that changing the CRC algorithm would fix this case.
- **Build 4:** Same core packing approach; failed device sparse CRC check, and the local super SHA was different from its published verification manifest.
- **Build 5:** Restarts from the **original Xiaomi stock**, retains Build2/3's tested sparse/CRC format, but performs stricter *post-package* image, CRC and Windows-extraction checks. It does not bypass the device's checksum verification.

## Debloat scope unchanged from Build 4

Exactly 48 user-approved stock Android package IDs; 46 complete app folders with contained APKs, app-owned native libraries and compiled files, plus 2 APKs inside shared overlay directories. No additional packages removed.

1. `com.google.android.googlequicksearchbox`
2. `com.google.android.apps.googleassistant`
3. `com.android.hotwordenrollment.okgoogle`
4. `com.android.hotwordenrollment.xgoogle`
5. `com.google.android.tts`
6. `com.google.android.marvin.talkback`
7. `com.google.android.accessibility.switchaccess`
8. `com.google.android.overlay.gmsconfig.gsa`
9. `com.google.android.youtube`
10. `com.google.android.apps.youtube.music`
11. `com.google.android.apps.photos`
12. `com.google.android.apps.docs`
13. `com.google.android.apps.maps`
14. `com.google.android.apps.tachyon`
15. `com.google.android.videos`
16. `com.google.android.apps.podcasts`
17. `com.google.android.apps.magazines`
18. `com.google.android.apps.subscriptions.red`
19. `com.google.android.apps.wellbeing`
20. `com.google.android.apps.safetyhub`
21. `com.google.android.gms.location.history`
22. `com.google.android.feedback`
23. `com.google.android.printservice.recommendation`
24. `com.google.android.apps.restore`
25. `com.google.mainline.adservices`
26. `com.google.android.onetimeinitializer`
27. `com.google.android.overlay.gmsconfig.personalsafety`
28. `com.mediatek.engineermode`
29. `com.mediatek.lbs.em2.ui`
30. `com.debug.loggerui`
31. `com.mediatek.mdmconfig`
32. `com.mediatek.mdmlsample`
33. `com.xiaomi.mtb`
34. `com.mediatek.ygps`
35. `com.mediatek.atci.service`
36. `com.modemdebug`
37. `com.mediatek.voicecommand`
38. `com.mediatek.voiceunlock`
39. `com.android.bluetoothmidiservice`
40. `com.android.bookmarkprovider`
41. `android.autoinstalls.config.Xiaomi.model`
42. `com.bsp.catchlog`
43. `com.miui.cit`
44. `com.android.dreams.basic`
45. `com.miui.miservice`
46. `com.xiaomi.payment`
47. `cn.wps.xiaomi.abroad.lite`
48. `com.android.apps.tag`

**Explicitly kept:** Gmail, Calendar, Contacts, Calendar Sync, Android System Intelligence, Private Compute Services, Intelligence overlay, original Xiaomi Gallery and Security, Network Stack/Wi-Fi, CellBroadcast, ContactsProvider, all APEX modules, vendor/vendor_dlkm and odm_dlkm partitions.

## Stronger Build 5 verification

1. Original Xiaomi firmware MD5 and SHA256 pinned.
2. Preserve original LP metadata in both slots and every unmodified raw super extent.
3. Rebuild only `system_a`, `system_ext_a`, `product_a`, `mi_ext_a` with EROFS; verify retained APK hashes, UID/GID, modes, and SELinux labels.
4. Validate 46 entire deleted folders and their app-owned contents, plus 2 individually removed shared-overlay APKs.
5. Verify raw-to-sparse-to-raw bitwise equivalence for the entire ~9.1GB logical super.
6. Reproduce original stock sparse CRC list exactly before generating any new sparse CRCs.
7. Re-open **the exact super.img stored inside the final ZIP** and recompute its SHA256 and Xiaomi-format sparse CRC sequence; verify against the `sparsecrclist.txt` in that same ZIP.
8. Patch only original main `vbmeta.img` (AVB flags 3); update `crclist.txt` and `sparsecrclist.txt`; verify stock `flash_all.bat` and other scripts **unchanged**.
9. Verify complete ZIP and every split Release part's SHA256, and all uploaded GitHub asset sizes/digests.
10. Include `FASTBOOT_IMAGE_SHA256.txt` and **`VERIFY_BUILD5_FASTBOOT.ps1`** in the Release: after extracting, Windows users can independently verify `images/super.img`, `vbmeta.img`, `crclist.txt`, `sparsecrclist.txt`, and `flash_all.bat` before flashing.

## Distribution

GitHub's 2-GiB per-asset limit requires the **complete** fastboot ZIP to be divided into 3 or more numbered .partNNN assets, with `WINDOWS_JOIN_FULL_FIRMWARE.ps1` and `ZIP_SHA256.txt`. Download all segments and checksums, join, extract, then run the additional Build 5 file verifier. No firmware files are omitted.

**Build 4 v1.0.0 will be deleted along with its tag only after the Build 5 draft has all assets uploaded and cryptographically verified, before publishing Build 5.** The separate stock DLKM source-image download must remain untouched.

**Warning:** Never relock the bootloader or bypass sparse CRC checks. The original Xiaomi `flash_all.bat` may wipe user data. The new image still requires real tablet flashing and boot tests; this release does not claim successful physical boot.
