# HyperOS 1 Yunluo Build 6 — Final Project Release v1.2.0

**Device:** Xiaomi Redmi Pad Wi-Fi (`yunluo`)  
**Base:** Original Xiaomi Global HyperOS 1, OS1.0.9.0.ULYMIXM, Android 14.  
**Type:** Unofficial custom project firmware, not an official Xiaomi firmware release.  
**Project status:** Final planned release. Offline validations required; real-device flash/boot not claimed until user tests it.

## Final changes from Build 5

All **48** original Build 5 package selections remain removed. Add **five** originally stock APKs, removing each dedicated *entire app directory*, including its APK, app-owned JNI/lib subdirectories, oat/odex/vdex and other owned contents. Total selected from `super.img`: **53 APKs, 51 complete app folders and two individual shared overlays**.

| App | Android package | Source logical partition | Entire stock folder removed |
|---|---|---|---|
| Weather | `com.miui.weather2` | `product_a` | `/data-app/MIUIWeatherGlobal` |
| Mi Home (Xiaomi smart home, **not the launcher**) | `com.xiaomi.smarthome` | `mi_ext_a` | `/product/data-app/SmartHome` |
| Mi Canvas | `com.miui.creation` | `product_a` | `/data-app/Creation` |
| Recorder (sound) | `com.android.soundrecorder` | `product_a` | `/data-app/MIUISoundRecorderTargetSdk30Global` |
| Scanner | `com.xiaomi.scanner` | `product_a` | `/data-app/MiuiScanner` |

**These names, package IDs, and paths are verified from the original HyperOS Stage 3 APK inventory (329 nonempty stock APKs).** No other removal should be inferred from similar-sounding apps.

**Explicit keeps:** `com.miui.home` Xiaomi system launcher, Xiaomi Gallery, Security, Cleaner, `com.miui.screenrecorder` Screen Recorder, `com.mediatek.callrecorder` Call Recorder, Contacts, Gmail, Calendar, Android System Intelligence, Private Compute Services, APEX packages, Wi-Fi/NetworkStack, telephony/system providers and all untouched vendor/vender_dlkm/odm_dlkm modules.

## Netflix: separate user-data app cleanup

The user's ADB output showed:
`package:/data/app/~~.../com.netflix.mediaclient-.../base.apk`

The original Xiaomi stock `super.img` APK inventory contains **no** `com.netflix.mediaclient`. **Therefore Netflix cannot be removed from the stock `super.img`**; it is a user-installed `/data/app` package. The original Xiaomi `flash_all.bat` may wipe user data, but Google/Xiaomi restore or later installs could bring Netflix back.

For complete requested cleanup **after the tablet boots**, download and run `REMOVE_NETFLIX_USER_APP.ps1` from the release with authorized ADB. The script checks that exactly one tablet is connected, runs `adb uninstall com.netflix.mediaclient`, and verifies `adb shell pm path` returns no installed APK. Android's normal package manager removes the app installation and its APK directory/data; **we never delete arbitrary `/data/app` folders manually.** If Netflix is not installed, the script reports already absent.

## Verified builder and prior flash issue

Build 5 was physically flashed and booted successfully, per user's device test. Build 6 reuses Build 5's successful EROFS partition reconstruction and Xiaomi sparse CRC generation pipeline, including its *exact completed ZIP* SHA256 and CRC re-check. The Build 4 local super CRC mismatch is not reproduced by this packaging pipeline; **Build 6 physical flash remains unverified until testing**.

Build 6 must:
- Start from checksum-pinned original stock firmware and preserve original LP metadata slots and all unaffected partition bytes.
- Assert 53 exact selected APK IDs and 51 entire recursively removed folders plus 2 shared-overlay APK removals.
- Assert each five *newly* selected package is found at the verified source path and is removed as a whole dedicated folder.
- Check retained APKs' hashes, UID/GID, mode, and SELinux attributes unchanged.
- Keep Xiaomi's original `flash_all.bat` byte-identical; do not change Windows flashing logic.
- Patch main `vbmeta.img` AVB flags 3 and update both CRC lists; confirm original Xiaomi stock `sparsecrclist` calculation before regenerating.
- Verify EROFS rebuild, raw↔sparse super roundtrip, and *in-ZIP* sparse CRC segments and SHA256.
- Verify complete ZIP and all split GitHub release asset SHA256 checksums.
- Publish `FASTBOOT_IMAGE_SHA256.txt` and `VERIFY_BUILD6_FASTBOOT.ps1` for Windows pre-flash checks; any mismatch means do not flash.

## Full Build 6 Android system debloat package list (53)

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
49. `com.miui.weather2`
50. `com.xiaomi.smarthome`
51. `com.miui.creation`
52. `com.android.soundrecorder`
53. `com.xiaomi.scanner`

## Download & flash cautions

Download every `.zip.partNNN` asset, `ZIP_SHA256.txt`, `WINDOWS_JOIN_FULL_FIRMWARE.ps1`, `FASTBOOT_IMAGE_SHA256.txt`, `VERIFY_BUILD6_FASTBOOT.ps1`, and optional Netflix cleanup helper. Reassemble and SHA256-verify the ZIP; extract into a new folder; then verify all images with the Windows preflight script **before attempting to flash**.

The original Xiaomi `flash_all.bat` may erase data. Never relock the bootloader with modified firmware. Maintain access to the already boot-tested Build 5 fallback. Build 6's GitHub checks do not constitute proof of a successful on-device flash or boot.

**Project closure:** v1.2.0 is the requested final planned firmware release; no additional builds are scheduled.
