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

user_problem_statement: "Route Mobile SMS needs IP whitelisting which Emergent K8s can't guarantee (no static IP). User wants a multi-provider SMS chain that tries each in order — if one fails, use the next. Providers: Route Mobile, Twilio, Africa's Talking, WhatsApp (whatsapp.nostress.vip)."

backend:
  - task: "Multi-provider SMS chain"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Refactored _send_sms into a pluggable chain. Added 4 providers: _sms_route_mobile (existing), _sms_twilio (Basic auth, MG-prefix messaging service support), _sms_africas_talking (apiKey header + Recipients.status='Success' check), _sms_whatsapp (POSTs JSON with multi-key body — to/phone/number/message/text — to any nostress-compatible endpoint). SMS_PROVIDER_ORDER env var controls sequence. First success wins. OTP start now checks 'any_provider_ready' instead of only Route Mobile. Curl-verified: Route Mobile still returns 1703, chain falls through to unconfigured providers, response shows all attempts."
  - task: "Admin SMS provider status + test endpoint"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "GET /api/admin/sms/providers returns {order, providers{name:{configured, senderId, from, endpoint, notes}}} — booleans only, secrets never exposed. POST /api/admin/sms/test {phone, message?} runs full chain and returns {sent, provider, attempts}. Curl-verified."

frontend:
  - task: "Admin SMS providers screen"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/admin/sms.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "New screen at /admin/sms shows providers in priority order with READY/OFF badges, sender IDs, and inline notes. Has a Send Test SMS input + button that surfaces which provider succeeded. Card added to admin home with icon 'chatbubbles-outline'. Route registered in root layout."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 8
  run_ui: true

test_plan:
  current_focus:
    - "Multi-provider SMS chain"
    - "Admin SMS provider status + test endpoint"
    - "Admin SMS providers screen"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Built pluggable SMS provider chain with fallback. Currently only Route Mobile is configured (and returning 1703 = credentials/IP not whitelisted). User is expected to add Twilio/Africa's Talking/WhatsApp API keys later. Please verify: (1) GET /api/admin/sms/providers returns 4 providers with correct .configured booleans. (2) POST /api/admin/sms/test with a phone tries each provider and returns attempts string with all providers listed. (3) Non-admin auth is rejected. (4) Frontend: admin can navigate to Admin > SMS Providers, see 4-row list with priority badges, see READY/OFF badges, can send a test SMS. Admin phone +250798875272, OTP in testCode field of otp/start."

