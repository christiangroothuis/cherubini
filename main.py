#!/usr/bin/env python3
import json
import os
import paho.mqtt.client as mqtt

from cherubini import CherubiniRemoteDriver

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "cherubini")
MQTT_TOPIC = "cherubini/command"
MQTT_USERNAME = os.getenv("MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None

TX_PIN = int(os.getenv("TX_PIN", "23"))
REMOTE_CONFIG_PATH = os.getenv("CHERUBINI_REMOTE_CONFIG_PATH", "remote.json")


def load_remote_config(path: str):
    with open(path, "r") as f:
        config = json.load(f)

    return config["serial_id"], bytes.fromhex(config["key"]), config.get("counter", 0)


def save_remote_config(path: str, serial_id: int, key: bytes, counter: int):
    config = {
        "serial_id": serial_id,
        "key": key.hex(),
        "counter": counter,
    }

    with open(path, "w") as f:
        json.dump(config, f, indent=4)


serial_id, key, counter = load_remote_config(REMOTE_CONFIG_PATH)
driver = CherubiniRemoteDriver(serial_id=serial_id, key=key, tx_pin=TX_PIN)


def on_connect(client: mqtt.Client, _u, _f, rc: int):
    if rc == 0:
        print("MQTT connected; subscribing:", MQTT_TOPIC)
        client.subscribe(MQTT_TOPIC, qos=1)
    else:
        print("MQTT connect failed rc=", rc)


def on_message(_c, _u, message):
    payload = (message.payload.decode() if message.payload else "").strip().upper()

    if payload not in ("UP", "DOWN", "STOP"):
        print("Ignoring:", repr(payload))
        return

    _, _, counter = load_remote_config(REMOTE_CONFIG_PATH)
    counter = (counter + 1) & 0xFFFF
    driver.command(payload, counter)
    save_remote_config(REMOTE_CONFIG_PATH, serial_id, key, counter)
    print("Sent command:", payload)


client = mqtt.Client(client_id=MQTT_CLIENT_ID)
if MQTT_USERNAME and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

client.on_connect = on_connect
client.on_message = on_message


try:
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    print(f"Listening for MQTT '{MQTT_TOPIC}' (UP/DOWN/STOP)")
    client.loop_forever()
except KeyboardInterrupt:
    pass
finally:
    try:
        client.disconnect()
    except Exception:
        pass
    driver.close()
