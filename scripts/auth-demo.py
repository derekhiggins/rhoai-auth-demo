#!/usr/bin/env python3
"""
LlamaStack Authentication Demo

This script demonstrates role-based access control for LlamaStack using Keycloak authentication.
It shows how different user personas (admin, datascience, basic) have different levels of access
to various models and APIs.

Usage:
    python auth-demo.py [--llamastack-url URL] [--keycloak-url URL] [--client-secret SECRET]

Environment Variables:
    LLAMASTACK_URL: LlamaStack server URL
    KEYCLOAK_URL: Keycloak base URL  
    KEYCLOAK_CLIENT_SECRET: Keycloak client secret
"""

import os
import sys
import json
import argparse
import requests
import urllib3
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import time

# Disable SSL warnings for demo purposes
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@dataclass
class User:
    username: str
    password: str
    role: str
    description: str

@dataclass
class TestCase:
    name: str
    method: str
    endpoint: str
    data: Optional[Dict[str, Any]] = None
    expected_success: bool = True
    description: str = ""

class LlamaStackAuthDemo:
    def __init__(self, llamastack_url: str, keycloak_url: str, client_secret: str):
        self.llamastack_url = llamastack_url.rstrip('/')
        self.keycloak_url = keycloak_url.rstrip('/')
        self.client_secret = client_secret
        self.realm = "llamastack-demo"
        self.client_id = "llamastack"
        
        # Demo users
        self.users = [
            User("admin-user", "admin123", "admin", "Full access to all models and operations"),
            User("datascience-user", "ds123", "datascience", "Access to all inference models"),
            User("basic-user", "basic123", "basic", "Basic inference access to vLLM models only")
        ]
        
        # Test cases for each user role
        self.test_cases = {
            "admin": [
                TestCase("List Models", "GET", "/v1/models", expected_success=True, 
                        description="Admin should be able to list all models"),
                TestCase("Access vLLM Model", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "vllm-inference/llama-3-2-3b", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=True, description="Admin should access vLLM models"),
                TestCase("Access GPT-4o-mini", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=True, description="Admin should access GPT-4o-mini"),
                TestCase("Access GPT-4o", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=True, description="Admin should access GPT-4o"),
                TestCase("List Agents", "GET", "/v1/agents", expected_success=True,
                        description="Admin should access agents API")
            ],
            "datascience": [
                TestCase("List Models", "GET", "/v1/models", expected_success=True,
                        description="Data Science should be able to list models"),
                TestCase("Access vLLM Model", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "vllm-inference/llama-3-2-3b", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=True, description="Data Science should access vLLM models"),
                TestCase("Access GPT-4o-mini", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=True, description="Data Science should access GPT-4o-mini"),
                TestCase("Access GPT-4o", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=False, description="Data Science should NOT access GPT-4o"),
                TestCase("List Agents", "GET", "/v1/agents", expected_success=True,
                        description="Data Science should access agents API")
            ],
            "basic": [
                TestCase("List Models", "GET", "/v1/models", expected_success=True,
                        description="Basic should be able to list models"),
                TestCase("Access vLLM Model", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "vllm-inference/llama-3-2-3b", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=True, description="Basic should access vLLM models"),
                TestCase("Access GPT-4o-mini", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=False, description="Basic should NOT access GPT-4o-mini"),
                TestCase("Access GPT-4o", "POST", "/v1/openai/v1/chat/completions",
                        data={"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 50},
                        expected_success=False, description="Basic should NOT access GPT-4o"),
                TestCase("List Agents", "GET", "/v1/agents", expected_success=True,
                        description="Basic should have read access to agents API")
            ]
        }
    
    def get_user_token(self, user: User) -> Optional[str]:
        """Get OAuth token for a user"""
        token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'username': user.username,
            'password': user.password,
            'grant_type': 'password'
        }
        
        try:
            response = requests.post(token_url, data=data, verify=False, timeout=10)
            if response.status_code == 200:
                return response.json().get('access_token')
            else:
                print(f"❌ Failed to get token for {user.username}: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Error getting token for {user.username}: {e}")
            return None
    
    def decode_token_claims(self, token: str) -> Dict[str, Any]:
        """Decode JWT token to show claims (for demo purposes)"""
        import base64
        try:
            # JWT tokens have 3 parts separated by dots
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            
            # Decode the payload (second part)
            payload = parts[1]
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.b64decode(payload)
            return json.loads(decoded)
        except Exception as e:
            print(f"Warning: Could not decode token: {e}")
            return {}
    
    def test_endpoint(self, token: str, test_case: TestCase) -> bool:
        """Test an endpoint with the given token"""
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.llamastack_url}{test_case.endpoint}"
        
        try:
            if test_case.method == "GET":
                response = requests.get(url, headers=headers, verify=False, timeout=30)
            elif test_case.method == "POST":
                response = requests.post(url, headers=headers, json=test_case.data, verify=False, timeout=30)
            else:
                print(f"❌ Unsupported method: {test_case.method}")
                return False
            
            success = response.status_code < 400
            
            # Print result
            status_icon = "✅" if success == test_case.expected_success else "❌"
            expected_text = "should succeed" if test_case.expected_success else "should fail"
            actual_text = "succeeded" if success else "failed"
            
            print(f"   {status_icon} {test_case.name}: {actual_text} (HTTP {response.status_code}) - {expected_text}")
            print(f"      {test_case.description}")
            
            # Show response for successful inference calls
            if success and "chat/completions" in test_case.endpoint and response.status_code == 200:
                try:
                    resp_data = response.json()
                    if 'choices' in resp_data and resp_data['choices']:
                        content = resp_data['choices'][0].get('message', {}).get('content', '')[:100]
                        print(f"      Response: {content}...")
                except:
                    pass
            
            return success == test_case.expected_success
            
        except Exception as e:
            print(f"   ❌ {test_case.name}: Error - {e}")
            return False
    
    def test_unauthenticated_access(self) -> bool:
        """Test that unauthenticated requests are rejected"""
        print("\n🔒 Testing Unauthenticated Access")
        print("=" * 50)
        
        try:
            response = requests.get(f"{self.llamastack_url}/v1/models", verify=False, timeout=10)
            success = response.status_code == 401
            
            if success:
                print("✅ Unauthenticated request properly rejected (HTTP 401)")
            else:
                print(f"❌ Unauthenticated request not rejected (HTTP {response.status_code})")
            
            return success
        except Exception as e:
            print(f"❌ Error testing unauthenticated access: {e}")
            return False
    
    def run_user_tests(self, user: User) -> Dict[str, Any]:
        """Run all tests for a specific user"""
        print(f"\n👤 Testing User: {user.username} ({user.role} role)")
        print("=" * 50)
        print(f"Description: {user.description}")
        
        # Get token
        print(f"🔑 Getting token for {user.username}...")
        token = self.get_user_token(user)
        if not token:
            print(f"❌ Failed to get token for {user.username}")
            return {"success": False, "tests_passed": 0, "tests_total": 0}
        
        print("✅ Token obtained successfully")
        
        # Show token claims
        claims = self.decode_token_claims(token)
        if claims:
            print(f"📋 Token claims:")
            print(f"   Subject: {claims.get('sub', 'N/A')}")
            print(f"   Username: {claims.get('preferred_username', 'N/A')}")
            print(f"   Roles: {claims.get('llamastack_roles', 'N/A')}")
            print(f"   Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(claims.get('exp', 0)))}")
        
        # Run tests
        test_cases = self.test_cases.get(user.role, [])
        tests_passed = 0
        
        print(f"\n🧪 Running {len(test_cases)} tests...")
        for test_case in test_cases:
            if self.test_endpoint(token, test_case):
                tests_passed += 1
        
        success_rate = (tests_passed / len(test_cases)) * 100 if test_cases else 0
        print(f"\n📊 Results: {tests_passed}/{len(test_cases)} tests passed ({success_rate:.1f}%)")
        
        return {
            "success": tests_passed == len(test_cases),
            "tests_passed": tests_passed,
            "tests_total": len(test_cases),
            "success_rate": success_rate
        }
    
    def run_demo(self) -> bool:
        """Run the complete authentication demo"""
        print("🦙 LlamaStack Authentication Demo")
        print("=" * 50)
        print(f"LlamaStack URL: {self.llamastack_url}")
        print(f"Keycloak URL: {self.keycloak_url}")
        print(f"Realm: {self.realm}")
        
        # Test unauthenticated access
        if not self.test_unauthenticated_access():
            print("⚠️  Warning: Unauthenticated access test failed")
        
        # Test each user
        all_results = []
        for user in self.users:
            result = self.run_user_tests(user)
            all_results.append(result)
        
        # Summary
        print("\n📈 Demo Summary")
        print("=" * 50)
        
        total_tests = sum(r["tests_total"] for r in all_results)
        total_passed = sum(r["tests_passed"] for r in all_results)
        overall_success = all(r["success"] for r in all_results)
        
        for i, (user, result) in enumerate(zip(self.users, all_results)):
            status = "✅" if result["success"] else "❌"
            print(f"{status} {user.username} ({user.role}): {result['tests_passed']}/{result['tests_total']} tests passed")
        
        print(f"\n🎯 Overall: {total_passed}/{total_tests} tests passed")
        
        if overall_success:
            print("🎉 All authentication and authorization tests passed!")
            print("\n✨ The demo shows that:")
            print("   o Admin users have full access to all models and APIs")
            print("   o Data Science users can access all inference models except GPT-4o")
            print("   o Basic users can only access vLLM models")
            print("   o Unauthenticated requests are properly rejected")
        else:
            print("⚠️  Some tests failed. Check the configuration and try again.")
        
        return overall_success

def main():
    parser = argparse.ArgumentParser(description="LlamaStack Authentication Demo")
    parser.add_argument("--llamastack-url", 
                       default=os.getenv("LLAMASTACK_URL", "http://localhost:8321"),
                       help="LlamaStack server URL")
    parser.add_argument("--keycloak-url",
                       default=os.getenv("KEYCLOAK_URL", "https://kc-keycloak.com"),
                       help="Keycloak base URL")
    parser.add_argument("--client-secret",
                       default=os.getenv("KEYCLOAK_CLIENT_SECRET"),
                       help="Keycloak client secret")
    
    args = parser.parse_args()
    
    if not args.client_secret:
        print("❌ Keycloak client secret is required")
        print("   Set KEYCLOAK_CLIENT_SECRET environment variable or use --client-secret")
        print("   Get the secret from Keycloak admin console: Clients → llamastack → Credentials")
        sys.exit(1)
    
    demo = LlamaStackAuthDemo(args.llamastack_url, args.keycloak_url, args.client_secret)
    success = demo.run_demo()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
