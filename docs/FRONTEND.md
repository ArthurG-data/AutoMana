# Frontend Architecture

Complete guide to the AutoMana React application, including component patterns, state management, API integration, testing, and deployment.

> **Start here for system-wide understanding.** For the full system (frontend + backend), see [`docs/ARCHITECTURE_MASTER.md`](ARCHITECTURE_MASTER.md).

## Frontend Overview

The frontend is a React 18 single-page application (SPA) built with Vite, providing users with:
- Card collection management (add/remove/organize cards)
- Price tracking and analytics
- Integration with eBay and Shopify for inventory sync
- Search and filtering capabilities
- Responsive UI for desktop and mobile

### Tech Stack Rationale

**React 18** chosen for: component reusability, large ecosystem, strong typing with TypeScript, proven production stability. Alternatives (Vue, Angular, Svelte) considered but React's ecosystem and team experience won out.

**Vite** chosen for: 10x faster dev builds than Webpack, native ESM, instant HMR. Webpack remains the industry standard but Vite's DX is superior for this project.

**[State Library]** (TBD - to be discovered) chosen for: [rationale]. Alternatives considered: [list].

---

## Table of Contents

### Architecture & Patterns (Component, Routing, State)
- [Component Architecture & Design System](frontend/architecture/COMPONENTS.md)
- [Routing & Navigation](frontend/architecture/ROUTING.md)
- [State Management Architecture](frontend/architecture/STATE_MANAGEMENT.md)

### Integration & Data (APIs, Authentication)
- [API Integration & Data Fetching](frontend/integration/API_INTEGRATION.md)
- [Authentication & Authorization](frontend/integration/AUTHENTICATION.md)

### User Experience (Forms)
- [Forms & Validation](frontend/user-experience/FORMS.md)

### Quality & Deployment (Testing, Build)
- [Testing Strategy](frontend/quality-operations/TESTING.md)
- [Build, Deployment & Performance](frontend/quality-operations/BUILD_DEPLOYMENT.md)

---

## Architecture Diagram

[TO BE ADDED: Mermaid diagram showing Features → Components → Services → Store → API]

---

## Key Design Decisions Summary

| Decision | Rationale | Alternatives | Trade-offs |
|---|---|---|---|
| React 18 | Large ecosystem, strong typing, team experience | Vue, Angular, Svelte | Larger bundle size, steeper learning curve for new team members |
| Vite | 10x faster builds, native ESM, instant HMR | Webpack, Parcel | Smaller ecosystem, younger project |
| [State Library] | TBD | TBD | TBD |
| Feature-based folder structure | Collocate related code, easier to maintain features | Atomic/utility-based | Larger feature folders, more complex tree |

---

## Request/Data Lifecycle

[TO BE ADDED: Mermaid sequence diagram showing user action → component → store → API call → response → UI update]

---

## Component Hierarchy Overview

[TO BE ADDED: ASCII or Mermaid tree showing how components are nested]

---

## Feature Directory

| Feature | Location | Purpose | Entry Point |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

---

## Operational Considerations

### Performance Bottlenecks
- [TO BE DISCOVERED]

### Bundle Size Management
- [TO BE DISCOVERED]

### Runtime Performance
- [TO BE DISCOVERED]

---

## Quick Start for New Developers

1. Read [Component Architecture & Design System](frontend/architecture/COMPONENTS.md) to understand how components are organized
2. Read [Routing & Navigation](frontend/architecture/ROUTING.md) to understand how pages are navigated
3. Read [State Management Architecture](frontend/architecture/STATE_MANAGEMENT.md) to understand global state
4. Read [API Integration & Data Fetching](frontend/integration/API_INTEGRATION.md) to understand data flow
5. For authentication details, see [Authentication & Authorization](frontend/integration/AUTHENTICATION.md)
6. For forms, see [Forms & Validation](frontend/user-experience/FORMS.md)
7. For testing, see [Testing Strategy](frontend/quality-operations/TESTING.md)
8. For production, see [Build, Deployment & Performance](frontend/quality-operations/BUILD_DEPLOYMENT.md)
