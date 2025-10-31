# RHOAI LlamaStack Keycloak Authentication Demo

This demo showcases role-based access control for LlamaStack using Keycloak authentication on Red Hat OpenShift AI (RHOAI).

## Overview

The demo features three user personas with different access levels:
- **Admin**: Full access to all models (vLLM + OpenAI)
- **Data Science**: Access to all inference models
- **Other**: Basic inference access (vLLM only)

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

2. **Configure Keycloak**:
   ```bash
   python scripts/setup-keycloak.py
   ```
   This will display the client secret. Copy it to your `vars.env` file.

3. **Deploy LlamaStack**:
   ```bash
   source vars.env  # Load environment variables
   ./scripts/deploy.sh
   ```

4. **Run the Demo**:

   Interactive demo (single user):
   ```bash
   python scripts/interactive-demo.py
   ```

   Full automated demo (all users):
   ```bash
   python scripts/auth-demo.py
   ```

## Architecture

The demo implements OAuth2 token-based authentication with role-based access control:

```
???????????????????????????????????
?          Resources              ?
???????????????????????????????????
? vLLM Model (llama-3-2-3b)       ? ? All authenticated users
? OpenAI GPT-4o-mini              ? ? datascience, admin
? OpenAI GPT-4o                   ? ? admin only
? Agents API (full access)        ? ? admin only
? Agents API (create/read)        ? ? datascience
? Agents API (read-only)          ? ? basic
???????????????????????????????????
```
