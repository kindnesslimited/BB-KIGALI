# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 27)
1. **Direct Video Upload — FIXED**. Backend `/api/admin/uploads/video` now:
   - Accepts extensions: mp4, m4v, mov, qt, webm, mkv, avi, 3gp, 3g2, hevc
   - Accepts MIME types: video/mp4, video/quicktime (iOS!), video/webm, video/x-matroska, video/x-msvideo, video/3gpp, video/mpeg, video/x-m4v, application/octet-stream (Android fallback)
   - Server-side **magic-byte sniffing** (ftyp/EBML/RIFF-AVI) → validates real file type regardless of what the client claims
   - Returns clear error message with the filename + received MIME when unsupported
   - Prefers sniffed content type over client-declared type for the final storage record
2. **Schedule on Home + richer admin schedule**
   - Backend `ScheduleIn` extended with `coverImage` + `status` ("on-air" | "upcoming" | "off-air")
   - Admin `/admin/schedule` page adds cover image picker + status chip selector; list rows show thumbnail
   - Home page TODAY'S SCHEDULE renders admin-managed items with image background + gradient + **LIVE NOW** badge; admins see a "Manage" link; empty state message when no slots
3. Google Cloud hosting/backup and Apple TestFlight questions routed to Emergent support (see support_agent response inline in chat).

## Prior updates (iter 26)
- iOS Store readiness (privacy manifests)
- Dedicated full-screen VOD checkout modal
- News: external source (publication + URL) + coverUrl↔thumbnail mirroring
- Admin Schedule CRUD created
- Web/Desktop responsive layout (maxWidth 1200) + How Our App Works / Need Help sections

## Test credentials
See `/app/memory/test_credentials.md`.
