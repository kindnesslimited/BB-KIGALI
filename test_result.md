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

user_problem_statement: "1) Payments failing on Android — MoMo shows a generic error and PayPal on Android WebView may fail to detect success. 2) Add admin ability to promote other users to admin. 3) Better MoMo error surfacing so users know WHY payment failed."

backend:
  - task: "Admin Users CRUD + Invite"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Added GET /api/admin/users (with optional ?q= search), PUT /api/admin/users/{id}/role (promote/demote with self-lockout + last-admin guard), POST /api/admin/users/invite (create-or-promote by phone/email), DELETE /api/admin/users/{id} (same guards). Curl-tested: list returned 19 users, invite promoted existing +250788111222 to admin."
  - task: "MoMo failure_reason surfacing"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Both /billing/momo/initiate and /billing/vod/{id}/momo now return a human-readable `message` and raw `failureReason` when BeSoft/MTN rejects the debit (insufficient balance, invalid number, not registered, timeout). Confirmed via curl the message returns 'MoMo declined: provider error [HTTP_400]...'"

frontend:
  - task: "Admin Users screen"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/admin/users.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "New screen: search bar, admin/user role toggle (with confirmation), delete user, and an Invite modal (phone or email tab) that creates or promotes to admin. Card added to /admin/index.tsx (icon: people-outline, route: /admin/users). Route registered in root layout."
  - task: "PayPal WebView Android return URL fix"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/checkout.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Changed onShouldStartLoadWithRequest to return false when URL contains /paypal/success or /paypal/cancel — previously it returned true, so on Android the WebView attempted to load bbkigali.com/paypal/success (which is behind Netlify password protection = 401) before the modal closed, causing an error page flash. Also applied to /app/frontend/app/video/[id].tsx for VOD unlock PayPal WebView."
  - task: "MoMo error surface in checkout + video"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/checkout.tsx, /app/frontend/app/video/[id].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "If backend returns status='failed' immediately (BeSoft/MTN rejects the debit), show the humanized `message` instead of entering pointless polling loop."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 6
  run_ui: true

test_plan:
  current_focus:
    - "Admin Users CRUD + Invite"
    - "MoMo failure_reason surfacing"
    - "Admin Users screen"
    - "PayPal WebView Android return URL fix"
    - "MoMo error surface in checkout + video"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "User reported: 'Payments not working for all channels on Android — payment page opens but errors out'. Root cause analysis: (a) MoMo debit is being genuinely rejected by BeSoft/MTN with HTTP 400 (this is a real gateway rejection, not our code — user needs to contact BeSoft support to resolve their MTN provider status); however the frontend was showing a generic 'Payment failed' message instead of the specific reason. Now shows humanized reason. (b) PayPal WebView on Android was allowing navigation to bbkigali.com/paypal/success which is behind Netlify password protection — this caused an error page flash before the modal could close. Fixed by returning false from onShouldStartLoadWithRequest. Also added new Admin Users management screen (search, toggle role, invite by phone/email). Please test: (1) admin can navigate to Admin > Users, see list, toggle roles, invite new user; (2) MoMo failure returns human-readable message; (3) PayPal WebView modal closes cleanly on success URL (returns false to avoid loading broken bbkigali.com). Admin phone: +250798875272 (OTP is returned in testCode field of /api/auth/otp/start response)."

