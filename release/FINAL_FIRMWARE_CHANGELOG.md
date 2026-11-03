# Build 1 - Final Firmware Release

**Device:** Xiaomi Redmi Pad (`yunluo`) · **Firmware:** HyperOS 1 Global OS1.0.9.0.ULYMIXM (Android 14)

### Changes

- Retains all **53 APK removals from Build 6**.
- Removes **Notes** (`com.miui.notes`) and its entire `product_a:/data-app/MIUINotes` folder.
- **Total:** 54 stock APKs removed: **52 complete app folders** and 2 individual shared-overlay APKs.
- Replaces stock `images/boot.img` with the user's already-tested **KernelSU Next** boot image, renamed exactly `boot.img`. SHA-256: `32eb0d6558828992e4bc64aeb217dcd38e73875f65e32a24a17c8c578aff3c81`.
- Preserves disabled-verity/verification `vbmeta.img`; updates `boot_a` and `vbmeta_a` in `crclist.txt`; recalculates `super` in `sparsecrclist.txt`.
- Leaves Xiaomi's original `flash_all.bat`, all other firmware files, system launcher, and critical core services unchanged.

### Download (no manual merging)

**GitHub Releases limits each asset to 2 GiB.** The complete `firmware.zip` is too large for one Release asset, so the three parts are uploaded permanently alongside `ONE_CLICK_DOWNLOAD_AND_EXTRACT.ps1`. Download **only that script** and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\ONE_CLICK_DOWNLOAD_AND_EXTRACT.ps1
```

It automatically downloads all parts, SHA-256 verifies each, creates one **`firmware.zip`** locally, extracts the complete fastboot firmware and checks the six files (super, KernelSU boot, vbmeta, both CRC lists, original flash_all.bat). No manual merging.

**Netflix:** user-installed `com.netflix.mediaclient` resides in `/data/app`, not stock `super.img`. Use the included optional `REMOVE_NETFLIX_USER_APP.ps1` after boot if still present.

### Important

The KernelSU Next boot image was independently reported working by the tablet owner; combined final firmware flashing/booting must still be verified on the device. Keep the bootloader unlocked. Original Xiaomi flashing scripts can erase user data.

**Final project release.** All earlier releases and tags are removed only after this complete firmware release has passed upload checks and is published.
