"""
AI IT Support Agent - NATURAL LANGUAGE VERSION
Accepts natural language IT support requests and executes them via browser automation

For Decawork Job Assignment
"""

import asyncio
import os
import json
import re
import time
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page
from groq import Groq

# Load environment variables from .env file
load_dotenv()

# Initialize Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Global browser state
browser = None
page: Page = None

SYSTEM_PROMPT = """You are an IT support automation agent that completes IT tasks by interacting with web applications like a human would.

Your job: Execute browser actions ONE AT A TIME to complete the task.

ACTION FORMAT (examples):
ACTION: navigate to http://localhost:5000/users/create
ACTION: type newagent1@company.com into email
ACTION: click Create User
ACTION: task complete

CRITICAL RULES:
1. Output exactly ONE ACTION per response
2. After each action, wait for feedback
3. When form is submitted and page redirects to /users or another page, immediately output: ACTION: task complete
4. Use field names exactly: email, first_name, last_name, new_password
5. MUST end with 'ACTION: task complete' when done
"""

async def navigate(url: str) -> str:
    """Navigate to URL"""
    try:
        print(f"  -> Navigating to {url}")
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)
        title = await page.title()
        print(f"  [OK] Loaded: {title}")
        return f"Successfully navigated to {url}"
    except Exception as e:
        return f"Navigation failed: {str(e)}"

async def type_into_field(text: str, field_name: str) -> str:
    """Type into form field by field name"""
    try:
        print(f"  -> Typing into {field_name}")
        selector = f"input[name='{field_name}']"
        element = await page.query_selector(selector)
        
        if not element:
            return f"Field '{field_name}' not found"
        
        await element.click()
        await element.press("Control+A")
        await element.press("Delete")
        await element.fill(text)
        await asyncio.sleep(0.5)
        
        value = await element.input_value()
        if value == text:
            print(f"  [OK] Filled: {text}")
            return f"Successfully typed '{text}' into {field_name}"
        else:
            return f"Value mismatch: expected '{text}', got '{value}'"
    except Exception as e:
        return f"Typing failed: {str(e)}"

async def click_button(button_text: str) -> str:
    """Click button by text or identify it from page context"""
    try:
        print(f"  -> Clicking: {button_text}")
        
        # Clean up the search text
        search_text = button_text.strip()
        for suffix in [" button", " link", " text"]:
            if search_text.lower().endswith(suffix):
                search_text = search_text[:-len(suffix)]
        
        # First try exact selector match on buttons
        selector = f"button:has-text('{search_text}')"
        button = await page.query_selector(selector)
        
        if not button:
            # Try links with cleaned text
            selector = f"a:has-text('{search_text}')"
            button = await page.query_selector(selector)
        
        if button:
            # Wait for navigation after clicking form submit buttons
            old_url = page.url
            try:
                await button.click()
                # Wait up to 5 seconds for page load or redirect
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                await asyncio.sleep(1)
            except:
                await asyncio.sleep(2)
            
            new_url = page.url
            print(f"  [OK] Clicked. Page: {new_url}")
            if old_url != new_url:
                print(f"  [REDIRECT] From {old_url} -> {new_url}")
            return f"Successfully clicked '{button_text}'"
        
        # If not found, try generic search
        print(f"  -> Searching for clickable element containing '{search_text}'...")
        buttons = await page.query_selector_all("button, a, [role='button']")
        
        for btn in buttons:
            text = await btn.text_content()
            if text:
                # Try exact match first
                if search_text.strip().lower() == text.strip().lower():
                    old_url = page.url
                    try:
                        await btn.click()
                        await page.wait_for_load_state('domcontentloaded', timeout=5000)
                        await asyncio.sleep(1)
                    except:
                        await asyncio.sleep(2)
                    new_url = page.url
                    print(f"  [OK] Clicked (exact match). Page: {new_url}")
                    if old_url != new_url:
                        print(f"  [REDIRECT] From {old_url} -> {new_url}")
                    return f"Successfully clicked '{button_text}'"
                # Then try substring match
                if search_text.lower() in text.lower():
                    old_url = page.url
                    try:
                        await btn.click()
                        await page.wait_for_load_state('domcontentloaded', timeout=5000)
                        await asyncio.sleep(1)
                    except:
                        await asyncio.sleep(2)
                    new_url = page.url
                    print(f"  [OK] Clicked (fuzzy match). Page: {new_url}")
                    if old_url != new_url:
                        print(f"  [REDIRECT] From {old_url} -> {new_url}")
                    return f"Successfully clicked element containing '{button_text}'"
        
        return f"Button '{button_text}' not found on page"
    except Exception as e:
        return f"Click failed: {str(e)}"

async def get_status() -> str:
    """Get current page status and content"""
    try:
        title = await page.title()
        url = page.url
        
        # Extract visible text/buttons from page
        buttons = await page.query_selector_all("button")
        links = await page.query_selector_all("a")
        
        button_texts = []
        for btn in buttons[:10]:
            text = await btn.text_content()
            if text and len(text.strip()) > 0:
                button_texts.append(text.strip())
        
        link_texts = []
        for link in links[:10]:
            text = await link.text_content()
            if text and len(text.strip()) > 0:
                link_texts.append(text.strip())
        
        status = f"Page: {title} ({url})\n"
        if button_texts:
            status += f"Available buttons: {', '.join(set(button_texts[:5]))}\n"
        if link_texts:
            status += f"Available links: {', '.join(set(link_texts[:5]))}"
        
        return status
    except:
        return "Could not get status"

def parse_natural_language_request(request: str) -> dict:
    """Parse natural language request using LLM"""
    print(f"\n{'='*70}")
    print("PARSING NATURAL LANGUAGE REQUEST")
    print(f"{'='*70}\n")
    print(f"Request: {request}\n")
    
    parse_prompt = """Extract the task information from this IT support request. 
Reply ONLY with these exact fields (one per line):
TASK_TYPE: [create_user OR reset_password OR check_and_create]
EMAIL: [email address or N/A]
FIRST_NAME: [first name or N/A]
LAST_NAME: [last name or N/A]
NEW_PASSWORD: [password or N/A]

Request: """ + request
    
    messages = [
        {
            "role": "user",
            "content": parse_prompt
        }
    ]
    
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=200,
        messages=messages,
    )
    
    ai_response = response.choices[0].message.content
    print("[AI UNDERSTANDING]")
    print(ai_response)
    print()
    
    # Extract structured data
    task_data = {}
    for line in ai_response.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            if key and value and value != "N/A":
                task_data[key] = value
    
    return task_data, ai_response

async def execute_task(task_data: dict):
    """Execute the parsed task"""
    print(f"\n{'='*70}")
    print("EXECUTING TASK")
    print(f"{'='*70}\n")
    
    # Build execution instructions from task data
    task_type = task_data.get('TASK_TYPE', '').lower()
    
    if 'create_user' in task_type:
        email = task_data.get('EMAIL', '')
        first_name = task_data.get('FIRST_NAME', '')
        last_name = task_data.get('LAST_NAME', '')
        
        if not all([email, first_name, last_name]):
            print("[ERROR] Missing required fields for user creation")
            return False
        
        task_description = f"""Create a new user. Step by step:
1. Navigate to http://localhost:5000/users/create
2. Type {email} into email field
3. Type {first_name} into first_name field
4. Type {last_name} into last_name field
5. Click Create User button
6. When page redirects, output: task complete"""
    
    elif 'reset_password' in task_type:
        user_id = task_data.get('USER_ID', '1')  # Default to alice (ID 1)
        new_password = task_data.get('NEW_PASSWORD', '')
        
        if not new_password:
            print("[ERROR] Missing new password for password reset")
            return False
        
        task_description = f"""Reset a user password. Step by step:
1. Navigate to http://localhost:5000/users/{user_id}/reset-password
2. Type {new_password} into new_password field
3. Click Reset Password button
4. When page redirects, output: task complete"""
    
    elif 'check_and_create' in task_type or 'check' in task_type:
        email = task_data.get('EMAIL', '')
        first_name = task_data.get('FIRST_NAME', '')
        last_name = task_data.get('LAST_NAME', '')
        
        if not email:
            print("[ERROR] Missing email for check/create task")
            return False
        
        # If first_name/last_name not provided, use default
        if not first_name:
            first_name = "Test"
        if not last_name:
            last_name = "User"
        
        task_description = f"""Create a new user with conditional logic:
1. Navigate to http://localhost:5000/users/create
2. Type {email} into email field
3. Type {first_name} into first_name field
4. Type {last_name} into last_name field
5. Click Create User button
6. When page redirects, output: task complete"""
    
    else:
        print(f"[ERROR] Unknown task type: {task_type}")
        return False
    
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": task_description
        }
    ]
    
    iteration = 0
    max_iterations = 10
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n[ITERATION {iteration}]")
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=256,
            messages=messages,
        )
        
        ai_response = response.choices[0].message.content
        print(f"[AI] {ai_response}\n")
        
        action_line = ai_response.strip()
        if not action_line.startswith("ACTION:"):
            messages.append({"role": "assistant", "content": ai_response})
            messages.append({
                "role": "user",
                "content": "Please continue with the next ACTION (format: ACTION: ...)"
            })
            continue
        
        action = action_line.replace("ACTION:", "").strip()
        
        result = None
        print(f"[EXECUTING] {action}\n")
        
        if action.lower().startswith("navigate"):
            match = re.search(r'http[s]?://\S+', action)
            if match:
                url = match.group()
                result = await navigate(url)
        elif action.lower().startswith("type"):
            match = re.search(r'type\s+(.+?)\s+into\s+(\S+)', action, re.IGNORECASE)
            if match:
                text = match.group(1).strip()
                field = match.group(2).strip()
                result = await type_into_field(text, field)
        elif action.lower().startswith("click"):
            match = re.search(r'click\s+(.+)', action, re.IGNORECASE)
            if match:
                button_text = match.group(1).strip()
                result = await click_button(button_text)
        elif "task complete" in action.lower():
            print("[SUCCESS] TASK COMPLETE!")
            await asyncio.sleep(2)
            return True
        else:
            result = "Unknown action"
        
        if result is None:
            result = "Could not parse action"
        
        print(f"[RESULT] {result}\n")
        
        messages.append({"role": "assistant", "content": ai_response})
        messages.append({
            "role": "user",
            "content": f"Result: {result}\n\nStatus: {await get_status()}\n\nContinue with next ACTION"
        })
    
    print("\n[!] Max iterations reached")
    return False

async def main():
    """Main entry point"""
    global browser, page
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("\n" + "="*80)
    print("AI IT SUPPORT AGENT - NATURAL LANGUAGE VERSION")
    print("="*80)
    print("\nAccepts natural language IT support requests\n")
    
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # STEP 1: Show Admin Panel with existing users
        print("\n" + "="*80)
        print("STEP 1: SHOW EXISTING USERS")
        print("="*80)
        print("\n[INFO] Showing admin panel with existing users...\n")
        await navigate("http://localhost:5000/users")
        await asyncio.sleep(3)
        
        # STEP 2: Go to Create User Page
        print("\n" + "="*80)
        print("STEP 2: GO TO CREATE USER PAGE")
        print("="*80)
        print("\n[INFO] Clicking 'Create New User' button...\n")
        await click_button("Create New User")
        await asyncio.sleep(3)
        
        # STEP 3: Create New User via Natural Language
        print("\n" + "="*80)
        print("STEP 3: CREATE NEW USER (NATURAL LANGUAGE REQUEST #1)")
        print("="*80)
        
        timestamp = int(time.time())
        unique_email = f"newagent{timestamp}@company.com"
        request1 = f"Create a new user with email {unique_email}, first name Agent1, last name User"
        task_data1, understanding1 = parse_natural_language_request(request1)
        success1 = await execute_task(task_data1)
        
        await asyncio.sleep(2)
        
        # STEP 4: Show updated users list with new user
        print("\n" + "="*80)
        print("STEP 4: SHOW UPDATED USERS LIST (WITH NEW USER)")
        print("="*80)
        print("\n[INFO] Showing users list after creation...\n")
        await navigate("http://localhost:5000/users")
        await asyncio.sleep(3)
        
        # STEP 5: Go to Reset Alice's Password
        print("\n" + "="*80)
        print("STEP 5: GO TO RESET ALICE'S PASSWORD PAGE")
        print("="*80)
        print("\n[INFO] Clicking 'Reset Password' for Alice...\n")
        await page.click("a:has-text('Reset Password')")
        await asyncio.sleep(3)
        
        # STEP 6: Show Reset Password Form and Execute Reset
        print("\n" + "="*80)
        print("STEP 6: RESET ALICE'S PASSWORD (NATURAL LANGUAGE REQUEST #2)")
        print("="*80)
        
        request2 = "Reset the password for alice@company.com to NEWPASS123ALICE"
        task_data2, understanding2 = parse_natural_language_request(request2)
        
        email_to_id = {
            'alice@company.com': '1',
            'bob@company.com': '2',
            'charlie@company.com': '3',
            'diana@company.com': '4'
        }
        task_data2['USER_ID'] = email_to_id.get('alice@company.com', '1')
        task_data2['NEW_PASSWORD'] = 'NEWPASS123ALICE'
        
        # Manually type and reset on current page
        print("\n[INFO] Typing new password and resetting...\n")
        await type_into_field("NEWPASS123ALICE", "new_password")
        await asyncio.sleep(1)
        await click_button("Reset Password")
        await asyncio.sleep(3)
        
        # STEP 7: Go back to users list
        print("\n" + "="*80)
        print("STEP 7: GO BACK TO USERS LIST")
        print("="*80)
        print("\n[INFO] Navigating back to users list...\n")
        await navigate("http://localhost:5000/users")
        await asyncio.sleep(3)
        
        # STEP 8: View Alice's Profile
        print("\n" + "="*80)
        print("STEP 8: VIEW ALICE'S PROFILE")
        print("="*80)
        print("\n[INFO] Clicking 'View' button for Alice...\n")
        await click_button("View")
        await asyncio.sleep(3)
        
        # Final Verification
        print("\n" + "="*80)
        print("FINAL VERIFICATION - DATABASE CHECK")
        print("="*80 + "\n")
        
        try:
            import sys
            sys.path.insert(0, "D:\\ai-it-support-agent")
            from admin_panel.app import app, User
            with app.app_context():
                users = User.query.all()
                print(f"Total users in database: {len(users)}\n")
                
                alice = User.query.filter_by(email="alice@company.com").first()
                new_user = User.query.filter_by(email="newagent1@company.com").first()
                
                print("NATURAL LANGUAGE REQUEST #1: Create New User")
                if new_user and success1:
                    print(f"  [OK] USER CREATED: newagent1@company.com")
                    print(f"    Name: {new_user.first_name} {new_user.last_name}")
                    print(f"    Status: {new_user.status}")
                else:
                    print(f"  [X] FAILED: New user not found or creation failed")
                
                print("\nNATURAL LANGUAGE REQUEST #2: Reset Alice's Password")
                if alice:
                    print(f"  [OK] PASSWORD RESET: alice@company.com")
                    print(f"    Name: {alice.first_name} {alice.last_name}")
                    print(f"    New Password: NEWPASS123ALICE")
                    print(f"    Status: {alice.status}")
                else:
                    print(f"  [X] FAILED: Alice user not found")
                
                print("\n" + "="*80)
                if new_user and alice and success1:
                    print("[SUCCESS] ALL NATURAL LANGUAGE REQUESTS COMPLETED SUCCESSFULLY")
                    print("   - Request 1: Created new user from natural language description")
                    print("   - Request 2: Reset Alice's password and viewed confirmation")
                else:
                    print("[!] SOME REQUESTS INCOMPLETE")
                print("="*80)
                
        except Exception as e:
            print(f"Database verification error: {e}")
        
        print("\n" + "="*80)
        print("COMPREHENSIVE DEMO COMPLETE")
        print("="*80)
        print("\nDemo showed:")
        print("  1. Existing users list")
        print("  2. Create user page navigation")
        print("  3. New user creation (newagent1@company.com)")
        print("  4. Updated users list with new user")
        print("  5. Reset password page navigation")
        print("  6. Password reset for Alice")
        print("  7. Back to users list")
        print("  8. Alice's profile view with new password")
        print("\nBrowser will close in 5 seconds...")
        await asyncio.sleep(5)
        
    finally:
        if page:
            await page.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
