# HyperOS1 Yunluo — Build 4 Official custom ROM Release v1.0.0

**Device:** Xiaomi Redmi Pad Wi-Fi (codename `yunluo`)  
**ROM:** HyperOS 1 Global, OS1.0.9.0.ULYMIXM, Android 14  
**Source:** Original checksum-pinned Xiaomi Global fastboot firmware, rebuilt from stock (NOT from failed Build 3 v0.2).  
**Project release:** Official release of this community/custom ROM project; **not an official Xiaomi ROM**.  
**Boot validation:** Awaiting user's on-device boot test; offline firmware checks alone cannot guarantee boot.

## Removal totals

- **48 unique stock package IDs**, **48 physical APK files**.
- **46 complete dedicated application folders**, with their contained APK, JNI/native libraries, oat/odex/vdex, app resources and companion files, rather than APK-only deletion.
- **2 individual overlay APKs** in shared overlay directories; the directories and other unrelated APKs are preserved.
- The build exports a detailed **recursive directory-content audit** for every deleted folder and verifies all selected folder and APK paths are absent from the rebuilt EROFS images.
- Shared libraries stored outside those dedicated app folders are **not blindly deleted**; removing a shared system library without verified ownership could break boot or unrelated apps.

## User-approved 48 removed Android package IDs

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

Duplicates in the user's requests are counted only once: Log Generator is CatchLog (`com.bsp.catchlog`) and Market Feedback Agent is Google Feedback (`com.google.android.feedback`).

Explicit additional removals include Basic Daydreams, Xiaomi Services & Feedback, Mi Coin, Mi Doc Viewer (WPS), and Tags. Android Auto (`com.google.android.projection.gearhead`) is absent from the original verified stock APK inventory and is not counted.

## Protected and restored versus Build 3

- **Gmail, Google Calendar, Google Contacts, Calendar Sync** all kept.
- **Android System Intelligence**, **Private Compute Services** and Android System Intelligence's configuration overlay all kept.
- **Xiaomi Gallery, Gallery Editor, Notes, Security, Cleaner, and the original Xiaomi apps** retained.
- **Network Stack, Wi-Fi, DNS, APEX modules including HealthFitness, CellBroadcast, AdServices**, core telecom/contact/calendar providers, and essential hardware drivers all retained.
- No Photon Gallery added; this is a **stock-app-preserving Google/MediaTek diagnostics debloat**, not Build 3's aggressive system modifications.
- Xiaomi original `flash_all.bat`, `flash_all.sh` and `flash_all_lock.bat` byte-for-byte unchanged. Stock image partition geometry retained; only `super.img`, main `vbmeta.img` and required CRC lists updated.

## Fastboot image verification

Pinned source archive MD5/SHA256, original partition mapping and filesystem integrity checked. Every selected complete app directory is recursively audited and proven absent from the rebuilt EROFS. Unselected APKs are checked for identical bytes, UID/GID, permissions, and SELinux context. Modified sparse super.img is round-trip verified. Updated AVB flags and Xiaomi checksum lists are validated. The full ZIP is fully reconstructed and CRC/SHA256 verified before release upload.

## Official GitHub custom project distribution

The entire Xiaomi fastboot ZIP is published in **GitHub Release assets, NOT temporary GitHub Actions artifacts**. GitHub's 2-GiB per-asset upload cap requires numbered release parts; all parts together reconstruct the FULL ZIP, with `WINDOWS_JOIN_FULL_FIRMWARE.ps1` and `ZIP_SHA256.txt` included. No partial firmware files or system partitions are omitted.

The previously published `v.0.1` and `v.0.2` Releases and their tags are deleted **only after the new draft Release has uploaded and verified all firmware assets**, then the new Release is published.

## Safety

Keep the bootloader unlocked; **never use `flash_all_lock.bat` or relock it** after modifying firmware. The unmodified Xiaomi `flash_all.bat` may erase userdata. Back up important data and keep a known-booting Build 2 firmware recovery package. This release may still fail to boot until physically tested. Bluetooth MIDI, voice assistance, TalkBack accessibility and related features will not function after removal of their APKs.
