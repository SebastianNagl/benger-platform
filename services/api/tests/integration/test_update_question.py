#!/usr/bin/env python3
"""
Test script to verify cache invalidation works for question updates
"""
import time

import requests

# Configuration
BASE_URL = "http://localhost:8000"
TASK_ID = "e001c57a-8417-466e-9df1-bbceff0dcfc2"

# Admin credentials
USERNAME = "admin"
PASSWORD = "admin"


def login():
    """Login and get access token"""
    response = requests.post(
        f"{BASE_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    if response.status_code == 200:
        token_data = response.json()
        return token_data["access_token"]
    else:
        print(f"Login failed: {response.status_code} - {response.text}")
        return None


def get_task_data(token, task_id):
    """Get task data"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/tasks/{task_id}/data", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to get task data: {response.status_code} - {response.text}")
        return None


def update_question(token, task_id, question_index, update_data):
    """Update a question in the task"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.patch(
        f"{BASE_URL}/tasks/{task_id}/questions/{question_index}",
        headers=headers,
        json=update_data,
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to update question: {response.status_code} - {response.text}")
        return None


def main():
    print("=== Testing Cache Invalidation for Question Updates ===\n")

    # Step 1: Login
    print("1. Logging in...")
    token = login()
    if not token:
        print("Failed to login!")
        return
    print("✓ Logged in successfully\n")

    # Step 2: Get initial task data
    print("2. Getting initial task data...")
    initial_data = get_task_data(token, TASK_ID)
    if initial_data:
        initial_count = initial_data.get("total_tasks", 0)
        tasks = initial_data.get("tasks", [])
        print(f"✓ Current question count: {initial_count}")
        if tasks:
            first_question = tasks[0]
            print(f"   First question: '{first_question.get('question', 'N/A')}'")
            print(f"   Reference answers: {first_question.get('reference_answers', [])}\n")
        else:
            print("   No questions found!")
            return
    else:
        print("Failed to get initial data!")
        return

    # Step 3: Update the first question
    print("3. Updating the first question...")
    updated_question_data = {
        "question": f"UPDATED: {first_question.get('question', 'Original')} - Updated at {time.strftime('%H:%M:%S')}",
        "reference_answers": [
            "Updated answer 1",
            "Updated answer 2",
            "Cache invalidation test",
        ],
        "context": "Updated context - testing cache invalidation for updates",
    }

    update_result = update_question(token, TASK_ID, 0, updated_question_data)
    if update_result:
        print("✓ Question updated successfully\n")
    else:
        print("Failed to update question!")
        return

    # Step 4: Get task data again (should show updated question immediately)
    print("4. Getting task data again (testing cache invalidation for updates)...")
    updated_data = get_task_data(token, TASK_ID)
    if updated_data:
        updated_tasks = updated_data.get("tasks", [])
        if updated_tasks:
            updated_first_question = updated_tasks[0]
            print(f"✓ Updated question: '{updated_first_question.get('question', 'N/A')}'")
            print(f"   Reference answers: {updated_first_question.get('reference_answers', [])}")

            # Check if the update was applied
            if (
                "UPDATED:" in updated_first_question.get("question", "")
                and len(updated_first_question.get("reference_answers", [])) == 3
            ):
                print(f"\n✅ SUCCESS: Cache invalidation works for question updates!")
                print("   The updated question and reference answers appear immediately!")
            else:
                print(f"\n❌ FAILURE: Question update not visible immediately")
                print(f"   Expected 'UPDATED:' in question and 3 reference answers")
        else:
            print("No tasks found in updated data!")
    else:
        print("Failed to get updated data!")


if __name__ == "__main__":
    main()
