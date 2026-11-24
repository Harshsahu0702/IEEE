import logging
import bcrypt
from datetime import datetime
from sqlalchemy import text
from backend.database.connection import Base, engine, SessionLocal
from backend.database.models import User, Device, MonitoringProfile

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def init_database():
    """Create tables and initialize baseline seed data."""
    logger.info("Creating database tables if not present...")
    Base.metadata.create_all(bind=engine)

    # Safe lightweight schema migration for existing SQLite DBs
    try:
        with engine.connect() as conn:
            cursor = conn.execute(text("PRAGMA table_info(devices)"))
            cols = [row[1] for row in cursor.fetchall()]
            if cols and "approval_status" not in cols:
                conn.execute(text("ALTER TABLE devices ADD COLUMN approval_status VARCHAR(32) DEFAULT 'approved'"))
                conn.commit()
                logger.info("Migrated devices table: added approval_status column.")
    except Exception as e:
        logger.warning(f"Schema migration note: {e}")

    db = SessionLocal()
    try:
        # 1. Seed Admin User
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@omnisense.local",
                hashed_password=hash_password("admin123"),
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            logger.info("Created default administrator: admin / admin123")

        # 2. Seed Default IoT Device
        default_device = db.query(Device).filter(Device.device_id == "env-sensor-01").first()
        if not default_device:
            default_device = Device(
                device_id="env-sensor-01",
                name="Environment Station Alpha (DHT22 + MQ2 + PIR)",
                device_type="environment",
                location="Main Facility Area",
                status="online",
                approval_status="approved",
                last_seen=datetime.utcnow(),
                config={
                    "temp_threshold": 32.0,
                    "humidity_max": 75.0,
                    "gas_threshold": 400.0
                }
            )
            db.add(default_device)
            logger.info("Created default device: env-sensor-01")

        # 3. Seed Default Camera Device
        default_cam = db.query(Device).filter(Device.device_id == "webcam_0").first()
        if not default_cam:
            default_cam = Device(
                device_id="webcam_0",
                name="Primary Optical Sensor (Webcam)",
                device_type="camera",
                location="Entry Lobby",
                status="online",
                approval_status="approved",
                last_seen=datetime.utcnow(),
                config={
                    "resolution": "640x480",
                    "fps": 15,
                    "person_threshold": 4
                }
            )
            db.add(default_cam)
            logger.info("Created default camera device: webcam_0")

        # 4. Seed Builtin Monitoring Profiles
        builtin_profiles = [
            {
                "name": "Crowd Safety Mode",
                "description": "Monitors high-density pedestrian gathering, spatial occupancy, and overcrowding conditions.",
                "domain": "vision",
                "modules": ["crowd_monitoring"],
                "source": "webcam_0",
                "rules": {
                    "person_threshold": 4,
                    "density_low_max": 2,
                    "density_medium_max": 5,
                    "cooldown_seconds": 30.0,
                    "confidence_threshold": 0.35
                },
                "duration_minutes": 60,
                "is_builtin": True
            },
            {
                "name": "Fire & Hazard Detection Mode",
                "description": "Continuous environmental watchdog for elevated temperature, combustible gas leakage, and smoke risks.",
                "domain": "iot",
                "modules": ["environment_monitoring"],
                "source": "env-sensor-01",
                "rules": {
                    "temp_threshold": 35.0,
                    "gas_threshold": 400.0,
                    "humidity_max": 80.0,
                    "cooldown_seconds": 30.0
                },
                "duration_minutes": 120,
                "is_builtin": True
            },
            {
                "name": "Restricted Area Mode",
                "description": "Surveillance of critical physical perimeter zones for unauthorized human intrusion.",
                "domain": "vision",
                "modules": ["security_monitoring"],
                "source": "webcam_0",
                "rules": {
                    "zones": [
                        {
                            "name": "Perimeter Zone A",
                            "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
                        }
                    ],
                    "cooldown_seconds": 20.0,
                    "confidence_threshold": 0.35
                },
                "duration_minutes": 60,
                "is_builtin": True
            }
        ]

        for p_data in builtin_profiles:
            existing = db.query(MonitoringProfile).filter(MonitoringProfile.name == p_data["name"]).first()
            if not existing:
                profile = MonitoringProfile(**p_data)
                db.add(profile)
                logger.info(f"Seeded profile: {p_data['name']}")

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()
    print("Database initialization complete.")
