#!/bin/bash
set -e

if [ -f "$(dirname "$0")/../vars.env" ]; then
    echo "📋 Loading environment variables from vars.env file..."
    source "$(dirname "$0")/../vars.env"
else
    echo "   Create vars.env file from vars.env.example for environment-specific configuration."
    exit 1
fi

# Deploy LlamaStack Auth Demo to OpenShift
echo "🚀 Deploying LlamaStack Auth Demo to OpenShift..."

# Check if we're logged into OpenShift
if ! oc whoami &>/dev/null; then
    echo "❌ Not logged into OpenShift. Please run 'oc login' first."
    exit 1
fi

# Check if we're in the correct namespace
CURRENT_PROJECT=$(oc project -q 2>/dev/null || echo "")
if [ "$CURRENT_PROJECT" != "$OPENSHIFT_NAMESPACE" ]; then
    echo "📋 Switching to $OPENSHIFT_NAMESPACE namespace..."
    oc project "$OPENSHIFT_NAMESPACE" || {
        echo "❌ Failed to switch to $OPENSHIFT_NAMESPACE namespace"
        echo "   Make sure you have access to this namespace"
        exit 1
    }
fi

# Deploy ConfigMap from config file
echo "📦 Creating ConfigMap from config/run.yaml..."
F=$(mktemp)
cat config/run.yaml | envsubst > $F
oc create configmap "${LLAMASTACK_DISTRIBUTION_NAME:-llamastack-auth-demo}-config" --from-file=run.yaml=$F -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -
rm $F

# Deploy LlamaStack Distribution
echo "🦙 Creating LlamaStack Distribution..."
envsubst < config/llamastack-distribution.yaml | oc apply -f -

# Create Route
echo "🌐 Creating Route..."
envsubst < config/route.yaml | oc apply -f -

# Wait for deployment to be ready
echo "⏳ Waiting for LlamaStack to be ready..."
oc wait --for=jsonpath='{.status.phase}'=Ready llamastackdistribution/"${LLAMASTACK_DISTRIBUTION_NAME:-llamastack-auth-demo}" -n "$NAMESPACE" --timeout=300s

# Get the route URL
ROUTE_URL=$(oc get route "${LLAMASTACK_DISTRIBUTION_NAME:-llamastack-auth-demo}" -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ -n "$ROUTE_URL" ]; then
    echo "✅ LlamaStack Auth Demo deployed successfully!"
    echo "🔗 Access URL: https://$ROUTE_URL"
else
    echo "⚠️  Deployment created but route not found. Check the deployment status:"
    echo "   oc get llamastackdistribution llamastack-auth-demo"
fi
