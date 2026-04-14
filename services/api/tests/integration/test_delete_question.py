#!/usr/bin/env python3
"""
Test script to verify cache invalidation works for question deletions
"""
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


def delete_question(token, task_id, question_index):
    """Delete a question from the task"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(
        f"{BASE_URL}/tasks/{task_id}/questions/{question_index}", headers=headers
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to delete question: {response.status_code} - {response.text}")
        return None


def main():
    print("=== Testing Cache Invalidation for Question Deletions ===\n")

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
        if tasks and len(tasks) > 1:
            second_question = tasks[1]
            print(f"   Second question to delete: '{second_question.get('question', 'N/A')}'")
            print(f"   Questions before deletion:")
            for i, task in enumerate(tasks):
                print(f"     {i+1}. {task.get('question', 'N/A')[:50]}...")
            print()
        else:
            print("   Need at least 2 questions to test deletion!")
            return
    else:
        print("Failed to get initial data!")
        return

    # Step 3: Delete the second question (index 1)
    print("3. Deleting the second question...")
    delete_result = delete_question(token, TASK_ID, 1)
    if delete_result:
        print("✓ Question deleted successfully\n")
    else:
        print("Failed to delete question!")
        return

    # Step 4: Get task data again (should show one less question immediately)
    print("4. Getting task data again (testing cache invalidation for deletions)...")
    updated_data = get_task_data(token, TASK_ID)
    if updated_data:
        updated_count = updated_data.get("total_tasks", 0)
        updated_tasks = updated_data.get("tasks", [])
        print(f"✓ Updated question count: {updated_count}")
        print(f"   Questions after deletion:")
        for i, task in enumerate(updated_tasks):
            print(f"     {i+1}. {task.get('question', 'N/A')[:50]}...")

        # Check if the deletion was applied
        if updated_count == initial_count - 1:
            print(f"\n✅ SUCCESS: Cache invalidation works for question deletions!")
            print(f"   Question count reduced from {initial_count} to {updated_count} immediately!")
        else:
            print(f"\n❌ FAILURE: Question deletion not reflected immediately")
            print(f"   Expected count: {initial_count - 1}, Actual count: {updated_count}")
    else:
        print("Failed to get updated data!")


if __name__ == "__main__":
    main()
