#!/usr/bin/env python3
import json
import os
import signal
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from cherubini.cherubini import CherubiniRemoteDriver, command_map

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "cherubini")
MQTT_TOPIC_BASE = "cherubini"
MQTT_TOPIC_CMD = f"{MQTT_TOPIC_BASE}/cmd"
MQTT_TOPIC_AVAILABILITY = f"{MQTT_TOPIC_BASE}/availability"
MQTT_USERNAME = os.getenv("MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None

TX_PIN = int(os.getenv("TX_PIN", "23"))
REMOTE_CONFIG_PATH = os.getenv("CHERUBINI_REMOTE_CONFIG_PATH", "remote.json")


discovery_topic = "homeassistant/cover/window_blinds/config"
discovery_payload = {
    "name": "Window Blinds",
    "unique_id": "blinds_01",
    "command_topic": MQTT_TOPIC_CMD,
    "availability_topic": MQTT_TOPIC_AVAILABILITY,
    "payload_open": "UP",
    "payload_close": "DOWN",
    "payload_stop": "STOP",
    "optimistic": True,
    "device": {
        "name": "Cherubini",
        "manufacturer": "Cherubini",
        "model": "Giro Wall",
    },
}


def load_remote_config(path: str):
    with open(path, "r") as f:
        config = json.load(f)

    return int(config["serial_id"], 16), int(config["key"], 16), int(config.get("counter", 0), 16)


def save_remote_config(path: str, serial_id: int, key: int, counter: int):
    config = {
        "serial_id": hex(serial_id),
        "key": hex(key),
        "counter": hex(counter),
    }

    with open(path, "w") as f:
        json.dump(config, f, indent=4)


driver = CherubiniRemoteDriver(tx_pin=TX_PIN)


def on_connect(client, _userdata, _flags, reason_code, _properties):
    print(f"Connected with result code {reason_code}")
    client.subscribe(MQTT_TOPIC_CMD, qos=1)


def on_message(_c, _u, message):
    command = (message.payload.decode() if message.payload else "").strip().upper()
    button = command_map.get(command.upper())

    if button is None:
        print("Ignoring:", repr(command))
        return

    serial_id, key, counter = load_remote_config(REMOTE_CONFIG_PATH)
    counter = (counter + 1) & 0xFFFF
    driver.transmit(serial_id=serial_id, counter=counter, button=button, key=key)
    save_remote_config(REMOTE_CONFIG_PATH, serial_id, key, counter)
    print("Sent command:", command)


client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
if MQTT_USERNAME and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

client.on_connect = on_connect
client.on_message = on_message

client.will_set(MQTT_TOPIC_AVAILABILITY, "offline", qos=1, retain=True)


def handle_shutdown(_signum, _frame):
    print("Shutting down...", flush=True)
    try:
        client.publish(MQTT_TOPIC_AVAILABILITY, "offline", qos=1, retain=True)
        client.disconnect()
    except Exception:
        pass


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
client.publish(MQTT_TOPIC_AVAILABILITY, "online", qos=1, retain=True)
client.publish(discovery_topic, json.dumps(discovery_payload), qos=1, retain=True)
print(f"Listening for MQTT '{MQTT_TOPIC_CMD}' (UP/DOWN/STOP)")
client.loop_forever()

try:
    driver.close()
except Exception:
    pass
