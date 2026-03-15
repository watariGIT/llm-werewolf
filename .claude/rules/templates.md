---
globs: src/llm_werewolf/templates/**
---

# Template / UI Rules

- Use Jinja2 templates
- Maintain consistent design theme:
  - Background: `linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%)` with `background-attachment: fixed`
  - Text: `#e0e0e0`
  - Buttons: `#e94560`
  - Fonts: `Noto Sans JP` (body), `Noto Serif JP` (headings) via Google Fonts
  - Panels: glassmorphism (`background: rgba(22, 33, 62, 0.7)`, `backdrop-filter: blur(10px)`, `border: 1px solid rgba(255, 255, 255, 0.08)`)
