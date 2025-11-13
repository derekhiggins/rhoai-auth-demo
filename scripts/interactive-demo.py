#!/usr/bin/env python3
"""
Interactive LlamaStack Authentication Demo

This script demonstrates multi-attribute access control with roles and teams:
- user: Read-only access to free/shared models (vLLM, embedding models)
- developer: Read models + CREATE vector stores and files
- admin: Full access to all resources

Team-based access control:
- Vector stores: Developers CREATE, teams READ/DELETE via "user in owners teams"
- developer (ml-team) creates vector store → developer2 (ml-team) can access
- developer3 (data-team) CANNOT access ml-team vector stores

Demonstrates RBAC and team-based access using only the OpenAI Python client.

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
                print(f"   Available models({len(models)}):")
                for model in models[:10]:
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

    def test_file_operations(self) -> tuple[dict, Optional[str]]:
        """Test file upload and list operations (keeps file for vector store test)"""
        print("\n   Testing file operations...")
        print("=" * 50)

        results = {
            'upload': False,
            'list': False,
        }

        file_id = None
        test_content = f"Sample document for RBAC testing - {int(time.time())}"

        # Test UPLOAD
        try:
            import io
            file_obj = self.openai_client.files.create(
                file=("test-rbac.txt", io.BytesIO(test_content.encode())),
                purpose="assistants"
            )
            file_id = file_obj.id
            print(f"   o File Upload: Access granted (ID: {file_id})")
            results['upload'] = True

        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   o File Upload: Access denied (403)")
            else:
                print(f"   o File Upload: Error - {e}")
            results['upload'] = False

        # Test LIST
        try:
            files_list = self.openai_client.files.list()
            print(f"   o File List: Access granted")
            results['list'] = True

        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   o File List: Access denied (403)")
            else:
                print(f"   o File List: Error - {e}")
            results['list'] = False

        # Note: File will be kept for vector store attachment test
        return results, file_id

    def cleanup_test_file(self, file_id: Optional[str]) -> bool:
        """Test file delete operation (cleanup after tests)"""
        print("\n   Testing file cleanup...")
        print("=" * 50)

        if not file_id:
            print(f"   o File Delete: Skipped (no file to delete)")
            return False

        try:
            self.openai_client.files.delete(file_id)
            print(f"   o File Delete: Access granted")
            return True

        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   o File Delete: Access denied (403)")
            else:
                print(f"   o File Delete: Error - {e}")
            return False

    def test_vector_store_operations(self, user_roles: list, test_file_id: Optional[str] = None) -> dict:
        """Test vector store create/delete operations and file attachments"""
        print("\n   Testing vector store operations...")
        print("=" * 50)

        results = {
            'create': False,
            'delete': False,
            'attach_file': False,
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

        # Test FILE ATTACHMENT (only if create succeeded and we have a file)
        if results['create'] and vector_store_id and test_file_id:
            try:
                vs_file = self.openai_client.vector_stores.files.create(
                    vector_store_id=vector_store_id,
                    file_id=test_file_id
                )
                print(f"   o Vector Store Attach File: Access granted")
                results['attach_file'] = True

            except Exception as e:
                error_str = str(e)
                if "403" in error_str or "Forbidden" in error_str:
                    print(f"   o Vector Store Attach File: Access denied (403)")
                elif "not found" in error_str.lower():
                    print(f"   o Vector Store Attach File: File not found (already deleted)")
                else:
                    print(f"   o Vector Store Attach File: Error - {e}")
                results['attach_file'] = False
        elif not test_file_id:
            print(f"   o Vector Store Attach File: Skipped (no file available)")

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

    def create_team_vector_store(self, username: str) -> dict:
        """Create persistent team vector store with a file (only for 'developer' user)"""
        results = {'created': False, 'already_exists': False, 'file_added': False}
        
        if username != "developer":
            return results
        
        print("\n   Creating persistent team vector store...")
        print("=" * 50)
        
        team_store_name = "vs_mlteam_team"
        
        # Check if it already exists
        try:
            stores_list = self.openai_client.vector_stores.list()
            for store in stores_list.data:
                if store.name == team_store_name:
                    print(f"   o Vector store '{team_store_name}' already exists (ID: {store.id})")
                    results['already_exists'] = True
                    return results
        except Exception as e:
            print(f"   o Error checking existing stores: {e}")
        
        # Create new vector store
        try:
            vector_store = self.openai_client.vector_stores.create(
                name=team_store_name,
                extra_body={"embedding_model": self.embedding_model}
            )
            print(f"   o Created vector store '{team_store_name}' (ID: {vector_store.id})")
            print(f"   o Owner: developer (ml-team)")
            results['created'] = True
            
            print(f"   o This store will persist for access testing by other users")
        except Exception as e:
            print(f"   o Failed to create vector store: {e}")
        
        return results

    def test_access_to_team_vector_store(self, username: str, user_teams: list) -> dict:
        """Test access to the persistent team vector store (all users)"""
        print("\n   Testing access to team-based vector store...")
        print("=" * 50)
        
        results = {'can_access': False, 'store_exists': False}
        team_store_name = "vs_mlteam_team"
        vector_store_id = None
        
        print(f"   o Current user: {username} (teams: {user_teams})")
        print(f"   o Testing access to '{team_store_name}' (owned by developer/ml-team)")
        
        # Try to list and find the vector store
        try:
            stores_list = self.openai_client.vector_stores.list()
            found = False
            for store in stores_list.data:
                if store.name == team_store_name:
                    found = True
                    vector_store_id = store.id
                    results['store_exists'] = True
                    results['can_access'] = True
                    print(f"   o ✓ LIST ACCESS: Vector store is visible in list")
                    print(f"     Store ID: {store.id}, Name: {store.name}")
                    break
            
            if not found:
                results['can_access'] = False
                print(f"   o ✗ LIST ACCESS: Vector store not visible in list")
                if "ml-team" not in user_teams:
                    print(f"     Reason: User is not in ml-team (owner's team)")
                else:
                    print(f"     Note: Store may not exist yet (run as 'developer' first)")
            return results
        
        except Exception as e:
            error_str = str(e)
            results['can_access'] = False
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   o ✗ LIST ACCESS: 403 Forbidden")
            else:
                print(f"   o Error listing stores: {e}")
                return results

    def test_responses_with_mcp(self) -> dict:
        """Test responses API with MCP server tools"""
        print("\n   Testing responses with MCP tools...")
        print("=" * 50)

        results = {
            'responses_with_mcp': False,
        }

        # Test responses.create with MCP server
        try:
            response = self.openai_client.responses.create(
                model="vllm-inference/llama-3-2-3b",
                tools=[
                    {
                        "type": "mcp",
                        "server_label": "deepwiki",
                        "server_description": "DeepWiki MCP server for wiki queries",
                        "server_url": "https://mcp.deepwiki.com/mcp",
                        "require_approval": "never",
                    }
                ],
                input="What version of python is used in the llamastack/llama-stack project, be brief and to the point? Make sure to use the deepwiki ask_question tool to answer the question.",
                stream=False,
            )

            print(f"   o Responses with MCP Tools: Access granted")
            if hasattr(response, 'output_text') and response.output_text:
                print(f"      Response: {response.output_text[:100]}...")
            results['responses_with_mcp'] = True

        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   o Responses with MCP Tools: Access denied (403)")
            else:
                print(f"   o Responses with MCP Tools: Error - {e}")
            results['responses_with_mcp'] = False

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
        user_teams = []
        if claims:
            print(f"\n   Token claims:")
            print(f"   Username: {claims.get('preferred_username', 'N/A')}")
            user_roles = claims.get('llamastack_roles', [])
            user_teams = claims.get('llamastack_teams', [])
            print(f"   Roles: {user_roles}")
            print(f"   Teams: {user_teams}")
            print(f"   Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(claims.get('exp', 0)))}")

        print("\n" + "=" * 50)
        print("ROLE-BASED ACCESS CONTROL TEST")
        print("=" * 50)

        # List models
        self.list_models()

        # Test all models
        model_results = self.test_models()

        # Test file operations
        file_results, test_file_id = self.test_file_operations()

        # Test vector store operations (with file if available)
        vector_results = self.test_vector_store_operations(user_roles, test_file_id)

        # Create persistent team vector store (only for 'developer' user)
        team_create_results = self.create_team_vector_store(username)

        # Test access to team vector store (all users)
        team_access_results = self.test_access_to_team_vector_store(username, user_teams)

        # Test responses API with MCP tools
        mcp_results = self.test_responses_with_mcp()

        # Cleanup: test file delete
        file_delete_result = self.cleanup_test_file(test_file_id)
        file_results['delete'] = file_delete_result

        # Print summary
        self.print_summary(user_roles, user_teams, model_results, file_results, vector_results, mcp_results, team_create_results, team_access_results)

        return True

    def print_summary(self, user_roles: list, user_teams: list, model_results: list, file_results: dict, vector_results: dict, mcp_results: dict, team_create_results: dict, team_access_results: dict):
        """Print access control summary"""
        print("\n" + "=" * 50)
        print("ACCESS SUMMARY")
        print("=" * 50)
        print(f"User Roles: {user_roles}")
        print(f"User Teams: {user_teams}")
        print(f"\nModel Access:")
        for model_name, success in model_results:
            status = "ALLOWED" if success else "DENIED"
            print(f"  {status:8} - {model_name}")

        print(f"\nFile Operations:")
        for op, success in file_results.items():
            status = "ALLOWED" if success else "DENIED"
            print(f"  {status:8} - {op.capitalize()}")

        print(f"\nVector Store Operations:")
        for op, success in vector_results.items():
            status = "ALLOWED" if success else "DENIED"
            op_name = op.replace('_', ' ').capitalize()
            print(f"  {status:8} - {op_name}")

        print(f"\nTeam-Based Vector Store (vs_mlteam_team):")
        if team_create_results.get('created'):
            print(f"  CREATED    - Persistent team vector store (developer only)")
            if team_create_results.get('file_added'):
                print(f"  FILE ADDED - Sample file attached to vector store")
        elif team_create_results.get('already_exists'):
            print(f"  EXISTS     - Team vector store already present")
        
        if team_access_results:
            can_list = team_access_results.get('can_access', False)
            can_retrieve = team_access_results.get('can_retrieve', False)
            can_list_files = team_access_results.get('can_list_files', False)
            list_status = "YES" if can_list else "NO"
            retrieve_status = "YES" if can_retrieve else "NO"
            files_status = "YES" if can_list_files else "NO"
            print(f"  List Store:  {list_status:3} - Can see in list()")

        print(f"\nMCP Operations:")
        for op, success in mcp_results.items():
            status = "ALLOWED" if success else "DENIED"
            op_name = op.replace('_', ' ').capitalize()
            print(f"  {status:8} - {op_name}")

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
