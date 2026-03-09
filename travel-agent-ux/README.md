# travel-agent-ux

Lightweight mobile-first PWA for the Travel AI agent. Separate client from the Next.js desktop frontend — same FastAPI backend, optimized for phone screens.

**Stack:** Vite + React 19 + TypeScript — no SSR, no utility CSS framework, pure CSS custom properties.

## Getting Started

```bash
cp .env.example .env   # or set env vars directly
npm install
npm run dev            # → http://localhost:5173
```

Open `http://<LAN-IP>:5173` on your phone to test on device.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `` (empty = same origin) | Backend URL. Leave empty in dev — Vite proxy forwards `/api` to `localhost:8000`. |
| `VITE_AUTH_MODE` | — | Set to `mock` to skip Cognito and use localStorage mock auth. |

## Development

```bash
# Backend must be running (see travel-agent/)
cd ../travel-agent && docker compose up

# Then in this directory:
npm run dev
```

Mock auth signs you in instantly as `dev@localhost` — no Cognito setup required.

## Build & Preview

```bash
npm run build      # TypeScript check + Vite bundle → dist/
npm run preview    # Serve dist/ locally (tests PWA)
```

## Architecture

```
src/
├── main.tsx          # React root, SW registration
├── App.tsx           # State router: signin → trips → chat
├── types.ts          # Shared TypeScript types
├── index.css         # All styles — mobile-first, CSS custom properties
├── lib/
│   ├── api.ts        # fetch wrapper + streamChat() SSE generator
│   └── auth.ts       # Amplify Cognito / mock auth abstraction
├── screens/
│   ├── SignIn.tsx    # Full-screen Google sign-in
│   ├── TripList.tsx  # Trip cards + FAB to create trip
│   └── Chat.tsx      # Messages + input bar + itinerary sheet toggle
└── components/
    ├── Message.tsx         # Chat bubble with minimal markdown + trade-off options
    ├── TypingIndicator.tsx # Three-dot animation
    ├── ItinerarySheet.tsx  # Bottom sheet, swipe to dismiss
    └── AlertBanner.tsx     # Proactive alert strip (flight delays, leave-now)
```

## PWA

- `public/manifest.json` — name, icons, `display: standalone`
- `public/sw.js` — cache-first for app shell, network-first for `/api/*`
- Registered in `main.tsx` on page load

Add to home screen on iOS: Share → Add to Home Screen
Add to home screen on Android: browser menu → Install App

## Mobile UX Details

- `height: 100dvh` — handles iOS address bar shrink/expand
- `font-size: 16px` on textarea — prevents iOS auto-zoom
- `env(safe-area-inset-*)` — iPhone notch / home indicator padding
- `-webkit-overflow-scrolling: touch` — native momentum scroll
- Bottom sheet: CSS `translateY` transition + touch gesture dismiss (60px down swipe)
