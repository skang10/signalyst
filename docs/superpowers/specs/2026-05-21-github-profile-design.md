# GitHub Profile README — Design Spec

**Date:** 2026-05-21
**Owner:** Xuemei (Simone) Jiang — github.com/simone-jiang

---

## Goal

Create a GitHub profile README that attracts ML Engineer recruiters and hiring managers. Optimized for signal over visual noise.

## Decisions

- **Approach:** Minimal & Sharp (no badge grids, no stats cards — one strong project, clean text)
- **Tagline style:** Personal and journey-oriented, not credential-listing
- **Audience:** Technical hiring managers at ML-focused companies

## Structure

### 1. Header
```
Hi, I'm Xuemei 👋
DS → ML → AI. Still following the signal.
```

### 2. About (2 sentences)
- Lead with research interest: multimodal learning across vision, language, and structured data
- Follow with craft: the full loop of reading papers, running experiments, shipping to production

### 3. Stack (inline code tags)
`Python` · `PyTorch` · `Computer Vision` · `Tabular AI` · `LLM Agents` · `TypeScript`

### 4. Featured Project
**⚡ TemporalAgent** — ReAct agent that detects oil market regime shifts using TabPFN for tabular classification, with live-streaming reasoning, derivatives pricing, and walk-forward backtesting.

### 5. Publications
- 📄 Less is More: Active Self-Supervised Learning in Remote Sensing — IGARSS 2024 (Oral)
- 📄 Self-Supervised Learning in Remote Sensing — IGARSS 2023 (Oral)

### 6. Footer
`🎓 PKU | HSG | UN · 🔍 Open to ML Engineer roles · ✉️ xuemei.jg@gmail.com`

---

## Rendering Target

Standard GitHub profile README (dark theme). No external image dependencies (no stats cards, no shields.io badges) — keeps the profile fast-loading and maintenance-free.

## Future Updates

When new projects are added, append them under Featured Project as a second pinned item. Publications section can grow in place.
