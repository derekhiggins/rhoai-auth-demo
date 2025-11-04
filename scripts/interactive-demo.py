#!/usr/bin/env python3
"""
Interactive LlamaStack Authentication Demo

This script demonstrates role-based access control with three user roles:
- user: Read-only access to free/shared models (vLLM, embedding models)
- developer: Read all models + manage vector stores
- admin: Full access to all resources

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
import httpx
from typing import Optional, Dict, Any
import getpass
import time
from openai import OpenAI

# Disable SSL warnings for demo purposes
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class InteractiveLlamaStackDemo:
    def __init__(self, llamastack_url: str, keycloak_url: str):
        self.llamastack_url = llamastack_url.rstrip('/')
        self.keycloak_url = keycloak_url.rstrip('/')
        self.realm = "llamastack-demo"
        self.client_id = "llamastack"
        self.token = None
        self.openai_client = None

        # Models to test
        self.models_to_test = [
            {"id": "vllm-inference/llama-3-2-3b", "name": "vLLM Llama 3.2 3B", "expected_roles": ["user", "developer", "admin"]},
            {"id": "openai/gpt-4o-mini", "name": "OpenAI GPT-4o-mini", "expected_roles": ["developer", "admin"]},
            {"id": "openai/gpt-4o", "name": "OpenAI GPT-4o", "expected_roles": ["admin"]}
        ]
        
        self.embedding_model = "sentence-transformers/ibm-granite/granite-embedding-125m-english"

    def get_user_credentials(self) -> tuple[str, str]:
        """Prompt user for credentials"""
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

    def initialize_openai_client(self):
        """Initialize OpenAI client with the authentication token"""
        self.openai_client = OpenAI(
            base_url=f"{self.llamastack_url}/v1",
            api_key=self.token,
            http_client=httpx.Client(verify=False)
        )

    def list_models(self) -> Optional[list]:
        """List available models"""
        print("=" * 50)

        try:
            models_response = self.openai_client.models.list()
            print(f"? Successfully retrieved model list")

            # Convert to list of dicts
            models = []
            if hasattr(models_response, 'data'):
                for model in models_response.data:
                    if hasattr(model, '__dict__'):
                        model_dict = {k: v for k, v in model.__dict__.items() if not k.startswith('_')}
                        models.append(model_dict)
                    else:
                        models.append(model)

            if models:
                print("   Available models:")
                for model in models:
                    if isinstance(model, dict):
                        model_id = model.get('id', 'unknown')
                        print(f"   ? {model_id}")
                    else:
                        model_id = getattr(model, 'id', str(model))
                        print(f"   ? {model_id}")

                # Store models for later use
                self._available_models = models
                return models
            else:
                print("   No models found")
                self._available_models = []
                return []
        except Exception as e:
            print(f"? Error listing models: {e}")
            return None

    def test_model(self, model_id: str, model_name: str) -> bool:
        """Test access to a specific model"""
        try:
            response = self.openai_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Say Hi!!!"}],
                max_tokens=10
            )

            print(f"   ? {model_name}: Access granted")
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                print(f"      Response: {content}")
            return True
        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   ? {model_name}: Access denied (403)")
                return False
            else:
                print(f"   ? {model_name}: Error - {e}")
                return False

    def test_models(self):
        """Test access to all models"""
        print("\n   Testing model access...")
        print("=" * 50)

        results = []
        for model in self.models_to_test:
            success = self.test_model(model['id'], model['name'])
            results.append((model['name'], success))

        return results

    def test_vector_store_operations(self, user_roles: list) -> dict:
        """Test vector store create/delete operations"""
        print("\n   Testing vector store operations...")
        print("=" * 50)
        
        results = {
            'create': False,
            'delete': False,
        }
        
        test_store_name = f"demo-test-store-{int(time.time())}"
        vector_store_id = None
        
        # Test CREATE
        try:
            vector_store = self.openai_client.vector_stores.create(
                name=test_store_name,
                extra_body={"embedding_model": self.embedding_model}
            )
            
            vector_store_id = vector_store.id
            print(f"   o Vector Store Create: Access granted (ID: {vector_store_id})")
            results['create'] = True
                
        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   o Vector Store Create: Access denied (403)")
                results['create'] = False
            else:
                print(f"   o Vector Store Create: Error - {e}")
                results['create'] = False
        
        # Test DELETE (only if create succeeded)
        if results['create'] and vector_store_id:
            try:
                self.openai_client.vector_stores.delete(vector_store_id=vector_store_id)
                print(f"   o Vector Store Delete: Access granted")
                results['delete'] = True
                    
            except Exception as e:
                error_str = str(e)
                if "403" in error_str or "Forbidden" in error_str:
                    print(f"   o Vector Store Delete: Access denied (403)")
                    results['delete'] = False
                else:
                    print(f"   o Vector Store Delete: Error - {e}")
                    results['delete'] = False
        
        return results


    def run_demo(self, client_secret: str) -> bool:
        """Run the interactive demo"""
        print("=" * 50)
        print(f"LlamaStack URL: {self.llamastack_url}")
        print(f"Keycloak URL: {self.keycloak_url}")
        print(f"Realm: {self.realm}")

        # Get credentials
        username, password = self.get_user_credentials()

        # Get token
        self.token = self.get_token(username, password, client_secret)
        open("token-"+username, "w").write(self.token or "")
        if not self.token:
            return False

        # Initialize OpenAI client
        self.initialize_openai_client()

        # Show token claims
        claims = self.decode_token_claims(self.token)
        user_roles = []
        if claims:
            print(f"\n   Token claims:")
            print(f"   Username: {claims.get('preferred_username', 'N/A')}")
            user_roles = claims.get('llamastack_roles', [])
            print(f"   Roles: {user_roles}")
            print(f"   Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(claims.get('exp', 0)))}")

        print("\n" + "=" * 50)
        print("ROLE-BASED ACCESS CONTROL TEST")
        print("=" * 50)

        # List models
        self.list_models()

        # Test all models
        model_results = self.test_models()

        # Test vector store operations
        vector_results = self.test_vector_store_operations(user_roles)

        # Print summary
        self.print_summary(user_roles, model_results, vector_results)

        return True

    def print_summary(self, user_roles: list, model_results: list, vector_results: dict):
        """Print access control summary"""
        print("\n" + "=" * 50)
        print("ACCESS SUMMARY")
        print("=" * 50)
        print(f"User Roles: {user_roles}")
        print(f"\nModel Access:")
        for model_name, success in model_results:
            status = "ALLOWED" if success else "DENIED"
            print(f"  {status:8} - {model_name}")
        
        print(f"\nVector Store Operations:")
        for op, success in vector_results.items():
            status = "ALLOWED" if success else "DENIED"
            print(f"  {status:8} - {op.capitalize()}")
        
        print("\n" + "=" * 50)

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
