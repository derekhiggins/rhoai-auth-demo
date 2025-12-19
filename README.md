# RHOAI LlamaStack Keycloak Authentication Demo

This demo showcases role-based access control for LlamaStack using Keycloak authentication on Red Hat OpenShift AI (RHOAI).

## Overview

The demo features three user personas with different access levels:
- **Admin**: Full access to all models
- **Data Science**: Access to vllm and GPT-4o-mini
- **Basic**: Basic inference access (vLLM only)

## Prerequisites

- OpenShift cluster with RHOAI installed
- LlamaStack operator deployed
- Keycloak instance running and accessible
- `oc` CLI tool configured and authenticated
- Python 3.x with virtual environment support (for running test scripts)

## Quick Start

1. **Setup Environment**:
   ```bash
   cp vars.env.example vars.env
   vi vars.env  # Add your OpenAI API key and other settings
   source ./vars.env
   ```

   **Setup Python Environment** (for running test scripts):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On fish shell: source venv/bin/activate.fish
   pip install -r requirements.txt
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

   RAG test (requires vector store provider configured):
   ```bash
   source vars.env  # Load environment variables
   source venv/bin/activate  # Activate virtual environment if not already active
   python scripts/rag-test.py
   ```

   Demo users (configured by setup-keycloak.py):
   - `admin-user` / `admin123` (admin role - full access to all models)
   - `datascience-user` / `ds123` (datascience role - vllm and gpt-4o-mini)
   - `basic-user` / `basic123` (basic role - vllm only)

## Architecture

The demo implements OAuth2 token-based authentication with role-based access control:

```
?????????????????????????????????
?          Resources              ?
???????????????????????????????????
? vLLM Model (llama-3-2-3b)       ? ? All authenticated users
? OpenAI GPT-4o-mini              ? ? datascience, admin
? OpenAI GPT-4o                   ? ? admin only
?????????????????????????????????
```

## Scripts

### `setup-keycloak.py`
Automatically configures Keycloak for the demo. Creates the realm, client, roles (admin, datascience, basic), demo users, and protocol mappers. Displays the client secret needed for authentication.

### `deploy.sh`
Deploys the LlamaStack distribution to OpenShift. Creates ConfigMaps from the run configuration, deploys the LlamaStackDistribution resource, creates the route, and waits for the deployment to be ready.

### `interactive-demo.py`
Interactive authentication demo that prompts for user credentials, obtains OAuth tokens from Keycloak, and tests access to various models based on role permissions. Shows which models each user role can access.

### `rag-test.py`
RAG (Retrieval Augmented Generation) test script that validates LlamaStack's vector store and RAG functionality. The script creates a vector store, inserts sample documents, and performs RAG queries to verify end-to-end RAG capabilities.

**Usage:**
```bash
source vars.env  # Load environment variables
python scripts/rag-test.py [options]
```

**Options:**
- `--llamastack-url URL` - LlamaStack server URL (default: `http://localhost:8321`, env: `LLAMASTACK_URL`)
- `--inference-model MODEL` - Inference model for RAG generation (default: `vllm-inference/llama-3-2-3b`, env: `INFERENCE_MODEL`)
- `--embedding-model MODEL` - Embedding model for vector store (default: `sentence-transformers/nomic-ai/nomic-embed-text-v1.5`, env: `EMBEDDING_MODEL`)
- `--embedding-dimension DIM` - Dimension of embedding vectors (default: `768`, env: `EMBEDDING_DIMENSION`)
- `--vector-store-provider PROVIDER` - Vector store provider (default: `milvus`, env: `VECTOR_STORE_PROVIDER`)

**What it does:**
1. Creates a vector store with the specified embedding model and provider
2. Inserts sample documents into the vector store
3. Performs RAG queries to retrieve relevant context and generate answers
4. Validates that the RAG pipeline returns expected results

**Prerequisites:**
- Python virtual environment with dependencies installed (see `requirements.txt`)
- LlamaStack server running and accessible
- Vector store provider (e.g., Milvus) configured and available

## Development Notes

This demo was developed through multiple iterations using Cursor agent alongside manual editing and debugging. The process involved several failed iterations, manual debugging of issues, and providing guidance to Cursor about how certain components worked. The combination of AI assistance and hands-on refinement helped create a working demo. Your mileage may vary.
