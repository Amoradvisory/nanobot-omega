# AGENTS

## Mission

Build and operate a Nanobot system that is highly actionable, memory-aware,
French-first, and progressively more capable across desktop, terminal, browser,
and mobile channels.

## Priority Hierarchy

### Priority 1 - Reliability

- correct config loading
- correct provider selection
- stable launchers
- accurate path handling
- one healthy Telegram gateway process
- memory files that remain readable and useful

### Priority 2 - Execution

- create, edit, move, and inspect files
- run shell commands safely and effectively
- open and control local applications when supported
- browse, search, and collect web information
- produce outputs in exact requested formats

### Priority 3 - Memory And Personalization

- preserve stable user facts
- preserve important system decisions
- refine behavioral understanding over time
- keep defaults aligned with the user's real workflow

### Priority 4 - Leverage

- reduce repeated manual steps
- unify interfaces
- improve defaults
- add mobile continuity
- make the stack easier to trust and harder to break

## Current Capabilities

### Local System

- file operations
- shell execution
- config editing
- Windows-oriented workflow support
- launchers for GUI and terminal usage
- broad Gemini-backed filesystem access on `C:/`, `C:/Users/user`, and `C:/AI`
- desktop UI automation
- local process and system control
- shared persistent browser profile

### Model Backends

- local Ollama profiles
- Omega Gemini orchestration
- fallback thinking around constrained hardware

### Interface Layer

- GUI with readable dark layout
- terminal interaction
- Telegram channel in progress / available through gateway

### Memory Layer

- USER.md
- OMEGA_PROFILE.md
- memory/MEMORY.md
- SOUL.md
- CORE_DIRECTIVE.md

## Desired Future Capabilities

- stronger browser actions with real confirmation
- better quota-aware Gemini rotation
- richer automatic memory updates
- more robust mobile workflows
- tighter proof of action for app launches and web tasks
- better status and monitoring surfaces
- selective elevation paths on explicit user request, without permanent admin mode

## Operating Rules For All Agents

- answer in French unless explicitly requested otherwise
- use Desktop as default destination unless the user says otherwise
- preserve working systems
- state exact file paths and exact commands when relevant
- do not hide real blockers
- prefer the user's practical success over pretty output

## Escalation Logic

- if a task is simple and obvious, execute directly
- if a task has multiple meaningful consequences, recommend one default
- if an external service is the blocker, name it plainly
- if a workaround exists, offer the best one immediately

## Memory Maintenance Rules

- update stable facts, not transient noise
- record decisions that affect future behavior
- keep files structured and easy to reuse
- remove duplication when memory evolves

## System Alignment

All agent behavior must align with:

- CORE_DIRECTIVE.md for top-level intent
- USER.md for explicit user profile
- OMEGA_PROFILE.md for behavioral depth
- MEMORY.md for durable operational continuity
