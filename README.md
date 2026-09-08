This is my attempt at making the Cbus Cgate system communicate with Home Assistant.
This project was based on Dave Oxley's CBUS Library and Scott Linton CBus Openhab Add-On.

Make the following folders in your Home Assistant
custom_components -> cbus

Within the cbus folder, place all the files into

---

## How groups are classified

Discovery reads the physical units first, so it knows which relay or dimmer
channel drives each lighting group. Classification then goes, in order:

1. name contains `exhaust` / `ex fan` → `switch` with an exhaust-fan icon
2. name contains `fan` → `fan` (Low / Medium / High presets)
3. driven by a **dimmer** (`DIM*`) → `light`, dimmable
4. driven by a **relay** (`REL*`) → `light` (on/off) — unless the name is
   clearly a non-light load (`gate`, `motor`, `hot water`, `pump`, `door`,
   `rsd`, `blind`, `outlet`, `charger`, …) → `switch`. Light words
   (`light`, `lamp`, `flood`, `d/l`, `led`, …) always win, so "Gate Floods"
   is a light and "Gate Motor" is a switch.
5. programmed on keypads only (no output unit) → `switch` (a virtual /
   scene / flag group, e.g. a PIR override)
6. `Type=area` groups and groups with no units → no entity

Groups named `… Spare` get entities that are **disabled by default**.

## Group classification overrides (optional)

If the rules above still get something wrong you can pin the answer.

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

---

## Physical units, PIR motion, and keypad events (v0.4+)

Discovery now also enumerates every physical unit on the network
(`get //proj/net Units` → `get //proj/net/p/N *` + `dbget`) and classifies it:

| Role      | C-Gate unit types                          | What you get in HA                                   |
|-----------|--------------------------------------------|------------------------------------------------------|
| `load`    | `RELDN*`, `RELAY*`, `DIMDN*`, `DIM*`       | A **device** per relay/dimmer; its groups' light/switch/fan entities attach to it |
| `keypad`  | `KEYE*`, `KEYEIR*`, other `KEY*` (Saturn/Neo) | A device + an **`event` entity** (`on` / `off` / `ramp`) fired on physical key presses |
| `edlt`    | `KEYGL*` (glass eDLT), `DLT*`              | Same as keypad; key slots come from the eDLT `WidgetGroups` table |
| `pir`     | `SENPIR*`                                  | A device + **`binary_sensor` (motion)** + **`sensor` (lux)** if the unit reports `LightLevel` |

### How motion / key presses are derived

C-Bus input units don't publish their own "pressed" or "motion" telegrams —
they are programmed to switch lighting groups directly. C-Gate, however, tags
every group change with the unit that originated it (`#sourceunit=N` on the
load-change port). The integration uses that:

- **`binary_sensor.<pir>_motion`** turns **on** when the PIR unit itself
  switches one of its groups on, and **off** when that group goes to 0 (PIR
  timeout, a keypad, or HA). Attributes: `group`, `group_name`, `last_motion`.
- **`event.<keypad>_keys`** fires `on` / `off` / `ramp` whenever that keypad
  originates a change. Attributes: `group`, `group_name`, `level`, `slot`
  (key position). The entity also lists all its `keys` as an attribute.
- Additionally every input-unit originated change is published on the HA
  event bus as **`cbus_unit_event`** with `unit`, `unit_name`, `unit_type`,
  `app`, `group`, `group_name`, `level`, `slot` — handy for automations:

```yaml
trigger:
  - platform: event
    event_type: cbus_unit_event
    event_data:
      unit_name: "EDLT1 Kitchen"
      group: 69          # Gate Motor key
```

- **`sensor.<pir>_light_level`** polls the PIR's `LightLevel` parameter
  (lux, 0–1600, refreshed by C-Gate's parameter sync) every 2 minutes.

A group that lives only on keypads (no relay/dimmer) is attached to the first
keypad's device; list it in `cbus_overrides.json` as a `switch` to expose it.

---

## Dynamic eDLT labels (v0.5+) — `cbus.set_label`

Push text to the glass eDLT / DLT keypad widgets so Home Assistant data
(Sonos track, temperature, alarm state) shows on the physical keypads.

Labels are addressed by **C-Bus group number** — the eDLT renders it on
whichever widget is mapped to that group (see the discovery log for each
eDLT's slot→group map).

```yaml
service: cbus.set_label
data:
  group: 69          # e.g. the "Gate Motor" widget on EDLT1 Kitchen
  text: "Gate Open"  # max 14 chars
```

| Field | Default | Notes |
|-------|---------|-------|
| `group` | — | C-Bus group whose widget label to set (required) |
| `text` | `""` | label text, ≤14 chars (truncated, whitespace collapsed) |
| `clear` | `false` | clear the label instead of setting text |
| `variant` | `F0` | widget label variant `F0`–`F3` |
| `unicode` | `true` | use `LIGHTING UNICODELABEL` (**required for glass 5055EDL eDLTs**); non-ASCII text is sent as raw UTF-8 |
| `language` | `1` | C-Bus label language code |
| `action_sel` | `-` | action selector; leave unset for a plain label |
| `icon` | — | numeric icon selector (non-unicode labels only) |
| `app` / `network` / `project` | `56` / configured | advanced overrides |

> **Glass eDLTs use unicode labels.** Once a group/variant holds a unicode
> label, C-Gate refuses plain-text labels for it — hence `unicode` defaults
> to on. Use `unicode: false` only for legacy DLTs. If a label doesn't
> appear, try a different `variant` (F0–F3) to match the widget.

### Example — show Sonos status on a keypad

```yaml
automation:
  - alias: "eDLT: Sonos now playing"
    trigger:
      - platform: state
        entity_id: media_player.kitchen_sonos
    action:
      - service: cbus.set_label
        data:
          group: 40      # Kitchen Main D/L widget on EDLT1
          text: >-
            {{ 'Vol ' ~ (state_attr('media_player.kitchen_sonos','volume_level')*100)|round(0)|int ~ '%'
               if is_state('media_player.kitchen_sonos','playing') else 'Idle' }}
```

Reacting to a physical keypad press (from the `event` entities added in
v0.4) pairs naturally with this — e.g. press a key, update its label.

---

## Resilience / link recovery (v0.6+)

C-Gate keeps answering `noop` on the command port even when the C-Bus
**network interface** has closed — so a keepalive alone can't tell that
events have stopped flowing. The integration now:

- polls `InterfaceState` every ~30 s and **reopens the network** if it has
  closed (C-Gate's `auto-reopen` plus a proactive `net open`);
- after any recovery — a closed network reopening, or the event/load-change
  sockets reattaching — runs a **full state resync** (re-reads every load
  group's level, ~0.7 s here) so entities can't be left stale for a change
  that happened while the link was down.

Resync updates carry no source unit, so they never fire spurious motion or
keypad `event`s.

---

## v0.7 additions

- **Link health & availability.** A `binary_sensor.<hub>_link` (connectivity,
  diagnostic) shows whether the C-Gate command port is up *and* the C-Bus
  network interface is running; its attributes carry reconnect / stream
  reattach / resync counters, the last link change and reason, and the
  C-Gate version. All C-Bus entities go **unavailable** while the link is
  down instead of showing stale state.
- **Light transitions.** `light.turn_on` / `turn_off` honour `transition:`
  (seconds) → C-Gate `ramp <group> <level> <n>s` (C-Gate rounds to the
  nearest C-Bus ramp rate). Works from HomeKit fades too.
- **Diagnostics.** Settings → Integrations → C-Bus → *Download diagnostics*
  gives the full discovery model (units, slots, groups), link stats, live
  levels and last-source-unit per group. Host is redacted.
- **Hub device.** A "C-Gate <project>/<network>" device (with C-Gate version)
  that every unit device hangs off via `via_device`.
- **All lighting applications.** Discovery enumerates every lighting-type
  application on the network (`$30`–`$5F`), not just 56. Override keys for
  non-default apps use `"app/group"` (e.g. `"65/1"`); plain `"group"` keys
  apply to app 56 only, and the file is authoritative for app 56 only.
- Config-flow field labels (`strings.json` / translations).
