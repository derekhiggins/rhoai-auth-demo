#!/usr/bin/env python3
"""
Interactive LlamaStack Authentication Demo

This script provides an interactive demonstration of LlamaStack authentication.
It prompts for user credentials, obtains a token, and tests access to various models and APIs.

Usage:
    python interactive-demo.py [--llamastack-url URL] [--keycloak-url URL]

Environment Variables:
    LLAMASTACK_URL: LlamaStack server URL
    KEYCLOAK_URL: Keycloak base URL
"""

import os
import sys
import json
import argparse
import requests
import urllib3
from typing import Optional, Dict, Any
import getpass

# Disable SSL warnings for demo purposes
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class InteractiveLlamaStackDemo:
    def __init__(self, llamastack_url: str, keycloak_url: str):
        self.llamastack_url = llamastack_url.rstrip('/')
        self.keycloak_url = keycloak_url.rstrip('/')
        self.realm = "llamastack-demo"
        self.client_id = "llamastack"
        self.token = None
        
        # Models to test
        self.models_to_test = [
            {"id": "vllm-inference/llama-3-2-3b", "name": "vLLM Llama 3.2 3B"},
            {"id": "openai/gpt-4o-mini", "name": "OpenAI GPT-4o-mini"},
            {"id": "openai/gpt-4o", "name": "OpenAI GPT-4o"}
        ]
    
    def get_user_credentials(self) -> tuple[str, str]:
        """Prompt user for credentials"""
        print("\n?? Please enter your credentials")
        print("=" * 50)
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        return username, password
    
    def get_token(self, username: str, password: str, client_secret: str) -> Optional[str]:
        """Get OAuth token from Keycloak"""
        token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        
        data = {
            'client_id': self.client_id,
            'client_secret': client_secret,
            'username': username,
            'password': password,
            'grant_type': 'password'
        }
        
        try:
            print(f"\n?? Requesting token from Keycloak...")
            response = requests.post(token_url, data=data, verify=False, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                print("? Token obtained successfully")
                return token_data.get('access_token')
            else:
                print(f"? Failed to get token: HTTP {response.status_code}")
                print(f"   {response.text}")
                return None
        except Exception as e:
            print(f"? Error getting token: {e}")
            return None
    
    def decode_token_claims(self, token: str) -> Dict[str, Any]:
        """Decode JWT token to show claims"""
        import base64
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            
            payload = parts[1]
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.b64decode(payload)
            return json.loads(decoded)
        except Exception as e:
            print(f"Warning: Could not decode token: {e}")
            return {}
    
    def list_models(self) -> Optional[list]:
        """List available models"""
        print("\n?? Listing available models...")
        print("=" * 50)
        
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(
                f"{self.llamastack_url}/v1/models",
                headers=headers,
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                response_data = response.json()
                print(f"? Successfully retrieved model list")
                
                # Handle different response formats
                models = response_data
                if isinstance(response_data, dict):
                    models = response_data.get('data', response_data.get('models', []))
                
                if isinstance(models, list) and models:
                    print("   Available models:")
                    embedding_models = []
                    for model in models:
                        if isinstance(model, dict):
                            # Try different possible field names
                            model_id = model.get('model_id', model.get('id', model.get('identifier', 'unknown')))
                            model_type = model.get('model_type', model.get('type', 'unknown'))
                            provider_id = model.get('provider_id', '')
                            
                            # Combine provider and model ID if both exist
                            if provider_id and model_id != 'unknown':
                                full_id = f"{provider_id}/{model_id}"
                            else:
                                full_id = model_id
                            
                            print(f"   ? {full_id} ({model_type})")
                            
                            # Track embedding models for later use
                            if model_type == 'embedding':
                                embedding_models.append(model_id)
                        else:
                            print(f"   ? {model}")
                    
                    # Show embedding models specifically
                    if embedding_models:
                        print(f"\n   Available embedding models: {', '.join(embedding_models)}")
                    else:
                        print("\n   ⚠️  No embedding models found!")
                    
                    # Store models for later use
                    self._available_models = models
                    return models
                else:
                    print("   No models found")
                    self._available_models = []
                    return []
            else:
                print(f"? Failed to list models: HTTP {response.status_code}")
                print(f"   {response.text}")
                return None
        except Exception as e:
            print(f"? Error listing models: {e}")
            return None
    
    def test_model(self, model_id: str, model_name: str) -> bool:
        """Test access to a specific model"""
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Say Hi!!!"}],
            "max_tokens": 10
        }
        
        try:
            response = requests.post(
                f"{self.llamastack_url}/v1/openai/v1/chat/completions",
                headers=headers,
                json=data,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                print(f"   ? {model_name}: Access granted")
                try:
                    resp_data = response.json()
                    if 'choices' in resp_data and resp_data['choices']:
                        content = resp_data['choices'][0].get('message', {}).get('content', '')
                        print(f"      Response: {content}")
                except:
                    pass
                return True
            elif response.status_code == 403:
                print(f"   ? {model_name}: Access denied (HTTP 403)")
                return False
            else:
                print(f"   ? {model_name}: Failed (HTTP {response.status_code})")
                return False
        except Exception as e:
            print(f"   ? {model_name}: Error - {e}")
            return False
    
    def test_models(self):
        """Test access to all models"""
        print("\n?? Testing model access...")
        print("=" * 50)
        
        results = []
        for model in self.models_to_test:
            success = self.test_model(model['id'], model['name'])
            results.append((model['name'], success))
        
        return results
    
    
    def run_demo(self, client_secret: str) -> bool:
        """Run the interactive demo"""
        print("?? Interactive LlamaStack Authentication Demo")
        print("=" * 50)
        print(f"LlamaStack URL: {self.llamastack_url}")
        print(f"Keycloak URL: {self.keycloak_url}")
        print(f"Realm: {self.realm}")
        
        # Get credentials
        username, password = self.get_user_credentials()
        
        # Get token
        self.token = self.get_token(username, password, client_secret)
        if not self.token:
            return False
        
        # Show token claims
        claims = self.decode_token_claims(self.token)
        if claims:
            print(f"\n?? Token claims:")
            print(f"   Username: {claims.get('preferred_username', 'N/A')}")
            print(f"   Roles: {claims.get('llamastack_roles', 'N/A')}")
            import time
            print(f"   Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(claims.get('exp', 0)))}")
        
        # List models
        models = self.list_models()
        
        # Test all models
        model_results = self.test_models()
        
        # Focus on inference access control testing
        print("\n🤖 Testing Inference Access Control")
        print("=" * 50)
        print("This demonstrates how different user roles have different access to models.")
        
        # Summary
        print("\n?? Demo Summary")
        print("=" * 50)
        print(f"User: {username}")
        
        print("\nModel Access Results:")
        for model_name, success in model_results:
            status = "✅ Granted" if success else "❌ Denied"
            print(f"   {model_name}: {status}")
        
        print(f"\n📊 Access Control Summary:")
        granted_count = sum(1 for _, success in model_results if success)
        total_count = len(model_results)
        print(f"   Models accessible: {granted_count}/{total_count}")
        
        if granted_count == 0:
            print("   🔒 No model access - check user roles and policies")
        elif granted_count == total_count:
            print("   🔓 Full model access - user has admin-level permissions")
        else:
            print("   🔐 Partial model access - role-based restrictions working")
        
        print("\n? Demo completed!")
        return True

def main():
    parser = argparse.ArgumentParser(description="Interactive LlamaStack Authentication Demo")
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
        print("? Keycloak client secret is required")
        print("   Set KEYCLOAK_CLIENT_SECRET environment variable or use --client-secret")
        sys.exit(1)
    
    demo = InteractiveLlamaStackDemo(args.llamastack_url, args.keycloak_url)
    success = demo.run_demo(args.client_secret)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
