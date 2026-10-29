# v.0.1 - HyperOS1 Yunluo

**Device:** Redmi Pad Wi-Fi (yunluo)  
**Firmware:** HyperOS 1 Global OS1.0.9.0.ULYMIXM, Android 14  
**Build:** Experimental Build 3  
**Base status:** Build 2 was successfully boot-tested on a physical device. Build 3 is a new experimental configuration, not yet device boot-tested.

## Changes from Build 2

- Continue debloating the 117 Build 2-selected packages, including the complete dedicated app directories.
- Remove Xiaomi MSA ads `com.miui.msa.global` (Google Mainline Ad Services was already removed in Build 2).
- Remove `com.android.providers.contacts` (Contacts Storage/ContactsProvider), `com.android.overlay.gmscontactprovider`, and `com.google.android.overlay.gmsconfig.contacts`.
- Remove carrier MCC/MNC UI overlay `com.miui.systemui.carriers.overlay` and MediaTek cell-broadcast vendor overlay `com.mediatek.cellbroadcastuiresoverlay`. The phone/telecom APKs and GMS telephony/telecom overlays were already removed in Build 2.
- Remove Notes Role enabled `com.android.role.notes.enabled`; its dedicated overlay directory is excluded.
- Check the stock EROFS image for an exact-match Health Connect module/APEX path, remove it if found, and report the exact result. Health Connect is absent from the verified stock APK inventory, so absence cannot be assumed without inspection.
- Add **Photon Gallery v2.1.3** official **arm64-v8a** APK to `/product/app/PhotonGallery/PhotonGallery.apk` as a system app. Verify the upstream APK SHA-256 before embedding.
- Preserve Xiaomi's original `flash_all.bat`, other fastboot scripts, partition layout, and retained APK ownership, modes and SELinux contexts; rebuild modified EROFS images and refresh patched vbmeta / CRC metadata.
- Original Gallery and Gallery Editor remain removed (as in Build 2).

## Distribution

A **complete fastboot firmware ZIP** is constructed and SHA-256 checked before release publishing. GitHub Releases limits each individual file to **2 GiB**, so the complete ZIP must be transported as release-hosted numbered binary segments and reassembled on Windows. **No expiring GitHub Actions download artifacts** are used.

## Critical warnings

Experimental firmware for an **unlocked bootloader only**. Removing ContactsProvider can break account sync, Android contacts APIs and contact-dependent apps. Removing the vendor cell-broadcast overlay adds compatibility risk. Adding Photon Gallery as a system app does not guarantee it becomes the default gallery role holder. This release must not be described as physically boot-tested. Back up first and retain a known-working Build 2 rescue image. The original stock `flash_all.bat` may wipe userdata. Never use `flash_all_lock.bat` or relock your bootloader with these images.

Photon Gallery upstream: https://github.com/Bn5prS/Photon_Gallery (GPL-3.0).
