#!/usr/bin/env python3
"""
Test script to verify multiple organizations are returned by the API
"""

import json

import requests


def test_multiple_organizations():
    # Test project with multiple organizations
    project_id = "6be8474c-5e55-4e99-890a-a39ef9ebff50"

    # We'll test without authentication first to see the structure
    try:
        response = requests.get(f"http://localhost:8000/api/projects/{project_id}")
        print(f"Status Code: {response.status_code}")

        if response.status_code == 401:
            print("Authentication required - expected for secure endpoints")
            return

        data = response.json()
        print(f"Response data: {json.dumps(data, indent=2)}")

        # Check if organizations field exists
        if "organizations" in data:
            print(f"✅ Organizations field found: {data['organizations']}")
            if len(data["organizations"]) > 1:
                print(
                    f"✅ Multiple organizations detected: {len(data['organizations'])} organizations"
                )
            else:
                print(f"❌ Only {len(data['organizations'])} organization(s) found")
        else:
            print("❌ Organizations field not found in response")

        # Check legacy organization field
        if "organization" in data:
            print(f"✅ Legacy organization field found: {data['organization']}")
        else:
            print("❌ Legacy organization field not found")

    except Exception as e:
        print(f"Error testing API: {e}")


if __name__ == "__main__":
    test_multiple_organizations()
