#!/usr/bin/env python3
"""
Interactive LlamaStack Authentication Demo

Demonstrates RBAC with roles (user/developer/admin) and team-based access control.
Uses the OpenAI Python client to test access to models, files, and vector stores.

Usage:
    python interactive-demo.py [--user USERNAME] [--tests TEST_LIST] [OPTIONS]

Authentication:
    --user USERNAME              Username for authentication (will prompt if not provided)
    If a valid cached token exists for the user, no password prompt is shown.

Test selection:
    --tests all                  Run all tests (default)
    --tests models               Run only model access tests
    --tests team                 Run only team-based access tests
    --tests models,files         Run models and files tests
    --tests models,files,vectors Run multiple test suites

Available tests: models, files, vectors, mcp, team

Token caching:
    By default, tokens are cached in ~/.cache/llamastack-demo/ and reused if still valid.
    --no-cache                   Don't use cached tokens, always request new ones
    --cache-dir DIR              Use custom directory for token cache
"""

import os
import sys
import json
import argparse
import requests
import urllib3
import httpx
from typing import Optional, Dict, Any, Callable
import getpass
import time
from pathlib import Path
from openai import OpenAI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class InteractiveLlamaStackDemo:
    def __init__(self, llamastack_url: str, keycloak_url: str, cache_dir: Optional[str] = None):
        self.llamastack_url = llamastack_url.rstrip('/')
        self.keycloak_url = keycloak_url.rstrip('/')
        self.realm = "llamastack-demo"
        self.client_id = "llamastack"
        self.token = None
        self.openai_client = None

        # Token cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path.home() / ".cache" / "llamastack-demo"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.models_to_test = [
            {"id": "vllm-inference/llama-3-2-3b", "name": "vLLM Llama 3.2 3B"},
            {"id": "openai/gpt-4o-mini", "name": "OpenAI GPT-4o-mini"},
            {"id": "openai/gpt-4o", "name": "OpenAI GPT-4o"}
        ]
        self.embedding_model = "sentence-transformers/ibm-granite/granite-embedding-125m-english"

    def get_username(self) -> str:
        """Prompt user for username"""
        print("=" * 50)
        username = input("Username: ").strip()
        return username

    def get_password(self) -> str:
        """Prompt user for password"""
        password = getpass.getpass("Password: ")
        return password

    def get_token_cache_path(self, username: str) -> Path:
        """Get the cache file path for a specific user's token"""
        # Use a hash of the realm and keycloak URL to avoid conflicts
        import hashlib
        cache_key = hashlib.md5(f"{self.keycloak_url}:{self.realm}".encode()).hexdigest()[:8]
        return self.cache_dir / f"token_{username}_{cache_key}.json"

    def load_cached_token(self, username: str) -> Optional[str]:
        """Load token from cache if it exists and is still valid"""
        cache_file = self.get_token_cache_path(username)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)

            token = cache_data.get('access_token')
            expires_at = cache_data.get('expires_at', 0)

            # Check if token is still valid (with 60 second buffer)
            if token and time.time() < (expires_at - 60):
                # Verify token is actually valid by decoding it
                claims = self.decode_token_claims(token)
                if claims:
                    print(f"? Using cached token (expires in {int(expires_at - time.time())}s)")
                    return token
            else:
                print("? Cached token expired")
        except Exception as e:
            print(f"? Could not load cached token: {e}")

        return None

    def save_token_to_cache(self, username: str, token: str, expires_in: int):
        """Save token to cache with expiration time"""
        cache_file = self.get_token_cache_path(username)

        try:
            cache_data = {
                'access_token': token,
                'expires_at': time.time() + expires_in,
                'cached_at': time.time()
            }

            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)

            print(f"? Token cached for future use")
        except Exception as e:
            print(f"? Warning: Could not cache token: {e}")

    def _handle_operation(self, operation: Callable, operation_name: str, success_msg: str = None) -> bool:
        """Common error handler for API operations"""
        try:
            result = operation()
            if hasattr(result, 'last_error') and result.last_error:
                print(f"   ? {operation_name} error: {result.last_error}")
                return False
            msg = success_msg or f"{operation_name}: Access granted"
            print(f"   o {msg}")
            return True
        except Exception as e:
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                print(f"   o {operation_name}: Access denied (403)")
            else:
                print(f"   o {operation_name}: Error - {e}")
            return False

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
                access_token = token_data.get('access_token')
                expires_in = token_data.get('expires_in', 300)

                print("? Token obtained successfully")

                # Cache the token
                self.save_token_to_cache(username, access_token, expires_in)

                return access_token
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
            if response.choices:
                print(f"      Response: {response.choices[0].message.content}")
            return True
        except Exception as e:
            status = "Access denied (403)" if "403" in str(e) or "Forbidden" in str(e) else f"Error - {e}"
            print(f"   ? {model_name}: {status}")
            return False

    def test_models(self):
        """Test access to all models"""
        print("\n   Testing model access...")
        print("=" * 50)
        return [(m['name'], self.test_model(m['id'], m['name'])) for m in self.models_to_test]

    def test_file_operations(self) -> tuple[dict, Optional[str]]:
        """Test file upload and list operations"""
        print("\n   Testing file operations...")
        print("=" * 50)

        results = {'upload': False, 'list': False}
        file_id = None

        # Test UPLOAD
        import io
        try:
            file_obj = self.openai_client.files.create(
                file=("test-rbac.txt", io.BytesIO(f"RBAC test - {int(time.time())}".encode())),
                purpose="assistants"
            )
            file_id = file_obj.id
            print(f"   o File Upload: Access granted (ID: {file_id})")
            results['upload'] = True
        except Exception as e:
            status = "Access denied (403)" if "403" in str(e) or "Forbidden" in str(e) else f"Error - {e}"
            print(f"   o File Upload: {status}")

        # Test LIST
        results['list'] = self._handle_operation(
            lambda: self.openai_client.files.list(),
            "File List"
        )

        return results, file_id

    def cleanup_test_file(self, file_id: Optional[str]) -> bool:
        """Test file delete operation"""
        print("\n   Testing file cleanup...")
        print("=" * 50)

        if not file_id:
            print(f"   o File Delete: Skipped (no file to delete)")
            return False

        return self._handle_operation(
            lambda: self.openai_client.files.delete(file_id),
            "File Delete"
        )

    def test_vector_store_operations(self, user_roles: list, test_file_id: Optional[str] = None) -> dict:
        """Test vector store create/delete operations and file attachments"""
        print("\n   Testing vector store operations...")
        print("=" * 50)

        results = {'create': False, 'delete': False, 'attach_file': False}
        vector_store_id = None

        # Test CREATE
        try:
            store = self.openai_client.vector_stores.create(
                name=f"demo-test-store-{int(time.time())}",
                extra_body={"embedding_model": self.embedding_model}
            )
            vector_store_id = store.id
            print(f"   o Vector Store Create: Access granted (ID: {vector_store_id})")
            results['create'] = True
        except Exception as e:
            status = "Access denied (403)" if "403" in str(e) or "Forbidden" in str(e) else f"Error - {e}"
            print(f"   o Vector Store Create: {status}")

        # Test FILE ATTACHMENT
        if results['create'] and vector_store_id and test_file_id:
            results['attach_file'] = self._handle_operation(
                lambda: self.openai_client.vector_stores.files.create(
                    vector_store_id=vector_store_id, file_id=test_file_id
                ),
                "Vector Store Attach File"
            )
        elif not test_file_id:
            print(f"   o Vector Store Attach File: Skipped (no file available)")

        # Test DELETE
        if results['create'] and vector_store_id:
            results['delete'] = self._handle_operation(
                lambda: self.openai_client.vector_stores.delete(vector_store_id=vector_store_id),
                "Vector Store Delete"
            )

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

        results = {'responses_with_mcp': False}

        def call_mcp():
            response = self.openai_client.responses.create(
                model="vllm-inference/llama-3-2-3b",
                tools=[{
                    "type": "mcp",
                    "server_label": "deepwiki",
                    "server_description": "DeepWiki MCP server for wiki queries",
                    "server_url": "https://mcp.deepwiki.com/mcp",
                    "require_approval": "never",
                }],
                input="What version of python is used in the llamastack/llama-stack project, be brief and to the point? Make sure to use the deepwiki ask_question tool to answer the question.",
                stream=False,
            )
            if hasattr(response, 'output_text') and response.output_text:
                print(f"      Response: {response.output_text[:100]}...")

        results['responses_with_mcp'] = self._handle_operation(call_mcp, "Responses with MCP Tools")
        return results


    def run_demo(self, client_secret: str, tests_to_run: set, use_cache: bool = True, username: Optional[str] = None) -> bool:
        """Run the interactive demo"""
        print("=" * 50)
        print(f"LlamaStack URL: {self.llamastack_url}")
        print(f"Keycloak URL: {self.keycloak_url}")
        print(f"Realm: {self.realm}")

        # Get username from parameter or prompt
        if not username:
            username = self.get_username()
        else:
            print("=" * 50)
            print(f"Username: {username}")

        # Try to load cached token first
        if use_cache:
            self.token = self.load_cached_token(username)

        # Get new token if cache miss or cache disabled
        if not self.token:
            # Only ask for password if we need to authenticate
            password = self.get_password()
            self.token = self.get_token(username, password, client_secret)
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
        print(f"ACCESS CONTROL TEST - Running: {', '.join(sorted(tests_to_run))}")
        print("=" * 50)

        # Initialize results
        model_results = []
        file_results = {}
        vector_results = {}
        mcp_results = {}
        team_create_results = {}
        team_access_results = {}
        test_file_id = None

        # Run models tests
        if 'models' in tests_to_run:
            # List models
            self.list_models()
            # Test all models
            model_results = self.test_models()

        # Run file tests
        if 'files' in tests_to_run:
            file_results, test_file_id = self.test_file_operations()

        # Run vector store tests
        if 'vectors' in tests_to_run:
            vector_results = self.test_vector_store_operations(user_roles, test_file_id)

        if 'files' in tests_to_run:
            # Cleanup: test file delete
            file_delete_result = self.cleanup_test_file(test_file_id)
            file_results['delete'] = file_delete_result

        # Run MCP tests
        if 'mcp' in tests_to_run:
            mcp_results = self.test_responses_with_mcp()

        # Run team tests
        if 'team' in tests_to_run:
            # Create persistent team vector store (only for 'developer' user)
            team_create_results = self.create_team_vector_store(username)
            # Test access to team vector store (all users)
            team_access_results = self.test_access_to_team_vector_store(username, user_teams)

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

        def print_results(title: str, results):
            print(f"\n{title}:")
            if isinstance(results, list):
                for name, success in results:
                    print(f"  {'ALLOWED' if success else 'DENIED':8} - {name}")
            else:
                for op, success in results.items():
                    op_name = op.replace('_', ' ').capitalize()
                    print(f"  {'ALLOWED' if success else 'DENIED':8} - {op_name}")

        if model_results:
            print_results("Model Access", model_results)
        if file_results:
            print_results("File Operations", file_results)
        if vector_results:
            print_results("Vector Store Operations", vector_results)

        print(f"\nTeam-Based Vector Store (vs_mlteam_team):")
        if team_create_results.get('created'):
            print(f"  CREATED    - Persistent team vector store (developer only)")
        elif team_create_results.get('already_exists'):
            print(f"  EXISTS     - Team vector store already present")

        if team_access_results:
            can_list = "YES" if team_access_results.get('can_access', False) else "NO"
            print(f"  List Store:  {can_list:3} - Can see in list()")

        if mcp_results:
            print_results("MCP Operations", mcp_results)
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
    parser.add_argument("--user",
                       default=None,
                       help="Username for authentication (will prompt if not provided)")
    parser.add_argument("--tests",
                       default="all",
                       help="Comma-separated list of tests to run: models,files,vectors,mcp,team (default: all)")
    parser.add_argument("--no-cache",
                       action="store_true",
                       help="Don't use cached tokens, always request new ones")
    parser.add_argument("--cache-dir",
                       default=None,
                       help="Directory to store cached tokens (default: ~/.cache/llamastack-demo)")

    args = parser.parse_args()

    if not args.client_secret:
        print("? Keycloak client secret is required")
        print("   Set KEYCLOAK_CLIENT_SECRET environment variable or use --client-secret")
        sys.exit(1)

    # Parse tests to run
    available_tests = {'models', 'files', 'vectors', 'mcp', 'team'}
    if args.tests.lower() == 'all':
        tests_to_run = available_tests
    else:
        requested_tests = {t.strip().lower() for t in args.tests.split(',')}
        invalid_tests = requested_tests - available_tests
        if invalid_tests:
            print(f"? Invalid test names: {', '.join(invalid_tests)}")
            print(f"   Available tests: {', '.join(sorted(available_tests))}")
            sys.exit(1)
        tests_to_run = requested_tests

    demo = InteractiveLlamaStackDemo(args.llamastack_url, args.keycloak_url, cache_dir=args.cache_dir)
    success = demo.run_demo(args.client_secret, tests_to_run, use_cache=not args.no_cache, username=args.user)

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
