# RHOAI LlamaStack Keycloak Authentication Demo

This demo showcases role-based access control for LlamaStack using Keycloak authentication on Red Hat OpenShift AI (RHOAI).

This repository targets RHOAI Next on the main branch. For other releases, check the corresponding branches (e.g., rhoai-3.0).

## Overview

The demo features three user personas with different access levels:
- **Admin**: Full access to all resources and operations
- **Developer**: Read all models, manage vector stores and tool groups
- **User**: Read-only access to free/shared models (vLLM, embedding models)

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
   - `admin` / `admin123` (admin role - full access)
   - `developer` / `dev123` (developer role - all models + data management)
   - `user` / `user123` (user role - free models only)

## Architecture

The demo implements OAuth2 token-based authentication with role-based access control:

| Resource Type          | User    | Developer | Admin       |
|------------------------|---------|-----------|-------------|
| vLLM Models            | Read    | Read      | Full (CRD)  |
| Embedding Models       | Read    | Read      | Full (CRD)  |
| OpenAI Models          | -       | Read      | Full (CRD)  |
| Files                  | -       | Full (CRD)| Full (CRD)  |
| Vector Stores          | -       | Full (CRD)| Full (CRD)  |
| Vector Store Files     | -       | Full (CRD)| Full (CRD)  |
| Tool Groups            | -       | Read      | Full (CRD)  |
| SQL Records            | -       | Read      | Full (CRD)  |
| Scoring Functions      | -       | Read      | Full (CRD)  |

**Legend:** CRD = Create, Read, Delete

## Scripts

### `setup-keycloak.py`
Automatically configures Keycloak for the demo. Creates the realm, client, roles (admin, developer, user), demo users, and protocol mappers. Displays the client secret needed for authentication.

### `deploy.sh`
Deploys the LlamaStack distribution to OpenShift. Creates ConfigMaps from the run configuration, deploys the LlamaStackDistribution resource, creates the route, and waits for the deployment to be ready.

### `interactive-demo.py`
Interactive authentication demo that prompts for user credentials, obtains OAuth tokens from Keycloak, and tests access to various resources based on role permissions. Demonstrates:

o Model access across different providers (vLLM, OpenAI)
o File operations (upload, list, delete)
o Vector store operations (create, delete)
o Vector store file attachments (end-to-end workflow)

## Development Notes

This demo was developed through multiple iterations using Cursor agent alongside manual editing and debugging. The process involved several failed iterations, manual debugging of issues, and providing guidance to Cursor about how certain components worked. The combination of AI assistance and hands-on refinement helped create a working demo. Your mileage may vary.
