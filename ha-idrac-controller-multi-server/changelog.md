## 0.1.0-ms.10 - 2026-10-01

* ✨ **New Feature**: Added `chassis_power_on` and `chassis_power_control` methods to `IPMIManager` to power on servers via IPMI.
* ✨ **New Feature**: Added a "Power On Server" button entity in Home Assistant via MQTT Discovery (`command/power_on`).

## 0.1.0-ms.9 - 2026-09-22

* 🐛 **Bug Fix**: The "Configuration saved" toast no longer links to `/hassio/dashboard` — that path 404s on many reverse-proxy/ingress setups. It now just tells you to restart via Settings > Add-ons.

## 0.1.0-ms.8 - 2026-09-22

* 🚀 **Performance**: Each server now builds a local SDR cache (`/data/sdr_cache_<ip>.bin`) at startup and passes it to `ipmitool` with `-S`. Without it, every single sensor read re-downloads the whole sensor repository over the network, which is slow enough to time out on large chassis such as the R730xd.
* 🔧 **Improvement**: Raised sensor read timeouts (temperature and fan 30s, full SDR list 45s) to suit servers with many sensors.
* 🔧 **Improvement**: The SDR cache is rebuilt automatically after five consecutive failed cycles, so a stale cache cannot permanently break sensor reads.

## 0.1.0-ms.7 - 2026-09-22

* 🐛 **Bug Fix**: Added exponential backoff when a server stops responding. A timed-out `ipmitool` call leaves its session open on the iDRAC, so polling a struggling BMC every cycle exhausted its session table and produced a self-sustaining loop of "insufficient resources for session" errors. Backoff now doubles from the check interval up to a 15 minute ceiling and resets on the first clean read.
* 🔧 **Improvement**: Worker sleeps are now interruptible, so the add-on shuts down promptly instead of blocking for up to a full interval.

## 0.1.0-ms.6 - 2026-09-22

* 🐛 **Bug Fix**: Adding a server no longer ends on a 404. The redirect after Add, and the error redirects from Edit and Delete, resolved relative to the wrong path (for example `/servers/servers`).
* 🎨 **UI Improvement**: Setting Fan Control to "Disabled (Monitor Only)" now hides the fan speed, threshold, and fan mode fields on the Add and Edit Server pages.

## 0.1.0-ms.5 - 2026-09-22

* 🔒 **Security Fix**: The iDRAC password is no longer written to the add-on log. Failed and timed-out `ipmitool` invocations previously logged the full command line, including `-P <password>` in plaintext.
* ✨ **New Feature**: Added a per-server **IPMI Privilege Level** setting (Administrator or Operator). The level is passed to `ipmitool` as `-L`, which is required by iDRACs that reject sessions when the requested privilege exceeds the account's assigned level.
* 🔧 **Improvement**: When a server is set to Operator, manual fan control commands are skipped with a log message instead of failing repeatedly, since Dell fan profile overrides require Administrator.

## 0.1.0-ms.4 - 2026-09-22

* 🐛 **Bug Fix**: The `temperature_unit` option now actually works. When set to `F`, fan thresholds, the PID target temperature, and fan curve points are converted to Celsius before being compared against sensor readings. Previously the option was read by `run.sh` but ignored by the app, so Fahrenheit values were treated as Celsius.
* 🎨 **UI Improvement**: Temperature input labels on the Add and Edit Server pages now show the configured unit instead of always showing °C.
* 🔧 **Improvement**: The `check_interval_seconds` fallback default now matches the add-on config default of 30 seconds (was 60).

## 0.1.0-ms.3 - 2026-09-22

* ✨ **New Feature**: Added a "monitor-only" mode to disable fan control on a per-server basis, with a "Fan Control" dropdown on the Add and Edit Server pages.
* 🐛 **Bug Fix**: Power consumption is now parsed correctly on older iDRAC 6 servers, which report the "System Level" sensor instead of "Pwr Consumption".
* 🐛 **Bug Fix**: The "Back to Server List" link on the Edit Server page no longer resolves to a dead URL.

## 0.1.0-ms.2 - 2026-09-22

* 🐛 **Bug Fix**: MQTT client ID is now unique per add-on instance. Running two copies of the add-on no longer causes the broker to kick both clients in an endless connect/disconnect loop.
* 🔧 **Improvement**: Added MQTT reconnect backoff (1s to 120s).

## 0.1.0-ms.1

* Initial multi-server release, branched from the development variant.
