# v.0.2 - HyperOS1 Yunluo (Experimental Build 3 revision)

**Device:** Redmi Pad Wi-Fi-only (yunluo)  
**Firmware:** HyperOS 1 Global OS1.0.9.0.ULYMIXM, Android 14  
**Status:** Experimental; prior Build 2 successfully booted. This revision is not yet device boot-tested.  
**Distribution:** GitHub Release assets containing all bytes of the full fastboot ZIP; NOT GitHub Actions artifacts.

## Changes inherited from v.0.1 Build 3

- Remove 124 selected package IDs (125 original stock APK instances), including 106 entire app/overlay folders and 19 individually selected shared-overlay APKs.
- Remove MSA advertising app, ContactsProvider, contacts/Telecom overlays, carrier components, and Notes Role enabled.
- Continue removal of the stock Gallery and Gallery Editor.
- Install official **Photon Gallery v2.1.3 arm64-v8a** at **/product/app/PhotonGallery/PhotonGallery.apk** as a system app, with APK SHA-256 validation, UID/GID, permissions and SELinux verification.
- Preserve original Xiaomi fastboot scripts including flash_all.bat byte-for-byte, stock dynamic LP metadata, and the ownership, modes, SELinux contexts and binaries of retained APKs.

## Additional v.0.2 changes — Android 14 APEX modules

- Remove the exact stock APEX archive for **HealthFitness** `com.google.android.healthfitness` (or corresponding `com.android.healthfitness` build). This contains `com.google.android.healthconnect.controller` on the user's device.
- **Retain the CellBroadcast APEX** (`com.google.android.cellbroadcast` or `com.android.cellbroadcast`) so the emergency-alert module is not removed. Earlier selected carrier configuration and optional legacy overlays remain subject to the prior Build 3 debloat policy.
- Remove the exact stock **AdServices** APEX archive `com.google.android.adservices` (or `com.android.adservices`). The Mainline Ad Services APK was already removed in Build 2.
- Verify two selected APEX modules (HealthFitness and AdServices) are physically absent from rebuilt EROFS. Refuse to publish if a selected archive is absent from the stock source.
- Preserve *every other* built-in APEX file byte-for-byte including its UID/GID, permissions and SELinux label. **Explicitly preserve Network Stack, Wi-Fi, DNS Resolver, tethering, IPsec and CellBroadcast APEX**.

## Integrity and packaging

- Validate all selected app/overlay and APEX paths absent from rebuilt EROFS partitions.
- Validate retained APKs/APEXes unchanged and Photon Gallery correctly integrated.
- Verify sparse super.img encoding and LP metadata; update vbmeta and Xiaomi CRC lists.
- Construct one FULL firmware ZIP, test its ZIP CRCs and verify its SHA-256 before distribution.
- GitHub limits each release asset to 2 GiB: all bytes of the full firmware ZIP are published as numbered Release assets, with checksums and a Windows PowerShell reassembly script. These are **not temporary Actions artifacts**.
- Release only after all checks pass; an experimental GitHub prerelease is not a confirmation of successful tablet boot.

## Critical warnings

**Risk of boot failure:** The modified APEX selection has NOT been tested on a real device; Android may rely on selected modules for core features. Removing Health Connect can break apps relying on its APIs. Removing AdServices may affect apps expecting its API. **CellBroadcast emergency-alert APEX is retained**.

**Updated /data modules:** Android may use newer APEX modules from userdata even after removing the system copy. This firmware project does not silently delete the user's data or promise that updated APEXes will disappear without additional device checks.

The tablet bootloader must remain unlocked; never flash `flash_all_lock.bat` or relock. Xiaomi's original `flash_all.bat` may erase userdata. Back up data and retain a boot-tested Build 2 recovery firmware.

Upstream Photon Gallery is GPL-3.0: https://github.com/Bn5prS/Photon_Gallery.
