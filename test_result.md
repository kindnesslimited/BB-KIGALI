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

user_problem_statement: "Enable Stripe LIVE card payments for subscriptions + VOD unlock (Android + Web only, hidden on iOS). Add MoMo→Stripe auto-fallback suggestion when MoMo declines. Route Mobile SMS: preview server IP is 34.7.135.173 (to be whitelisted). Airtel stays 'Coming soon'."

backend:
  - task: "Stripe LIVE integration"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Added Stripe endpoints per integration_expert playbook: GET /api/billing/stripe/config, POST /api/billing/stripe/create-checkout (subscription OR vod), GET /api/billing/stripe/session-status/{id}, POST /api/billing/stripe/webhook (idempotent via db.stripe_events), GET /api/billing/stripe/return (HTML), GET /api/billing/stripe/cancel (HTML). Uses hosted Checkout with inline price_data (EUR). Curl-tested: subscription and VOD both return cs_live_ session IDs with proper checkout URLs. Managed Payments disabled per-session (was causing 'tax code required' error). LIVE keys stored in backend/.env; iOS clients gate the UI so Stripe purchase surface never renders there."

frontend:
  - task: "Checkout: Add Stripe method + iOS gating + MoMo→Stripe fallback"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/checkout.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Added stripe method row (hidden on iOS via ALL_METHODS.filter). WebView modal with #635bff header opens hosted Stripe Checkout URL. onShouldStartLoadWithRequest intercepts /billing/stripe/return and /billing/stripe/cancel URLs. On web, opens Stripe in new tab and polls session-status. When MoMo returns status='failed' on non-iOS, shows a tap-to-switch 'Try card payment instead?' fallback banner."
  - task: "VOD Player: Add Stripe unlock button + fallback"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/video/[id].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Locked box now shows 3 payment options stacked vertically: Card (Stripe, hidden on iOS), PayPal, MoMo. buyVodStripe calls /billing/stripe/create-checkout with purchase_type='vod', opens the same WebView. Same URL interception applied. Post-MoMo-failure suggests Stripe (non-iOS)."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 7
  run_ui: true

test_plan:
  current_focus:
    - "Stripe LIVE integration"
    - "Checkout: Add Stripe method + iOS gating + MoMo→Stripe fallback"
    - "VOD Player: Add Stripe unlock button + fallback"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Enabled Stripe LIVE with user-provided keys. Please validate the endpoints work and the frontend flow renders correctly. IMPORTANT — since these are LIVE keys, do NOT attempt to complete a real payment. Instead: (1) hit /api/billing/stripe/config and expect enabled=true, publishableKey starts with pk_live_. (2) POST /api/billing/stripe/create-checkout with subscription+plan and with vod+show_id — both should return sessionId (starts with cs_live_) and checkoutUrl. (3) Session-status for a non-owner should return 404 (auth boundary). (4) Frontend: on the checkout screen (via paywall → pick plan), verify 3 methods visible (PayPal / Stripe / MoMo) with Airtel showing 'Coming soon'. On iOS platform simulation the Stripe row should be hidden — since we can only test web/Android on the emulator, confirm the isIOS gate is correct in code but skip iOS runtime test. (5) On the VOD screen with a locked video, verify the three payment buttons render vertically. Admin phone +250798875272, OTP in testCode field of otp/start response. Do NOT test actual Stripe payment completion (would charge the real card)."

