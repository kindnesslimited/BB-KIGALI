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

user_problem_statement: "1) Wire the new WhatsApp token f8237d8959e03355010bb85cc3dc46a46fb31110 and verify OTPs deliver. 2) Simplify SMS provider chain to only route_mobile + whatsapp (remove Twilio + Africa's Talking references). 3) Build a Payment History Dashboard admin screen showing all Stripe/PayPal/MoMo transactions + revenue totals per method + status breakdown."

backend:
  - task: "Admin Payment History + Revenue endpoints"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Added GET /api/admin/payments (list, filters: method, status, days, limit) — joins user phone/email. GET /api/admin/payments/summary?days=N returns {totals: {success, pending, failed, count}, byMethod: [{method, count, revenue by currency}], totalRevenue: {EUR, RWF, ...}, byDay}. Curl-verified: 30-day summary shows 6 success / 42 pending / 29 failed across stripe/mtn_momo/paypal with EUR 1 + RWF 13,000 revenue."
  - task: "WhatsApp token + simplified SMS chain"
    implemented: true
    working: true
    file: "/app/backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Updated WHATSAPP_API_TOKEN to new value 'f8237d8959e03355010bb85cc3dc46a46fb31110'. Set SMS_PROVIDER_ORDER='route_mobile,whatsapp' (removed africas_talking + twilio per user request). Direct API test with curl confirmed WhatsApp accepts the token: {code:'110', status:'request accepted', output:'Message sent'} — REAL WHATSAPP DELIVERY IS NOW WORKING."

frontend:
  - task: "Admin Payments dashboard screen"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/admin/payments.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "New screen at /admin/payments. Time-window segment (7D/30D/90D), revenue cards per currency, status pills (success/pending/failed counts), 'By Method' breakdown card (PayPal/Stripe/MoMo icons with amounts per currency), transaction list with status filter chips (all/success/pending/failed). Card added to admin home at position 2 (right after Live URLs). Route registered in root layout. Pull-to-refresh + top-right refresh button."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 10
  run_ui: true

test_plan:
  current_focus:
    - "Admin Payment History + Revenue endpoints"
    - "WhatsApp token + simplified SMS chain"
    - "Admin Payments dashboard screen"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Verify: (1) GET /api/admin/payments/summary?days=30 returns totalRevenue map + byMethod array + byDay array. (2) GET /api/admin/payments?days=30&limit=5 returns enriched Payment[] with userPhone/userEmail. (3) Filter by ?method=stripe and ?status=success work. (4) Non-admin auth → 403; no auth → 401. (5) WhatsApp OTP now REALLY delivers — POST /api/auth/otp/start with a random Rwandan phone (NOT admin) should return {ok:true, smsSent:true, provider:'whatsapp' or 'route_mobile'} — verify against sms_deliveries collection there's a new row with success=true. Do NOT test with real user phone — a mock phone like +250799000123 is fine, but expect the message to be sent to that number. (6) Frontend: admin can navigate to Admin Console → 'Payments & Revenue' card (position 2), see 3 window options (7D/30D/90D), revenue cards, status pills, method breakdown, tx list with filter chips. Admin phone +250798875272, OTP in testCode field."


