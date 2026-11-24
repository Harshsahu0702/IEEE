"""
OmniSense AI - Standalone Python MQTT Broker
Alternative to Docker Mosquitto for local development.
Runs an MQTT broker on localhost:1883 without Docker.
"""

import sys
import asyncio
import logging
from amqtt.broker import Broker

# Configure clean logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("OmniSenseBroker")

broker_config = {
    'listeners': {
        'default': {
            'type': 'tcp',
            'bind': '0.0.0.0:1883',
            'max_connections': 100,
        }
    },
    'sys_interval': 15,
    'auth': {
        'allow-anonymous': True,
        'plugins': ['auth_anonymous']
    }
}

async def run():
    print("=" * 65)
    print("  OMNISENSE AI — STANDALONE PYTHON MQTT BROKER")
    print("  Port: 1883 (TCP) | Host: localhost (0.0.0.0)")
    print("  Status: Listening for IoT devices and simulator")
    print("  (Press Ctrl+C to stop)")
    print("=" * 65)

    broker = Broker(broker_config)
    await broker.start()
    logger.info("MQTT Broker is active and ready on port 1883.")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await broker.shutdown()
        logger.info("MQTT Broker stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nBroker gracefully terminated by user.")
        sys.exit(0)
