# BB FM Kigali — Radio + VOD Mobile App

## Overview
Cross-platform (iOS/Android/Web via Expo Router) app for BB FM Kigali radio station.
Users can listen to live radio, watch on-demand videos, listen to podcasts, read news,
and subscribe to premium tiers.

## Features (MVP)
1. **Phone OTP Authentication** — mock code `123456` (Twilio integration planned)
2. **Live Radio Streaming** — with persistent glass mini-player above tab bar & full player modal
3. **Shows (VOD + Podcasts + Interviews)** — 2-column grid, category chip filter (sticky), premium gating
4. **News feed** — cards with expandable body
5. **Profile & Subscription Management** — tier badge, payment history, sign out
6. **Subscription Paywall** — Basic (1,000 RWF/mo, 10,000 RWF/yr) & Premium (3,000 RWF/mo, 30,000 RWF/yr)
7. **Multi-payment Checkout** — PayPal (LIVE, EUR) + MTN MoMo via BeSoft (LIVE, RWF); Stripe/Airtel currently mocked
8. **Admin Panel** — Programs, VOD/Podcast library, Live URLs & Branding, and **Categories (unlimited, admin-managed)** — added Aug 2026

## Stack
- **Frontend**: Expo SDK 54, expo-router, expo-audio (live radio), react-native-webview (VOD), expo-blur (glass mini-player), react-native-reanimated (wave animation), Barlow Condensed via @fontsource CDN.
- **Backend**: FastAPI + Motor (async MongoDB), PyJWT, mock OTP + mock payment flows.
- **DB**: MongoDB collections — users, otp_challenges, shows, news, schedule, radio_state, payments.

## Design
Dark-First Utility personality. Amber/rust `#FF6B00` on obsidian `#0F0F13`. See `/app/design_guidelines.json`.

## Mocked / Not Real
- **Phone OTP** — universal code `123456`. Replace `/api/auth/otp/*` handlers to plug Twilio.
- **All payment providers** — Stripe/PayPal/MoMo/Airtel routed through `/api/billing/subscribe` and instantly return success. Replace with real gateways per playbook.
- **Live stream URL** — demo Zeno.fm URL `https://stream.zeno.fm/0r0xa792kwzuv`.
- **VOD videos** — YouTube embed URLs seeded (rickroll etc.). Admin panel not yet implemented; videos are seeded on backend startup.

## Business Enhancement Idea
Add a **"Send a Shoutout"** paid feature (small in-app payment) — listeners pay 500 RWF via MoMo to have their message read on air. Perfect revenue stream leveraging Rwanda's high MoMo adoption.
