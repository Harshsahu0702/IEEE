# OmniSense AI — Engineering Integrity & Architectural Rules

## 1. Zero-Faking & Anti-Shortcut Policy
- **No Hardcoded Illusion Lists:** Never hardcode small dictionaries (e.g., `fast_objects_map = {"phone", "laptop", ...}`) or bounded integer lookups (`{"one": 1, ... "ten": 10}`) to create the illusion of universal capability.
- **True Generalization:** All object detection, parsing, and threshold evaluation must be generic, open-vocabulary, and dynamic for any input string or count.
- **Hardware Honesty:** Always report true execution latencies, CPU utilization, and hardware boundaries. Never hide bottlenecks behind synthetic fast-paths.

## 2. Model Tiering Standards
- **Tier 1 (Fast Open-Vocabulary Detector):** YOLO-World (`yolov8s-worldv2.pt` / INT8). Responsible for real-time (~30ms) open-vocabulary detection and spatial localization of any noun/object.
- **Tier 2 (Deep Semantic Reasoner):** VLM (Ollama Moondream or Cloud Gemini). Responsible for multi-agent reasoning, complex temporal actions, posture, gestures, and conditions that cannot be represented by a bounding box.

## 3. Real-Time Video & Overlay Standards
- **Live Labeling:** In standard monitoring mode, all detected objects in view must be rendered live with neat bounding boxes and category labels in calm cyan/green.
- **Alert Isolation:** When an alert condition is triggered, the offending object(s) must be distinctly highlighted in prominent RED with an ALERT badge, while suppressing or deemphasizing non-relevant boxes.
