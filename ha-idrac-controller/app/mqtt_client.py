# HA-iDRAC/ha-idrac-controller/app/mqtt_client.py
import paho.mqtt.client as mqtt
import os
import time
import json
import re # For sanitizing fan names
import uuid


def build_unique_client_id(base_id):
    """Two add-on instances sharing an MQTT client id get kicked off the broker in a loop."""
    host = re.sub(r'[^a-zA-Z0-9_-]+', '', os.getenv("HOSTNAME", ""))[-24:]
    parts = [base_id]
    if host:
        parts.append(host)
    parts.append(uuid.uuid4().hex[:8])
    return "_".join(parts)


class MqttClient:
    def __init__(self, client_id="ha_idrac_controller"):
        self.client_id = build_unique_client_id(client_id)
        self.client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311)
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)
        self.broker_address = "core-mosquitto" # Default, will be overridden by main.py
        self.port = 1883
        self.username = ""
        self.password = ""
        self.is_connected = False
        self.device_info_dict = None # This will be set by main.py after server_info is fetched
        self.availability_topic = "ha_idrac_controller/status" # Re-scoped per device in set_device_info
        self.log_level = "info" # Default, can be updated from main.py

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    def _log(self, level, message):
        levels = {"trace": -1, "debug": 0, "info": 1, "warning": 2, "error": 3, "fatal": 4}
        if levels.get(self.log_level, levels["info"]) <= levels.get(level.lower(), levels["info"]):
            print(f"[{level.upper()}] MQTT ({self.client_id}): {message}", flush=True)

    def configure_broker(self, host, port, username, password, log_level="info"):
        self.broker_address = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.log_level = log_level.lower()
        if self.username: # Only set if username is actually provided
            self.client.username_pw_set(self.username, self.password)

    def set_device_info(self, manufacturer, model, ip_address):
        sanitized_ip = ip_address.replace('.', '_') if ip_address else "default_ip"
        self.device_info_dict = {
            "identifiers": [f"idrac_controller_{sanitized_ip}_device"],
            "name": f"iDRAC Controller ({ip_address or 'N/A'})",
            "model": model or "HA iDRAC Controller",
            "manufacturer": manufacturer or "HA Add-on" # Changed from Aesgarth for generality
        }
        self.availability_topic = f"ha_idrac_controller/{self.device_info_dict['identifiers'][0]}/status"
        self._log("info", f"Device info for MQTT discovery set to: {self.device_info_dict}")


    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._log("info", f"Connected successfully to broker {self.broker_address}:{self.port}")
            self.is_connected = True
            
            # Publish general add-on availability status sensor
            if self.device_info_dict:
                status_config_topic = f"homeassistant/binary_sensor/idrac_controller_{self.device_info_dict['identifiers'][0]}/status/config"
                status_config_payload = {
                    "name": "iDRAC Controller Connectivity",
                    "state_topic": self.availability_topic,
                    "unique_id": f"idrac_controller_{self.device_info_dict['identifiers'][0]}_connectivity",
                    "device_class": "connectivity",
                    "payload_on": "online",
                    "payload_off": "offline",
                    "device": self.device_info_dict
                }
                self.publish(status_config_topic, json.dumps(status_config_payload), retain=True)
            self.publish(self.availability_topic, "online", retain=True)

            # Static sensor discoveries (non-CPU, non-FanRPM which are dynamic)
            self.publish_static_sensor_discoveries()
        else:
            self._log("error", f"Connection failed with code {rc}")
            self.is_connected = False

    def on_disconnect(self, client, userdata, rc):
        self._log("info", f"Disconnected from broker with result code {rc}.")
        self.is_connected = False

    def connect(self):
        if not self.is_connected:
            self._log("info", f"Attempting to connect to broker {self.broker_address}:{self.port}...")
            try:
                self.client.will_set(self.availability_topic, payload="offline", qos=1, retain=True)
                self.client.connect(self.broker_address, self.port, 60)
                self.client.loop_start() 
            except ConnectionRefusedError:
                self._log("error", f"Connection refused by broker {self.broker_address}:{self.port}.")
            except OSError as e:
                self._log("error", f"OS error connecting to broker {self.broker_address}:{self.port} - {e}")
            except Exception as e:
                self._log("error", f"Could not connect to broker: {e}")

    def disconnect(self):
        if self.is_connected:
            # LWT should handle setting status to offline
            # self.publish("ha_idrac_controller/status", "offline", retain=True) 
            self.client.loop_stop()
            self.client.disconnect()
            self._log("info", "Gracefully disconnected.")
            self.is_connected = False


    def publish(self, topic, payload, retain=False, qos=0):
        if self.is_connected:
            try:
                # self._log("trace", f"Publishing to {topic}: {payload}")
                msg_info = self.client.publish(topic, payload, qos=qos, retain=retain)
                if msg_info.rc != mqtt.MQTT_ERR_SUCCESS:
                    self._log("warning", f"Failed to enqueue message for topic {topic}. Error code: {msg_info.rc}")
                return msg_info.is_published()
            except Exception as e:
                self._log("error", f"Failed to publish to {topic}: {e}")
        else:
            self._log("warning", f"Not connected. Cannot publish to {topic}.")
        return False

    def publish_sensor_discovery(self, sensor_type_slug, sensor_name, 
                                 device_class=None, unit_of_measurement=None, 
                                 icon=None, value_template=None, 
                                 entity_category=None, unique_id_suffix=None,
                                 state_class=None): # <<< ADD state_class=None HERE
        if not self.device_info_dict:
            self._log("warning", f"Device info not set. Cannot publish discovery for {sensor_name}.")
            return

        base_unique_id = f"{self.device_info_dict['identifiers'][0]}_{sensor_type_slug}"
        if unique_id_suffix: 
            base_unique_id = f"{base_unique_id}_{unique_id_suffix}"

        # Use a consistent node_id for all sensors of this device to group them under the device in MQTT integration
        node_id_for_topic = self.device_info_dict['identifiers'][0] 
        # Sanitize slug further if needed, but usually identifier is okay
        config_topic_slug_part = f"{sensor_type_slug}{(unique_id_suffix if unique_id_suffix else '')}"
        
        config_topic = f"homeassistant/sensor/{node_id_for_topic}/{config_topic_slug_part}/config"
        state_topic_base = f"ha_idrac_controller/sensor/{node_id_for_topic}" # Base for all sensor states of this device
        
        payload = {
            "name": f"{sensor_name}", 
            "state_topic": f"{state_topic_base}/{config_topic_slug_part}/state",
            "unique_id": base_unique_id,
            "device": self.device_info_dict,
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline"
        }
        if device_class: payload["device_class"] = device_class
        if unit_of_measurement: payload["unit_of_measurement"] = unit_of_measurement
        if icon: payload["icon"] = icon
        if value_template: payload["value_template"] = value_template
        if entity_category: payload["entity_category"] = entity_category
        if state_class: payload["state_class"] = state_class # <<< ADD THIS LINE TO INCLUDE IT IN PAYLOAD

        self.publish(config_topic, json.dumps(payload), retain=True)
        self._log("debug", f"Published discovery for '{sensor_name}' (unique_id: {base_unique_id}) on topic {config_topic}")



    def publish_static_sensor_discoveries(self):
        """Publishes discovery for sensors that are always present or have fixed names."""
        if not self.is_connected or not self.device_info_dict:
            self._log("warning", "MQTT not connected or device_info not set, skipping static discoveries.")
            return
        
        self._log("info", "Publishing static sensor discovery messages...")
        # Inlet Temp
        self.publish_sensor_discovery(
            sensor_type_slug="inlet_temp", sensor_name="Inlet Temperature",
            device_class="temperature", unit_of_measurement="°C",
            value_template="{{ value_json.temperature | round(1) }}"
        )
        # Exhaust Temp
        self.publish_sensor_discovery(
            sensor_type_slug="exhaust_temp", sensor_name="Exhaust Temperature",
            device_class="temperature", unit_of_measurement="°C",
            value_template="{{ value_json.temperature | round(1) }}"
        )
        # Target Fan Speed
        self.publish_sensor_discovery(
            sensor_type_slug="target_fan_speed", sensor_name="Target Fan Speed",
            unit_of_measurement="%", icon="mdi:fan-chevron-up",
            value_template="{{ value_json.speed if value_json.speed is not none else 'Auto' }}"
        )
        # Hottest CPU Temp
        self.publish_sensor_discovery(
            sensor_type_slug="hottest_cpu_temp", sensor_name="Hottest CPU Temp",
            device_class="temperature", unit_of_measurement="°C",
            value_template="{{ value_json.temperature | round(1) }}"
        )
        # Power Consumption (NEW)
        self.publish_sensor_discovery(
            sensor_type_slug="power_consumption", sensor_name="Power Consumption",
            device_class="power", unit_of_measurement="W",
            state_class="measurement", # For power sensors representing current consumption
            icon="mdi:flash",
            value_template="{{ value_json.power | round(0) }}"
        )


    def publish_sensor_state(self, sensor_type_slug, value_dict, unique_id_suffix=None):
        if not self.device_info_dict:
            self._log("warning", "Device info not set. Cannot publish sensor state.")
            return

        state_topic_base = f"ha_idrac_controller/sensor/{self.device_info_dict['identifiers'][0]}"
        state_topic = f"{state_topic_base}/{sensor_type_slug}{(unique_id_suffix if unique_id_suffix else '')}/state"
        self.publish(state_topic, json.dumps(value_dict))