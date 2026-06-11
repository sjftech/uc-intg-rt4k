"""
RetroTINK-4K integration driver for Unfolded Circle Remote 3.

Exposes a remote entity for each RT4K (Pro on ttyUSB0, CE on ttyUSB1),
sending commands via Home Assistant's REST API to the serial-connected devices.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import aiohttp
import ucapi
from ucapi.remote import Attributes as RemoteAttr
from ucapi.remote import Features as RemoteFeatures
from ucapi.remote import States as RemoteStates

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_FILE = "rt4k_config.json"

# Maps UCR3 command IDs to RT4K serial commands.
# "on" and "off" are the built-in IDs sent by UCR3 activity power sequences.
# POWER_ON and POWER_OFF are the user-facing simple command names.
COMMAND_MAP: dict[str, str] = {
    "POWER_ON":   "pwr on",
    "POWER_OFF":  "remote pwr",
    "MENU":       "remote menu",
    "UP":         "remote up",
    "DOWN":       "remote down",
    "LEFT":       "remote left",
    "RIGHT":      "remote right",
    "OK":         "remote ok",
    "BACK":       "remote back",
    "DIAG":       "remote diag",
    "STAT":       "remote stat",
    "INPUT":      "remote input",
    "OUTPUT":     "remote output",
    "SCALER":     "remote scaler",
    "SFX":        "remote sfx",
    "ADC":        "remote adc",
    "COL":        "remote col",
    "AUD":        "remote aud",
    "PROF":       "remote prof",
    "PROF1":      "remote prof1",
    "PROF2":      "remote prof2",
    "PROF3":      "remote prof3",
    "PROF4":      "remote prof4",
    "PROF5":      "remote prof5",
    "PROF6":      "remote prof6",
    "PROF7":      "remote prof7",
    "PROF8":      "remote prof8",
    "PROF9":      "remote prof9",
    "PROF10":     "remote prof10",
    "PROF11":     "remote prof11",
    "PROF12":     "remote prof12",
    "GAIN":       "remote gain",
    "PHASE":      "remote phase",
    "PAUSE":      "remote pause",
    "SAFE":       "remote safe",
    "GENLOCK":    "remote genlock",
    "BUFFER":     "remote buffer",
    "RES4K":      "remote res4k",
    "RES1080P":   "remote res1080p",
    "RES1440P":   "remote res1440p",
    "RES480P":    "remote res480p",
    "RES1":       "remote res1",
    "RES2":       "remote res2",
    "RES3":       "remote res3",
    "RES4":       "remote res4",
    "AUX1":       "remote aux1",
    "AUX2":       "remote aux2",
    "AUX3":       "remote aux3",
    "AUX4":       "remote aux4",
    "AUX5":       "remote aux5",
    "AUX6":       "remote aux6",
    "AUX7":       "remote aux7",
    "AUX8":       "remote aux8",
}

SIMPLE_COMMANDS = list(COMMAND_MAP.keys())

DEVICES: dict[str, str] = {
    "rt4k_pro": "RetroTINK-4K Pro",
    "rt4k_ce":  "RetroTINK-4K CE",
}

# ---------------------------------------------------------------------------
# ucapi setup
# ---------------------------------------------------------------------------

loop = asyncio.new_event_loop()
api = ucapi.IntegrationAPI(loop)

_ha_url: str = ""
_ha_token: str = ""
_device_paths: dict[str, str] = {"rt4k_pro": "", "rt4k_ce": ""}
_power_states: dict[str, RemoteStates] = {
    "rt4k_pro": RemoteStates.OFF,
    "rt4k_ce":  RemoteStates.OFF,
}
_session: aiohttp.ClientSession | None = None


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    config_home = os.environ.get("UC_CONFIG_HOME", str(Path.home()))
    return Path(config_home) / CONFIG_FILE


def _load_config() -> bool:
    global _ha_url, _ha_token
    path = _config_path()
    if not path.exists():
        return False
    try:
        with open(path) as f:
            cfg = json.load(f)
        _ha_url = cfg.get("ha_url", "")
        _ha_token = cfg.get("ha_token", "")
        _device_paths["rt4k_pro"] = cfg.get("rt4k_pro_path", "")
        _device_paths["rt4k_ce"] = cfg.get("rt4k_ce_path", "")
        _LOGGER.info("Config loaded from %s", path)
        return bool(_ha_url and _ha_token)
    except Exception as e:
        _LOGGER.error("Failed to load config: %s", e)
        return False


def _save_config() -> None:
    path = _config_path()
    try:
        with open(path, "w") as f:
            json.dump(
                {
                    "ha_url":        _ha_url,
                    "ha_token":      _ha_token,
                    "rt4k_pro_path": _device_paths["rt4k_pro"],
                    "rt4k_ce_path":  _device_paths["rt4k_ce"],
                },
                f,
                indent=2,
            )
        _LOGGER.debug("Config saved to %s", path)
    except Exception as e:
        _LOGGER.error("Failed to save config: %s", e)


# ---------------------------------------------------------------------------
# HA REST API
# ---------------------------------------------------------------------------

async def _send_ha_command(entity_id: str, serial_command: str) -> bool:
    """POST a shell_command service call to HA's REST API."""
    global _session

    device_path = _device_paths.get(entity_id, "")
    if not device_path:
        _LOGGER.error("No device path configured for %s", entity_id)
        return False

    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()

    headers = {
        "Authorization": f"Bearer {_ha_token}",
        "Content-Type": "application/json",
    }
    payload = {"device": device_path, "command": serial_command}

    try:
        async with asyncio.timeout(5):
            resp = await _session.post(
                f"{_ha_url}/api/services/shell_command/retrotink_4k_send",
                json=payload,
                headers=headers,
            )
            if resp.status != 200:
                _LOGGER.error(
                    "HA API returned %d for '%s' on %s",
                    resp.status, serial_command, entity_id,
                )
                return False
            _LOGGER.debug("Sent '%s' to %s", serial_command, entity_id)
            return True
    except TimeoutError:
        _LOGGER.error("Timeout sending '%s' to %s", serial_command, entity_id)
        return False
    except aiohttp.ClientError as e:
        _LOGGER.error("HTTP error sending '%s': %s", serial_command, e)
        return False


# ---------------------------------------------------------------------------
# Entity management
# ---------------------------------------------------------------------------

async def _cmd_handler(
    entity: ucapi.remote.Remote,
    cmd_id: str,
    params: dict[str, Any] | None,
    websocket: Any,
) -> ucapi.StatusCodes:
    """Handle all remote commands from the UCR3."""
    entity_id = entity.id

    # 1. Unpack the "send_cmd" wrapper to get the actual button press
    if cmd_id == "send_cmd":
        if params and "command" in params:
            cmd_id = params["command"]
        else:
            _LOGGER.warning("Received 'send_cmd' but no command in params for %s", entity_id)
            return ucapi.StatusCodes.BAD_REQUEST

    # 2. UCR3 activity power sequences send lowercase "on"/"off".
    # Manual presses from the command list send "POWER_ON"/"POWER_OFF".
    # Normalise both to our COMMAND_MAP keys.
    if cmd_id == "on":
        cmd_id = "POWER_ON"
    elif cmd_id == "off":
        cmd_id = "POWER_OFF"

    serial_command = COMMAND_MAP.get(cmd_id)
    if serial_command is None:
        _LOGGER.warning("Unknown command '%s' for %s", cmd_id, entity_id)
        return ucapi.StatusCodes.BAD_REQUEST

    success = await _send_ha_command(entity_id, serial_command)
    if not success:
        return ucapi.StatusCodes.SERVER_ERROR

    # Track power state so the UCR3 activity knows the device is on/off.
    if cmd_id == "POWER_ON":
        _power_states[entity_id] = RemoteStates.ON
        api.configured_entities.update_attributes(
            entity_id, {RemoteAttr.STATE: RemoteStates.ON}
        )
    elif cmd_id == "POWER_OFF":
        _power_states[entity_id] = RemoteStates.OFF
        api.configured_entities.update_attributes(
            entity_id, {RemoteAttr.STATE: RemoteStates.OFF}
        )

    return ucapi.StatusCodes.OK


def _create_entity(entity_id: str, name: str) -> ucapi.remote.Remote:
    return ucapi.remote.Remote(
        entity_id,
        {"en": name},
        features=[RemoteFeatures.ON_OFF, RemoteFeatures.SEND_CMD],
        attributes={RemoteAttr.STATE: _power_states.get(entity_id, RemoteStates.OFF)},
        simple_commands=SIMPLE_COMMANDS,
        cmd_handler=_cmd_handler,
    )


def _register_entities() -> None:
    for entity_id, name in DEVICES.items():
        entity = _create_entity(entity_id, name)
        if not api.available_entities.contains(entity.id):
            api.available_entities.add(entity)
            _LOGGER.info("Registered entity: %s (%s)", entity_id, name)


# ---------------------------------------------------------------------------
# UCR3 event handlers
# ---------------------------------------------------------------------------

@api.listens_to(ucapi.Events.CONNECT)
async def on_connect():
    _LOGGER.info("Remote connected")
    await api.set_device_state(ucapi.DeviceStates.CONNECTED)


@api.listens_to(ucapi.Events.DISCONNECT)
async def on_disconnect():
    _LOGGER.info("Remote disconnected")


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def on_enter_standby():
    _LOGGER.debug("Remote entering standby")


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def on_exit_standby():
    _LOGGER.debug("Remote exiting standby")


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def on_subscribe_entities(entity_ids: list[str]):
    """Push current power state when the UCR3 subscribes to our entities."""
    _LOGGER.info("Subscribe entities: %s", entity_ids)
    for entity_id in entity_ids:
        if entity_id in DEVICES:
            api.configured_entities.update_attributes(
                entity_id,
                {RemoteAttr.STATE: _power_states.get(entity_id, RemoteStates.OFF)},
            )


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def on_unsubscribe_entities(entity_ids: list[str]):
    _LOGGER.info("Unsubscribe entities: %s", entity_ids)


# ---------------------------------------------------------------------------
# Setup flow
# ---------------------------------------------------------------------------

async def driver_setup_handler(msg: ucapi.SetupDriver) -> ucapi.SetupAction:
    if isinstance(msg, ucapi.DriverSetupRequest):
        return await _handle_setup_request(msg)
    if isinstance(msg, ucapi.UserDataResponse):
        return await _handle_user_data(msg)
    return ucapi.SetupError()


async def _handle_setup_request(msg: ucapi.DriverSetupRequest) -> ucapi.SetupAction:
    """
    Process the setup form defined in driver.json.
    Validates the HA connection before saving config and registering entities.
    """
    global _ha_url, _ha_token

    ha_url    = msg.setup_data.get("ha_url", "").strip().rstrip("/")
    ha_token  = msg.setup_data.get("ha_token", "").strip()
    pro_path  = msg.setup_data.get("rt4k_pro_path", "").strip()
    ce_path   = msg.setup_data.get("rt4k_ce_path", "").strip()

    if not ha_url or not ha_token:
        _LOGGER.error("Setup: HA URL or token missing")
        return ucapi.SetupError(ucapi.IntegrationSetupError.NOT_FOUND)

    # Verify the token works before saving anything.
    try:
        async with aiohttp.ClientSession() as session:
            async with asyncio.timeout(5):
                resp = await session.get(
                    f"{ha_url}/api/",
                    headers={"Authorization": f"Bearer {ha_token}"},
                )
                if resp.status != 200:
                    _LOGGER.error("Setup: HA returned %d", resp.status)
                    return ucapi.SetupError(ucapi.IntegrationSetupError.CONNECTION_REFUSED)
    except Exception as e:
        _LOGGER.error("Setup: could not reach HA at %s: %s", ha_url, e)
        return ucapi.SetupError(ucapi.IntegrationSetupError.CONNECTION_REFUSED)

    _ha_url = ha_url
    _ha_token = ha_token
    _device_paths["rt4k_pro"] = pro_path
    _device_paths["rt4k_ce"]  = ce_path

    _save_config()
    _register_entities()

    _LOGGER.info(
        "Setup complete — HA: %s  Pro: %s  CE: %s",
        ha_url, pro_path, ce_path,
    )
    return ucapi.SetupComplete()


async def _handle_user_data(msg: ucapi.UserDataResponse) -> ucapi.SetupAction:
    # No second-step user input in this integration.
    return ucapi.SetupError()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    if _load_config():
        _register_entities()

    await api.init("driver.json", driver_setup_handler)


if __name__ == "__main__":
    loop.run_until_complete(main())
    loop.run_forever()