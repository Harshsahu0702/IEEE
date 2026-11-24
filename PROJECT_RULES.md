# PROJECT VISION & SYSTEM RULES (GROUND TRUTH)

> **MANDATORY INSTRUCTION FOR ASSISTANT / AGENT:**
> You MUST read and adhere to this file before designing, writing, or modifying any code in this repository. NEVER deviate from the principles defined here unless explicitly instructed by the user.

---

## 1. Core Vision & Purpose
This project is evolving from a rigid, hardcoded vision system into an **Autonomous, Universal Monitoring Platform**.
The user should be able to specify **ANY real-world monitoring scenario** in natural language (e.g., student cheating in exams, elderly fall detection, kitchen hazard, classroom disruption, domestic altercation, etc.), and the system must dynamically understand and monitor it **without requiring hardcoded plugin folders for every scenario**.

---

## 2. Architectural Pillars

### A. The Hybrid Vision-Language Intelligence (VLM) Architecture
1. **Lightweight Local Motion / Activity Filter**:
   - Runs locally at minimal compute (CPU/GPU).
   - Only triggers deeper analysis when meaningful frame delta/motion occurs (saving compute and API bandwidth).
2. **Cognitive VLM Reasoner (Vision-Language Model)**:
   - Evaluates the captured scene against the user's natural language goal.
   - Replaces the need for separate hardcoded detection folders (`crowd/`, `security/`, `threat/`).
   - Returns structured decisions: `{ incident_detected: bool, confidence: float, explanation: str, action_required: str }`.

### B. What Remains Intact & How It Adapts
- **Frontend SOC Dashboard** (`frontend/`): React, Tailwind, WebSockets, live MJPEG player, incident review drawers.
  - **Context-Adaptive Dynamic UI (Mandatory)**: Dashboard widgets and charts must NOT be static. The UI must dynamically adapt based on the active monitoring task:
    - *People + Temperature task*: Renders Time-Series chart for Person Count + Line chart for Arduino Temp.
    - *Exam Cheating task*: Renders Cheating Risk Gauge + Incident snapshot timeline.
    - *Home / Accident task*: Renders Status Indicator (Safe / Fall Detected) + Gas/Smoke levels.
- **Backend Infrastructure** (`backend/api/`, `backend/database/`): SQLite models, WebSocket broadcasting, JWT auth, evidence archiving.
- **Physical IoT & Edge Layer** (`backend/iot/`, `firmware/`): Real Arduino USB Serial bridge (`run_arduino_bridge.py`), environmental sensors (DHT22, MQ-2, PIR), hardware strobe/buzzer alarms.

### C. What to Deprecate / Replace
- Deprecate rigid rule-based monitoring folders (`backend/monitoring/crowd`, `backend/monitoring/security`, `backend/monitoring/threat`).
- Replace them with a single **Universal VLM Reasoning Monitor** that handles arbitrary user prompts.

---

## 3. Strict Development Guidelines & Rules for the Assistant

1. **No Scenario Sprawl**:
   - NEVER create individual folders or rule files for specific human scenarios (e.g., do NOT create `exam_monitor/`, `fall_monitor/`, `fight_monitor/`).
   - Implement the **Universal VLM Reasoner** that handles all such cases through contextual prompts.

2. **Always Keep Responses Concise & Grounded**:
   - The user prefers straightforward, focused answers that highlight main points without unnecessary fluff.
   - Do not hallucinate capabilities or overcomplicate solutions.

3. **Human-in-the-Loop Safeguards**:
   - Maintain the principle that alerts start as `pending_review` with visual evidence snapshots saved to `evidence/`.

4. **Hardware & Edge Awareness**:
   - Maintain compatibility with local webcams and the **Arduino UNO Q / standard Arduino** USB bridge on `COM5`.
