#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Iter 23 (June 2026): (1) News admin CRUD w/ cover images. (2) Bulk user invite (paste CSV). (3) User edit — role, tier, name, phone/email. (4) Subscription expiry reminder scheduler (auto every 12h + manual). (5) Add B&B Sports Bar YouTube channel (@BBSPORTSBAR) as a second content source alongside @bbkigalifm."

backend:
  - task: "Multi-channel YouTube sync (@bbkigalifm + @BBSPORTSBAR)"
    implemented: true
    working: true
    file: "/app/backend/youtube_sync.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "Iter 23: POST /admin/youtube/sync returns { ok:true, channels:[...] } with both channels, each upserted=50. New category 'bbsportsbar-youtube' auto-created. Shows queryable by category. GET /admin/youtube/status returns per-channel status."

  - task: "Admin News CRUD"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "POST/PATCH/DELETE /api/admin/news all work; non-admin gets 403 on writes."

  - task: "Bulk invite + user edit"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "POST /admin/users/bulk-invite idempotent (create-then-update), skips empty rows, admin-only. PATCH /admin/users/{id} supports displayName, phone, email, role, tier, active; self-demote blocked with 400."

  - task: "Subscription expiry reminder scheduler"
    implemented: true
    working: true
    file: "/app/backend/subscription_reminders.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "Background loop runs every 12h. POST /admin/subscriptions/send-reminders triggers a manual pass. Dedup verified — same user+expiry never gets a second SMS. Reminder targets are subscriptionExpiresAt = now+3 days and now+1 day."

frontend:
  - task: "Admin News page + Bulk-invite modal + multi-channel sync UI"
    implemented: true
    working: true
    file: "/app/frontend/app/admin/news.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "All new admin surfaces render and function on mobile web (390×844). /admin has 8 cards inc. News. /admin/news creates/edits/deletes posts w/ cover image picker. /admin/users has bulk-invite icon that opens a textarea modal with role toggle. /admin/shows shows both @bbkigalifm + @BBSPORTSBAR status lines and SYNC ALL NOW button."

metadata:
  created_by: "main_agent"
  version: "1.4"
  test_sequence: 23
  run_ui: true

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Iter 23 shipped: Multi-channel YouTube (@bbkigalifm + @BBSPORTSBAR imported 50 videos each), full Admin News CRUD, Bulk invite CSV modal, User edit endpoint, Subscription expiry reminders (auto every 12h + manual admin trigger). Backend 30/30 pytest green, frontend Playwright green."

# ---------- Previous iteration (iter 22) ----------
prev_iter22:

backend:
  - task: "MoMo /public/payments/transfer (debit-only)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "Iter 21: 16/16 tests pass. HTTP 201 Created from BeSoft on both subscription and VOD flows. X-API-Key + X-API-Secret headers present. besoftAttempt='transfer' persisted. Safety guard still blocks merchant number in all 4 normalization variants."

  - task: "Privacy Policy served from backend"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "GET /api/privacy returns 200 text/html with the full policy body. Reachable at https://radio-vod-platform.preview.emergentagent.com/api/privacy."

frontend:
  - task: "Privacy Policy accessible in-app"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/profile.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Profile → Settings → Privacy Policy row and the 'By continuing you accept … Privacy Policy' link on the phone entry screen both open ${EXPO_PUBLIC_BACKEND_URL}/api/privacy via Linking. No third-party hosting required to work in the app."

metadata:
  created_by: "main_agent"
  version: "1.3"
  test_sequence: 21
  run_ui: true

test_plan:
  current_focus: ["Privacy Policy accessible in-app"]
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Iter 21 shipped: MoMo back on /public/payments/transfer (debit-only payload, BeSoft 201). Privacy served at /api/privacy from FastAPI so the in-app link works with no external hosting. Phone entry screen now has a tap-through Privacy Policy link in the acknowledgement footer for App Store review."

# ---------- Previous iteration ----------
previous_iter20:

backend:
  - task: "MoMo /debit-credit for subscription + VOD"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "22/22 backend tests pass in iter 19. /billing/momo/initiate and /billing/vod/{id}/momo now correctly POST to /public/payments/debit-credit, credit amount == debit amount, credit payee = BESOFT_PAYOUT_MSISDN (250798875274). Safety guard blocks merchant number in all 3 normalization variants (canonical, +250 spaces, 0-prefix). besoftAttempt='debit_credit' persisted."

  - task: "YouTube Data API v3 sync from @bbkigalifm"
    implemented: true
    working: true
    file: "/app/backend/youtube_sync.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "Admin POST /api/admin/youtube/sync returns { ok:true, channelTitle:'B&B Kigali 89.7FM', upserted:50 }. Non-admin returns 403. GET /api/admin/youtube/status returns last sync metadata. Background asyncio task runs on startup + every 6h."
      - working: true
        agent: "main"
        comment: "Follow-up fix: youtube_sync.py now also writes `category` (slug), `thumbnail`, and formatted `duration` (H:MM:SS) so the /(tabs)/shows.tsx list renders without crashing. Verified — Shows tab loads with 50 YouTube videos categorized under 'BB Kigali on YouTube'."

  - task: "Sign in with Apple backend"
    implemented: true
    working: true
    file: "/app/backend/apple_auth.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "POST /api/auth/apple with an invalid identity token returns 401 (JWKS verification runs). Full real-token flow requires a physical iOS device but the endpoint schema and error handling are correct."

  - task: "Delete Account endpoint"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "DELETE /api/auth/me returns 200 { ok:true }, user + user_sessions + otp_challenges purged. Payments/vod_purchases anonymised (userId prefixed 'deleted-', phone → null, deletedAt set). Unauthenticated returns 401."

  - task: "Additional admin phones"
    implemented: true
    working: true
    file: "/app/backend/.env"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Added 25078844524 and 250788316999 to ADMIN_PHONES. Any user verifying OTP with those numbers is auto-promoted to role='admin'."

frontend:
  - task: "MoMo retry button on failure (checkout + VOD)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/checkout.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Checkout: shown below the error message when method=='mtn_momo' and !loading (testID='momo-retry-btn'). VOD unlock modal: shown below the error inside the MoMo phone entry state (testID='momo-retry-btn'). Both call the same pay/buyVodMomo function which re-uses the entered phone."

  - task: "Sign in with Apple button (iOS only)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/auth/phone.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Black 'Continue with Apple' button rendered below the Google button ONLY on Platform.OS==='ios'. Uses expo-apple-authentication.signInAsync with FULL_NAME + EMAIL scopes. Cancel is handled silently (ERR_REQUEST_CANCELED). App.json now has usesAppleSignIn:true and expo-apple-authentication plugin."

  - task: "Delete Account + Privacy Policy in Profile"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/profile.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Under Profile → Settings: 'Privacy Policy' row opens https://bbkigali.com/privacy via Linking. 'Delete Account' row triggers a two-step confirmation Alert (both dialogs destructive), then calls DELETE /api/auth/me and clears the local token."

  - task: "Admin YouTube 'Sync Now' button"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/admin/shows.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Red 'SYNC NOW' button at the top of admin/shows page with @BBKIGALIFM label. Shows last sync timestamp from /api/admin/youtube/status. Success Alert reports channel title + upsert count."

  - task: "Shows tab crash fix"
    implemented: true
    working: true
    file: "/app/frontend/app/(tabs)/shows.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Root cause of red-screen: newly-synced YouTube shows had no `category` slug field. Two fixes applied: (a) youtube_sync.py now populates `category: 'bbkigali-youtube'`. (b) Defensive `(item.category || 'SHOW').toUpperCase()` in the shows card. Verified via web preview — Shows tab lists all 50 YouTube videos with proper thumbnails and durations."

metadata:
  created_by: "main_agent"
  version: "1.2"
  test_sequence: 20
  run_ui: true

test_plan:
  current_focus:
    - "MoMo retry button on failure (checkout + VOD)"
    - "Sign in with Apple button (iOS only)"
    - "Delete Account + Privacy Policy in Profile"
    - "Admin YouTube 'Sync Now' button"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Iter 20 shipped: MoMo /debit-credit + retry, YouTube sync (@bbkigalifm channel), Sign in with Apple, Delete Account, Privacy Policy link. Backend was tested 22/22 in iter 19. Fixed the Shows-tab red-screen by adding category/duration fields in youtube_sync.py and defensive fallback in shows.tsx. Awaiting frontend re-test for retry button + delete account UI flow. Native Sign in with Apple requires a real iOS device to fully test."


# ---------- Previous session history ----------
previous_agent_communication:

backend:
  - task: "MTN MoMo VOD unlock via /public/payments/transfer collection API"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Migrated /billing/vod/{show_id}/momo from legacy /public/payments/debit-credit to the new /public/payments/transfer collection API. Payload is now flat (idempotency_key, amount, currency, payment_method='mtn_momo_collection', payer_identifier, description, country, metadata, callback_url) and BeSoft auto-settles to BESOFT_PAYOUT_MSISDN (250798875274) which is configured on the merchant profile. Safety guard _guard_payer_not_merchant() still runs before every call. Failure responses now include failureReason. Subscription MoMo /billing/momo/initiate was already on /transfer."

  - task: "PayPal subscription — no shipping, guest-friendly"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Updated /billing/paypal/create-subscription payload with application_context.shipping_preference=NO_SHIPPING and payment_method.payer_selected=PAYPAL / payee_preferred=UNRESTRICTED. Buyer no longer asked for shipping address on the PayPal Subscribe flow."

  - task: "PayPal VOD one-time — guest-friendly card-first"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Changed VOD PayPal order landing_page from NO_PREFERENCE to BILLING so users without a PayPal account see the card/guest form first. Added payment_method.payer_selected=PAYPAL. NO_SHIPPING was already set."

  - task: "MoMo safety guard — merchant number cannot be debited"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Regression check: BESOFT_PAYOUT_MSISDN is now 250798875274 (updated in .env). _guard_payer_not_merchant() must still return HTTP 400 if a customer enters 250798875274 as their payer number. Test both /billing/momo/initiate (subscription) and /billing/vod/{show_id}/momo (VOD). Test payer 250794230137 should succeed at the request-acceptance level (pending status)."

frontend:
  - task: "Stripe / PayPal WebView keyboard stability on mobile"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/checkout.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Root cause of the white-screen bug: the payment Modal opens a separate view hierarchy on iOS/Android and the WebView inside did not have explicit flex:1 style, so when the on-screen keyboard opened (Android adjustResize) the WebView height collapsed to 0 and rendered a blank/white page. Fix: (a) wrapped both Stripe and PayPal Modal contents in KeyboardAvoidingView (padding on iOS), (b) added explicit style={{flex:1}} and containerStyle={{flex:1}} to WebView, (c) set softwareKeyboardLayoutMode='pan' in app.json Android config, (d) added contentInsetAdjustmentBehavior='never' + automaticallyAdjustContentInsets=false + androidLayerType='hardware' for stable rendering. Same fix applied to video/[id].tsx modal (PayPal + Stripe VOD checkout). NOTE: Native soft-keyboard behavior can only be verified on a real device or emulator — Playwright web preview renders WebView as iframe and doesn't reproduce the bug. Requires user validation on iOS/Android device."

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 15
  run_ui: true

test_plan:
  current_focus:
    - "MTN MoMo VOD unlock via /public/payments/transfer collection API"
    - "PayPal subscription — no shipping, guest-friendly"
    - "PayPal VOD one-time — guest-friendly card-first"
    - "MoMo safety guard — merchant number cannot be debited"
    - "Stripe / PayPal WebView keyboard stability on mobile"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Fixed 3 user-reported issues: (1) Stripe/PayPal card checkout white-screen when keyboard opens — added KeyboardAvoidingView + explicit WebView flex + Android pan layout + insets fixes. (2) VOD MoMo migrated to /public/payments/transfer collection API. (3) PayPal simplified — no shipping, guest-friendly landing. Please test: (a) VOD MoMo initiate with payer 250794230137 returns 2xx with pending status (safety guard rejects 250798875274 with HTTP 400). (b) Subscription MoMo same behaviour. (c) PayPal create-subscription returns approveUrl with no shipping asked. (d) PayPal VOD order returns approveUrl. (e) Frontend: open checkout, choose Card (Stripe) or PayPal, tap PAY, verify the WebView stays visible when the keyboard opens on both iOS and Android."

# ---------- Previous session history (kept for context) ----------
previous_agent_communication:
  - agent: "main"

