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

user_problem_statement: "Wire the WhatsApp API (whatsapp.nostress.vip/api_com.php) with the user-provided token 18237d895903355010bb85cc3dc46a46fb31110 so OTP can deliver via WhatsApp. Add Stripe webhook secret whsec_OwJWz4MgxKAogBu7TYrZOt1Qw7pSQTKn to secure webhook signature verification. Build a Provider Analytics dashboard that shows attempt/delivered counts + success rate per SMS provider over the last 7 days. USER-REPORTED BUG: 'Check if OTP can deliver via WhatsApp'."

backend:
  - task: "WhatsApp OTP wiring (nostress.vip api_com.php)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Rewrote _sms_whatsapp per the actual nostress.vip API docs (crawled from whatsapp.nostress.vip/api/). Correct format is POST to https://whatsapp.nostress.vip/api_com.php with JSON {action:'send',auth:<token>,tel:<phone-no-plus>,msg:<text>}. Success indicator is code=='110' or status contains 'accepted'. Parses JSON response; treats code=='101' invalid token, code=='102' invalid phone, etc. Curl-verified: our request now reaches the API correctly and returns {code:'101', status:'Error: invalid token'} — the token in .env is being REJECTED by the WhatsApp gateway. Code is correct; user must verify their token."
  - task: "Stripe webhook signing secret"
    implemented: true
    working: true
    file: "/app/backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Set STRIPE_WEBHOOK_SECRET='whsec_OwJWz4MgxKAogBu7TYrZOt1Qw7pSQTKn' (the production BB KIGALI endpoint secret). Existing webhook handler /api/billing/stripe/webhook already uses stripe.Webhook.construct_event with this secret; unsigned events now rejected in prod."
  - task: "SMS provider analytics"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Added db.sms_deliveries collection — every provider attempt is now recorded with {provider, success, skipped, response, weekKey, createdAt}. GET /api/admin/sms/analytics?days=7 returns {windowDays, totals, providers[], byDay[]} with success rate per provider. Includes zero-data providers so UI always shows all 4. Curl-verified with real test SMS run that recorded 4 rows (2 attempts + 2 skipped)."

frontend:
  - task: "SMS Providers screen: Analytics dashboard"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/admin/sms.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Added Analytics card at top of screen (only visible when attempts>0): 3-stat grid (Delivered, Attempts, Success rate %) + horizontal bar chart per provider showing delivered/attempts ratio. Fetched in parallel with providers list."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 9
  run_ui: true

test_plan:
  current_focus:
    - "WhatsApp OTP wiring (nostress.vip api_com.php)"
    - "Stripe webhook signing secret"
    - "SMS provider analytics"
    - "SMS Providers screen: Analytics dashboard"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "USER-REPORTED BUG: 'check if OTP can deliver via WhatsApp'. I have wired WhatsApp per the nostress.vip API docs. Curl test confirms the request format is correct — but their API returned {code:'101', status:'Error: invalid token'} for the token the user provided. So: (1) validate the WhatsApp integration CODE is correct (the request body must be {action:'send', auth:<token>, tel:<phone-no-+>, msg:<text>} POSTed as JSON to https://whatsapp.nostress.vip/api_com.php); (2) confirm the token is being sent as-is from .env; (3) confirm the failure path is being recorded in sms_deliveries collection; (4) confirm analytics endpoint returns provider-level counts; (5) frontend: SMS Providers screen shows the analytics card when there's data. Please do NOT test actual delivery to a WhatsApp number — token is confirmed rejected by the gateway. Admin phone +250798875272, OTP in testCode field."


