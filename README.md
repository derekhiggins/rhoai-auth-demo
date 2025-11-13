# RHOAI LlamaStack Keycloak Authentication Demo

This demo showcases role-based access control for LlamaStack using Keycloak authentication on Red Hat OpenShift AI (RHOAI).

This repository targets RHOAI Next on the main branch. For other releases, check the corresponding branches (e.g., rhoai-3.0).

## Overview

The demo features user personas with different access levels based on both roles and teams:
- **Admin** (platform-team): Full access to all resources and operations
- **Developer** (ml-team): Read models, create vector stores, manage files
- **Developer2** (ml-team): Same as developer - demonstrates team-based access
- **Developer3** (data-team): Same role as developer but DIFFERENT team - cannot access ml-team resources
- **User** (data-team): Read-only access to on-site models (vLLM, embedding models)

The demo showcases LlamaStack's multi-attribute access control, supporting:
- **Roles**: Traditional role-based access control (admin, developer, user)
- **Teams**: Group-based access control (platform-team, ml-team, data-team)

**Key Insight:** Vector store access is controlled by the `user in owners teams` policy:
- Developers can CREATE vector stores (role-based permission)
- Team members can READ/DELETE their team's vector stores (team-based permission)
- Developer3 (data-team) cannot access vector stores owned by developer (ml-team)

## Prerequisites

- OpenShift cluster with RHOAI installed
- LlamaStack operator deployed
- Keycloak instance running and accessible
- `oc` CLI tool configured and authenticated

## Quick Start

1. **Setup Environment**:
   ```bash
   cp vars.env.example vars.env
   vi vars.env  # Add your OpenAI API key and other settings
   source ./vars.env
   ```

2. **Deploy Keycloak** (if not already deployed):

   Create the Keycloak project and deploy:
   ```bash
   oc new-project keycloak
   oc process -f https://raw.githubusercontent.com/keycloak/keycloak-quickstarts/refs/heads/main/openshift/keycloak.yaml \
     -p APPLICATION_NAME=kc \
     -p KEYCLOAK_ADMIN=admin \
     -p KEYCLOAK_ADMIN_PASSWORD=$KEYCLOAK_ADMIN_PASSWORD \
     -p NAMESPACE=keycloak | oc create -f -
   ```

   Get the Keycloak URL and add it to `vars.env`:
   ```bash
   KEYCLOAK_URL=https://$(oc get route kc --template='{{ .spec.host }}')
   vi vars.env # Note: KEYCLOAK_ISSUER_URL uses http:// vs KEYCLOAK_URL uses https://
   ```

   Update the Frontend URL in Keycloak admin console:
   ```bash
   oc port-forward $(oc get pods -l application=kc -o name | head -n1) 8080:8080
   ```
   Navigate to http://localhost:8080 in your browser, log in with the Keycloak admin credentials, and update the Frontend URL to match `$KEYCLOAK_URL` (In Realm settings). 

3. **Configure Keycloak**:
   ```bash
   python scripts/setup-keycloak.py
   ```
   This will display the client secret. Copy it to your `vars.env` file.

4. **Deploy LlamaStack**:
   ```bash
   source vars.env  # Load environment variables
   ./scripts/deploy.sh
   ```

   Update  `$LLAMASTACK_URL` in vars.env with the "Access Url" output by the above script

5. **Run the Demo**:

   Interactive demo (single user):
   ```bash
   source vars.env  # Load environment variables
   python scripts/interactive-demo.py
   ```

   Demo users (configured by setup-keycloak.py):
   - `admin` / `admin123` (role: admin, team: platform-team - full access)
   - `developer` / `dev123` (role: developer, team: ml-team - 2 models + data management)
   - `developer2` / `dev223` (role: developer, team: ml-team - same as developer)
   - `developer3` / `dev323` (role: developer, team: data-team - different team)
   - `user` / `user123` (role: user, team: data-team - vllm model only)
   
   **Team-Based Access Demo**: 
   - When logged in as `developer`, the demo creates a persistent vector store named `vs_mlteam_team` with a sample file attached
   - On every demo run (any user), the demo tests access to this vector store by:
     - **List access**: Can the user see it in `vector_stores.list()`?
   - **Access Results:**
     - `developer` (ml-team, creator): ✓ All access (owner)
     - `developer2` (ml-team): ✓ All access (same team via "user in owners teams")
     - `developer3` (data-team): ✗ NO access (different team)
     - `admin` (platform-team): ✓ All access (admin override)
     - `user` (data-team): ✗ NO access (different team + no create permission)
   - This demonstrates the "user in owners teams" policy: only team members can access team resources

## Architecture

The demo implements OAuth2 token-based authentication with multi-attribute access control:

### Access Control Attributes

LlamaStack supports multiple attribute categories for fine-grained access control:
- **roles**: Traditional role-based access (admin, developer, user)
- **teams**: Group/team membership (platform-team, ml-team, data-team)
- **projects**: Project-based access (not used in this demo)
- **namespaces**: Namespace-based access (not used in this demo)

Resources are accessible when users match the resource owner's attributes. The default policy requires users to have matching values in ALL attribute categories that exist on the resource. 

**This demo demonstrates both:**
1. **Role-based rules**: Explicit permissions based on user roles (e.g., "user with developer in roles")
2. **Team-based rules**: Access to team-owned resources via `user in owners teams` policy

The vector store access pattern showcases this hybrid approach:
- Role grants CREATE permission
- Team membership grants READ/DELETE permission to owned resources

### Permission Matrix

| Resource Type          | User    | Developer      | Admin       | Notes |
|------------------------|---------|----------------|-------------|-------|
| vLLM Models            | Read    | Read           | Full (CRD)  | Role-based |
| Embedding Models       | Read    | Read           | Full (CRD)  | Role-based |
| OpenAI Models          | -       | Read           | Full (CRD)  | Role-based |
| Files                  | -       | Full (CRD)     | Full (CRD)  | Role-based |
| Vector Stores          | -       | Create only    | Full (CRD)  | **Team-based R/D** |
| Vector Store Files     | -       | Team-based     | Full (CRD)  | **Team-based** |
| MCP Servers            | Read    | Read           | Full (CRD)  | Role-based |
| SQL Records            | -       | Read           | Full (CRD)  | Role-based |

**Legend:** CRD = Create, Read, Delete

**Key Access Control Pattern:**
- **Vector Stores**: Developers can CREATE vector stores. Reading and deleting is controlled by the `user in owners teams` policy
  - Example: developer (ml-team) creates `vs_mlteam_team` → developer2 (ml-team) can read/delete it
  - Example: developer3 (data-team) CANNOT read/delete `vs_mlteam_team` (different team)
- This demonstrates how team-based access control works alongside role-based permissions

## Scripts

### `setup-keycloak.py`
Automatically configures Keycloak for the demo. Creates:
- Realm (llamastack-demo)
- Client (llamastack)
- Roles (admin, developer, user)
- Groups/Teams (platform-team, ml-team, data-team)
- Demo users with role and team assignments
- Protocol mappers for both roles and teams

Displays the client secret needed for authentication.

### `deploy.sh`
Deploys the LlamaStack distribution to OpenShift. Creates ConfigMaps from the run configuration, deploys the LlamaStackDistribution resource, creates the route, and waits for the deployment to be ready.

### `interactive-demo.py`
Interactive authentication demo that prompts for user credentials, obtains OAuth tokens from Keycloak, and tests access to various resources based on role and team permissions. Demonstrates:

o Model access across different providers (vLLM, OpenAI)
o File operations (upload, list, delete)
o Vector store operations (create, delete)
o Vector store file attachments (end-to-end workflow)
o **Team-based access control** (Vector Stores):
  - Access model: CREATE (role-based) + READ/DELETE (team-based via "user in owners teams")
  - When logged in as `developer`: Creates persistent vector store `vs_mlteam_team` (ml-team owned) with a sample file
  - For ALL users: Tests access with three operations:
    - `vector_stores.list()` - Can the user see the vector store in the list?
  - **Expected results:**
    - developer/developer2 (ml-team): ✓ All operations work (team access)
    - developer3 (data-team): ✗ All operations denied (different team)
    - admin: ✓ All operations work (admin override)
    - user: ✗ All operations denied (no create + different team)
  - Demonstrates "user in owners teams" policy in action
  - Run with different users to see team-based isolation
o Responses API with MCP server tools (demonstrates external tool integration)

All demonstrations use only the OpenAI Python client for API interactions.

## MCP Server Integration

The demo includes integration with the DeepWiki MCP (Model Context Protocol) server, which provides three tools:
- `ask_question`: Query knowledge bases
- `read_wiki_structure`: Read wiki structure information
- `read_wiki_contents`: Read wiki content

The demo uses the `responses.create()` API with MCP tools to demonstrate how models can dynamically connect to external MCP servers at runtime. The MCP server URL (`https://mcp.deepwiki.com/mcp`) is provided directly in the API call, allowing flexible integration with external services. The demo queries the deepwiki server about the llamastack/llama-stack project to show real-world MCP tool usage.

## Development Notes

This demo was developed through multiple iterations using Cursor agent alongside manual editing and debugging. The process involved several failed iterations, manual debugging of issues, and providing guidance to Cursor about how certain components worked. The combination of AI assistance and hands-on refinement helped create a working demo. Your mileage may vary.
