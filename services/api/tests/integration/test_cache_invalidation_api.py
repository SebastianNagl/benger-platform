#!/usr/bin/env python3
"""
Test script to verify cache invalidation is working properly for Issue #153
"""
import json
import time

import redis
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


def add_question(token, task_id, question_data):
    """Add a question to the task"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(
        f"{BASE_URL}/tasks/{task_id}/add-questions",
        headers=headers,
        json={"questions": [question_data]},
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to add question: {response.status_code} - {response.text}")
        return None


def check_redis_cache():
    """Check Redis cache directly"""
    try:
        r = redis.Redis(
            host="localhost",
            port=6379,
            db=0,
            password="redis123!",
            decode_responses=True,
        )
        r.ping()

        # Find all task_data keys
        pattern = f"task_data:{TASK_ID}:*"
        keys = r.keys(pattern)

        print(f"📊 Redis cache keys matching '{pattern}': {len(keys)}")
        for key in keys:
            value = r.get(key)
            if value:
                data = json.loads(value)
                print(f"   {key}: {data.get('total', 'N/A')} items")
            else:
                print(f"   {key}: (empty)")
        return r
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return None


def main():
    print("=== Testing Cache Invalidation for Issue #153 ===\n")

    # Step 0: Check Redis cache before starting
    print("0. Checking Redis cache before test...")
    check_redis_cache()
    print()

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
        print(f"✓ Initial question count: {initial_count}")
        print(f"   Tasks: {[t.get('question', 'N/A') for t in initial_data.get('tasks', [])]}\n")
    else:
        print("Failed to get initial data!")
        return

    # Step 3: Add a new question
    print("3. Adding a new question...")
    new_question = {
        "question": f"Test Question: Cache invalidation test at {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "context": "Testing cache invalidation fix for Issue #153",
        "reference_answers": ["Yes, the cache invalidation is working properly"],
    }

    add_result = add_question(token, TASK_ID, new_question)
    if add_result:
        print("✓ Question added successfully")
        print("   Checking cache after adding question...")
        check_redis_cache()
        print()
    else:
        print("Failed to add question!")
        return

    # Step 4: Get task data again (should show new question immediately)
    print("4. Getting task data again (testing cache invalidation)...")
    updated_data = get_task_data(token, TASK_ID)
    if updated_data:
        updated_count = updated_data.get("total_tasks", 0)
        print(f"✓ Updated question count: {updated_count}")
        print(f"   Tasks: {[t.get('question', 'N/A') for t in updated_data.get('tasks', [])]}")

        # Check if cache invalidation worked
        if updated_count > initial_count:
            print(
                f"\n✅ SUCCESS: Cache invalidation is working! Question count increased from {initial_count} to {updated_count}"
            )
            print("   The new question appears immediately without manual refresh!")
        else:
            print(
                f"\n❌ FAILURE: Cache invalidation not working. Question count still {updated_count}"
            )
            print("   The new question is not visible immediately.")
    else:
        print("Failed to get updated data!")


if __name__ == "__main__":
    main()
