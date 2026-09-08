This is my attempt at making the Cbus Cgate system communicate with Home Assistant.
This project was based on Dave Oxley's CBUS Library and Scott Linton CBus Openhab Add-On.

Make the following folders in your Home Assistant
custom_components -> cbus

Within the cbus folder, place all the files into

---

## Group classification overrides (optional)

By default the integration guesses each C-Bus lighting group's type from its
name and unit count (see `discovery.py._classify`). That heuristic can
misclassify loads — most commonly it can't tell a dimmer from a relay.

To pin ground-truth types, drop a file at **`/config/cbus_overrides.json`** on
your Home Assistant instance. See `cbus_overrides.sample.json` for the format:

```json
{
  "1":  { "device_class": "light",  "dimmable": true,  "name": "Kitchen Downlights" },
  "12": { "device_class": "light",  "dimmable": false, "name": "Pantry" }
}
```

- Keys are C-Bus **group numbers** (application 56 / lighting).
- `device_class` is one of `light`, `switch`, `fan`.
- `dimmable` controls whether a light exposes brightness (`BRIGHTNESS`) or is
  on/off only (`ONOFF`).
- `name` (optional) overrides the Toolkit tag name.

**When the overrides file is present it is authoritative:** only the groups
listed in it are created as entities; unlisted groups are skipped. Remove the
file to fall back to name/unit auto-classification.
