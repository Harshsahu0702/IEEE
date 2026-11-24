# AGENT INSTRUCTION & WORKSPACE CONTEXT
Always consult [PROJECT_RULES.md](file:///d:/IEEE/PROJECT_RULES.md) before designing, modifying, or implementing any features in this workspace.

Strict principles:
1. Universal VLM + Motion Filter over scenario-specific plugins.
2. No folder sprawl (do not hardcode separate folders for exam, fall, fight, etc.).
3. Context-Adaptive UI: Frontend widgets & charts must dynamically adapt to the active monitoring context (e.g., person-count + temp graphs, risk gauges, accident alerts).
4. Preserve existing React UI, FastAPI WebSockets, and Arduino hardware bridge.
5. Keep answers concise, factual, and focused on core points.
