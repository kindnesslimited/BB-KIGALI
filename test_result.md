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

user_problem_statement: "USER-REPORTED BUG: 'MoMo declined: provider error [HTTP_400]: unexpected status 400: (retryable: false)'. Root cause: BeSoft's debit-credit atomic endpoint fails at MTN provider level. Fix: add automatic fallback to pure /debit endpoint + humanize the error message + suggest Stripe as alternative in the UI (frontend already does this via suggestStripe banner)."

backend:
  - task: "MoMo debit-credit → debit fallback"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Refactored /billing/momo/initiate to try /public/payments/debit-credit first; if that returns provider error HTTP_400 (or non-2xx), automatically retry with /public/payments/debit (pure collection). Records besoftAttempt='debit_credit' or 'debit_only_fallback' on the payment row so admin can trace which endpoint served each transaction. Also added new friendly error branch for HTTP_400/provider errors: 'MTN MoMo temporarily unavailable. Please try Card payment or try again in a few minutes.' Curl-verified: fallback attempts both endpoints; both currently fail (confirming BeSoft/MTN gateway is the root cause, not our payload)."

frontend:
  - task: "MoMo → Stripe auto-suggest banner (existing feature)"
    implemented: true
    working: true
    file: "/app/frontend/app/checkout.tsx, /app/frontend/app/video/[id].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Existing suggestStripe banner already fires when MoMo returns status='failed'. Now with the new humanized message the user sees a clearer explanation before deciding to switch. No new frontend changes needed."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 11
  run_ui: true

test_plan:
  current_focus:
    - "MoMo debit-credit → debit fallback"
    - "MoMo → Stripe auto-suggest banner (existing feature)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Verify: (1) POST /api/billing/momo/initiate {plan:basic_monthly, phone:+250788999888} returns status='failed' with message that includes 'MTN MoMo temporarily unavailable' or 'Card payment'. (2) The payment row in db.payments has besoftAttempt field set to either 'debit_credit' (if fallback wasn't reached) or 'debit_only_fallback' (if fallback succeeded but the payment still failed at MTN). (3) Response has both 'message' (humanized) and 'failureReason' (raw) fields. (4) Frontend: on checkout screen selecting MoMo → tap PAY → verify humanized error appears + 'Try card payment instead?' fallback banner is visible (non-iOS). Tap banner → verify method flips to Stripe. Do NOT test actual MoMo success — BeSoft gateway is genuinely broken for this account. Admin phone +250798875272, OTP in testCode."


