# HyperOS Build 1 — Stage 3 Final APK Inventory

**Run:** [Stage 3 GitHub Actions #40794158139](https://github.com/hashyofficial/copilot_project-2/actions/runs/40794158139)  
**Artifact:** [APK inventory ZIP (30-day Actions artifact)](https://github.com/hashyofficial/copilot_project-2/actions/runs/40794158139/artifacts/12862464562)  
**Source:** original, unmodified Xiaomi Global MIXM fastboot firmware, OS1.0.9.0.ULYMIXM (Android 14), codename yunluo  
**Published MD5 verified:** `f8dbb84a10dc96a9d3ce9e78883e87f3`  
**Measured source SHA-256:** `90562e6f369bb17cdaf67a86f2b72b16492fb1a63c86f7e389cf2ba306942530`

## Inventory result

Read-only scan of **all seven** populated super.img logical partitions: **336 files with an `.apk` extension**. Of those, **329 are nonempty APKs** and all **329 package IDs parsed successfully**. There are **307 distinct Android package IDs** (some packages have multiple APK instances, e.g. overlays).

| Logical partition | Nonempty APKs | Zero-byte .apk placeholders |
|---|---:|---:|
| product_a | 166 | 0 |
| system_a | 76 | 0 |
| system_ext_a | 50 | 0 |
| vendor_a | 14 | 0 |
| mi_ext_a | 23 | 7 |
| vendor_dlkm_a | 0 | 0 |
| odm_dlkm_a | 0 | 0 |
| **Total** | **329** | **7** |

### Important finding: seven .apk path placeholders in mi_ext_a

The original Stage 3 artifact labels seven entries "package ID parse errors." Inspection of the artifact's CSV revealed these files are **exactly zero bytes**, so they contain **no APK ZIP data or package manifest**; aapt2 correctly rejected them as invalid APK ZIP files. They are filesystem placeholders, **not seven missing package IDs from valid APKs**:

```text
mi_ext_a:/product/app/Calendar/Calendar.apk
mi_ext_a:/product/app/GoogleCalendarSyncAdapter/GoogleCalendarSyncAdapter.apk
mi_ext_a:/product/app/MiuiCalendarGlobalPad/MiuiCalendarGlobalPad.apk
mi_ext_a:/product/priv-app/Contacts/Contacts.apk
mi_ext_a:/product/priv-app/MiuiCalendarGlobalPad/MiuiCalendarGlobalPad.apk
mi_ext_a:/system_ext/app/MtkCalendar/MtkCalendar.apk
mi_ext_a:/system_ext/priv-app/MtkContacts/MtkContacts.apk
```

**Preserve these original placeholders until their actual purpose is established; do not count them as removable app APKs or infer their package IDs from filenames.** They may participate in Xiaomi's image layout/packaging; their purpose was not established by this read-only scan.

## Artifact contents

- `APK_LIST.txt`: all 336 original on-disk paths, including seven placeholders
- `APK_DETAILS.csv`, `APK_DETAILS.tsv`, `APK_DETAILS.json`: package ID, application label, version, full source path, original UID/GID, mode, size, available SELinux label, and required library metadata
- `APK_BY_PARTITION.txt`: partition-grouped package IDs and APK paths
- `APK_PACKAGE_ERRORS.txt`: the seven invalid zero-length placeholder entries
- `APK_SUMMARY.json`, `STAGE3_RESULTS.md`: automatic raw counts (336 extension matches, 329 parsed)
- Partition geometry reports, source hash verification, and stock firmware metadata

**No firmware image was modified, no application was removed, no vbmeta was patched and no release was published.** Stage 4 begins only after the user reviews the APK list and supplies their removal selection. APEX/CAPEX packages embedded in containers are outside this on-disk `.apk` path inventory.
