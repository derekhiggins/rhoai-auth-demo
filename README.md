# RHOAI LlamaStack Keycloak Authentication Demo

This demo showcases role-based access control for LlamaStack using Keycloak authentication on Red Hat OpenShift AI (RHOAI).

## Overview

The demo features four user personas with different access levels:
- **Admin**: Full access to all models
- **Data Science**: Access to vllm and GPT-4o-mini
- **Basic**: Basic inference access (vLLM only)

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
   vi vars.env # Note: KEYCLOAK_ISSUER_URL with http:// vs KEYCLOAK_JWKS_URL with https://
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

## Development Notes

This demo was developed through multiple iterations using Cursor agent alongside manual editing and debugging. The process involved several failed iterations, manual debugging of issues, and providing guidance to Cursor about how certain components worked. The combination of AI assistance and hands-on refinement helped create a working demo. Your mileage may vary.
