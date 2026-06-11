# intg-retrotink4k

Unfolded Circle Remote 3 integration for RetroTINK-4K Pro and CE.

Exposes a `remote` entity for each device, sending commands via Home Assistant's
REST API to the serial-connected scalers. Bypasses the UCR3's built-in HA
WebSocket integration entirely — each button press is a stateless HTTP POST,
so there is no persistent connection to drop.

## Requirements

- Home Assistant with `shell_command.retrotink_4k_send` configured
- Both RT4K devices connected via USB serial with stable `/dev/serial/by-id/` paths
- A Home Assistant long-lived access token

## Building

Push a tag to trigger the GitHub Actions workflow:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow builds an aarch64 binary via PyInstaller in a QEMU-emulated Docker
container and attaches the `.tar.gz` package to the GitHub release.

You can also trigger a build manually from the Actions tab using
**Run workflow** without creating a tag — the artifact will be available
for download from the workflow run.

## Installation

Upload the `.tar.gz` to your Remote 3 via the integrations page.

## Setup

During setup you will be prompted for:

- **Home Assistant URL** — e.g. `http://192.168.3.2:8123`
- **Long-lived Access Token** — create one in HA under your profile → Security
- **RT4K Pro Serial Device Path** — e.g. `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_XXXXXXXX-if00-port0`
- **RT4K CE Serial Device Path** — e.g. `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_YYYYYYYY-if00-port0`

The integration will verify the HA connection before saving. If either the URL
or token is wrong it will return a connection error at setup time rather than
failing silently later.

## Home Assistant configuration

Only `shell_command` is required in `configuration.yaml`:

```yaml
shell_command:
  retrotink_4k_send: /bin/sh -c 'stty -F "{{ device }}" 115200 cs8 -cstopb -parenb && echo "{{ command }}" > "{{ device }}"'
```

No `input_select`, automations, or scripts are needed.

## Commands

All RetroTINK-4K serial commands are exposed as simple commands on the remote
entity. `POWER_ON` and `POWER_OFF` also update the entity's power state, which
the UCR3 uses for activity on/off sequencing.

| Command | Serial |
|---------|--------|
| POWER_ON | `pwr on` |
| POWER_OFF | `remote pwr` |
| MENU | `remote menu` |
| UP / DOWN / LEFT / RIGHT | `remote up` etc. |
| OK | `remote ok` |
| BACK | `remote back` |
| PROF1–PROF12 | `remote prof1` etc. |
| RES4K / RES1080P / RES1440P / RES480P | `remote res4k` etc. |
| AUX1–AUX8 | `remote aux1` etc. |
| DIAG, STAT, INPUT, OUTPUT, SCALER, SFX, ADC, COL, AUD, PROF, GAIN, PHASE, PAUSE, SAFE, GENLOCK, BUFFER, RES1–RES4 | as named |
