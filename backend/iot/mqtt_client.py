import logging
import threading
import time
from typing import Optional
import paho.mqtt.client as mqtt

from backend.config import settings
from backend.iot.telemetry import telemetry_handler

logger = logging.getLogger(__name__)


class MQTTClientService:
    """
    Background MQTT client service.
    Features:
    - Auto-reconnecting background loop
    - Subscribes to telemetry and status topics
    - Username/password authentication support
    - Non-blocking execution; does not hang application if broker is unavailable
    """
    def __init__(self):
        self.host = settings.MQTT_BROKER_HOST
        self.port = settings.MQTT_BROKER_PORT
        self.keepalive = settings.MQTT_KEEPALIVE
        self.client_id = settings.MQTT_CLIENT_ID
        self.username = settings.MQTT_USERNAME
        self.password = settings.MQTT_PASSWORD

        self._client: Optional[mqtt.Client] = None
        self._is_connected = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the MQTT subscriber service in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MQTTClientServiceThread")
        self._thread.start()
        # Also start offline checker
        telemetry_handler.start_offline_checker(
            interval_sec=10,
            timeout_sec=settings.DEVICE_OFFLINE_TIMEOUT_SECONDS
        )
        logger.info(f"MQTT Client Service thread initialized for {self.host}:{self.port}")

    def _run_loop(self):
        """Manages client connection lifecycle with exponential retry backoff."""
        while self._running:
            try:
                # Initialize paho client (supports both paho v1 and v2 API versions)
                if hasattr(mqtt, "CallbackAPIVersion"):
                    self._client = mqtt.Client(
                        mqtt.CallbackAPIVersion.VERSION2,
                        client_id=self.client_id
                    )
                else:
                    self._client = mqtt.Client(client_id=self.client_id)

                # Set credentials if provided
                if self.username:
                    self._client.username_pw_set(self.username, self.password)

                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                self._client.on_message = self._on_message

                logger.info(f"Attempting connection to MQTT broker at {self.host}:{self.port}...")
                self._client.connect(self.host, self.port, keepalive=self.keepalive)
                self._client.loop_forever()
            except Exception as e:
                self._is_connected = False
                logger.warning(f"MQTT connection failed ({e}). Re-attempting in 5 seconds...")
                time.sleep(5.0)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback triggered upon establishing connection to MQTT broker."""
        # Handle both integer rc (v1) and ReasonCode object (v2)
        rc_code = rc.value if hasattr(rc, "value") else rc
        if rc_code == 0:
            self._is_connected = True
            logger.info("Connected to Mosquitto MQTT Broker successfully.")
            # Subscribe to topics
            client.subscribe(settings.MQTT_TOPIC_TELEMETRY, qos=1)
            client.subscribe(settings.MQTT_TOPIC_STATUS, qos=1)
            logger.info(f"Subscribed to: {settings.MQTT_TOPIC_TELEMETRY} and {settings.MQTT_TOPIC_STATUS}")
        else:
            self._is_connected = False
            logger.error(f"MQTT Connection refused with result code: {rc_code}")

    def _on_disconnect(self, client, userdata, flags=None, rc=None, properties=None):
        self._is_connected = False
        logger.warning(f"Disconnected from MQTT broker (rc={rc}). Will auto-reconnect...")

    def _on_message(self, client, userdata, msg):
        """Callback on receiving an incoming MQTT message."""
        topic = msg.topic
        payload = msg.payload
        try:
            if "/telemetry" in topic:
                telemetry_handler.handle_raw_telemetry(payload, topic=topic)
            elif "/status" in topic:
                telemetry_handler.handle_raw_status(payload, topic=topic)
        except Exception as e:
            logger.error(f"Error handling MQTT message on topic {topic}: {e}")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def publish_alarm(self, payload: dict, topic: str = "omnisense/alerts/alarm"):
        """Publish alarm trigger to MQTT so physical actuators & Arduino devices react."""
        if self._client and self._is_connected:
            try:
                import json
                self._client.publish(topic, json.dumps(payload), qos=1)
                logger.info(f"Published alarm command to MQTT topic {topic}")
            except Exception as e:
                logger.warning(f"Failed to publish alarm to MQTT: {e}")

    def stop(self):
        """Stops the MQTT client service."""
        self._running = False
        telemetry_handler.stop_offline_checker()
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
        logger.info("MQTT Client Service stopped.")


mqtt_service = MQTTClientService()
