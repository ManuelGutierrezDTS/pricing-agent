# 🚚 DTS Pricing Agent API

Advanced freight pricing analysis and validation system with FastAPI REST interface.

## 📋 Overview

This pricing agent analyzes freight loads, validates pricing against historical data, and provides intelligent recommendations through external APIs (DAT, GreenScreens, Google Maps).

### Key Features

- ✅ **Multi-equipment support** (Flatbed, Van, Reefer, Hotshot)
- ✅ **Multistop optimization** with routing
- ✅ **Historical data validation** (Unity Catalog)
- ✅ **External API integration** (DAT market data, GreenScreens AI)
- ✅ **Negotiation range calculation**
- ✅ **Accept/Reject recommendations** with confidence scores
- ✅ **FastAPI REST interface** with automatic documentation

---

## 🚀 Quick Start

### Local Development

#### 1. Clone the repository

```bash
git clone https://github.com/ManuelGutierrezDTS/pricing-agent.git
cd pricing-agent
```

#### 2. Create virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Configure environment variables

Create a `.env` file in the root directory:

```env
# DAT API
DAT_ORG_USERNAME=your_username
DAT_ORG_PASSWORD=your_password
DAT_USER_EMAIL=your_email
DAT_ORG_TOKEN_URL=https://...
DAT_USER_TOKEN_URL=https://...
DAT_RATE_LOOKUP_URL=https://...
DAT_FORECAST_URL=https://...

# GreenScreens API
GS_CLIENT_ID=your_client_id
GS_CLIENT_SECRET=your_client_secret
GS_AUTH_URL=https://...

# Google Maps API
GOOGLE_MAPS_API_KEY=your_api_key

# Azure Blob Storage (optional)
AZ_BLOB_ACCOUNT=databricksdts
AZ_BLOB_CONTAINER=databrickscontainer
AZ_BLOB_FILE=UnityCatalog_Tables.xlsx
AZ_BLOB_KEY=your_azure_key
```

#### 5. Run the API

```bash
# Development mode with auto-reload
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Or use the main script
python api.py
```

The API will be available at:
- **API Base**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🐳 Docker Deployment

### Build and run locally

```bash
# Build the image
docker build -t pricing-agent:latest .

# Run with docker-compose (recommended)
docker-compose up -d

# Or run directly
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name pricing-agent \
  pricing-agent:latest
```

### Test the container

```bash
# Health check
curl http://localhost:8000/health

# Test pricing analysis
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "proposed_price": 1500,
    "carrier_cost": "auto",
    "stops": [
      {"type": "PICKUP", "zip": "60160"},
      {"type": "DROP", "zip": "53703"}
    ],
    "customer_name": "SureBuilt",
    "equipment_type": "HOTSHOT",
    "weight": 6036
  }'
```

---

## ☁️ Azure Container Apps Deployment

### Prerequisites

1. Azure subscription
2. Azure CLI installed (`az --version`)
3. Azure Container Registry (ACR) created
4. Resource Group created

### Step 1: Azure Login

```bash
az login
az account set --subscription "YOUR_SUBSCRIPTION_ID"
```

### Step 2: Create Azure Container Registry (if not exists)

```bash
# Variables
RESOURCE_GROUP="rg-pricing-agent"
LOCATION="eastus"
ACR_NAME="acrpricingagent"  # Must be globally unique, lowercase only

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create container registry
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)

echo "ACR Login Server: $ACR_LOGIN_SERVER"
echo "ACR Username: $ACR_USERNAME"
echo "ACR Password: $ACR_PASSWORD"
```

### Step 3: Build and push Docker image to ACR

```bash
# Login to ACR
az acr login --name $ACR_NAME

# Build and push using Azure ACR build (recommended)
az acr build \
  --registry $ACR_NAME \
  --image pricing-agent:latest \
  --file Dockerfile \
  .

# Or build locally and push
docker build -t $ACR_LOGIN_SERVER/pricing-agent:latest .
docker push $ACR_LOGIN_SERVER/pricing-agent:latest
```

### Step 4: Create Container Apps Environment

```bash
# Install Container Apps extension
az extension add --name containerapp --upgrade

# Create Container Apps environment
ENVIRONMENT_NAME="env-pricing-agent"

az containerapp env create \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### Step 5: Deploy to Azure Container Apps

```bash
# Container App name
APP_NAME="pricing-agent-api"

# Create Container App
az containerapp create \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image $ACR_LOGIN_SERVER/pricing-agent:latest \
  --registry-server $ACR_LOGIN_SERVER \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2.0Gi
```

### Step 6: Configure environment variables (secrets)

```bash
# Add secrets
az containerapp secret set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --secrets \
    dat-org-username="YOUR_DAT_USERNAME" \
    dat-org-password="YOUR_DAT_PASSWORD" \
    dat-user-email="YOUR_DAT_EMAIL" \
    dat-org-token-url="YOUR_DAT_ORG_URL" \
    dat-user-token-url="YOUR_DAT_USER_URL" \
    dat-rate-lookup-url="YOUR_DAT_RATE_URL" \
    dat-forecast-url="YOUR_DAT_FORECAST_URL" \
    gs-client-id="YOUR_GS_CLIENT_ID" \
    gs-client-secret="YOUR_GS_CLIENT_SECRET" \
    gs-auth-url="YOUR_GS_AUTH_URL" \
    google-maps-api-key="YOUR_GOOGLE_API_KEY" \
    az-blob-account="YOUR_AZURE_STORAGE_ACCOUNT" \
    az-blob-container="YOUR_BLOB_CONTAINER" \
    az-blob-file="YOUR_BLOB_FILE" \
    az-blob-key="YOUR_AZURE_STORAGE_KEY"

# Update container app to use secrets
az containerapp update \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars \
    DAT_ORG_USERNAME=secretref:dat-org-username \
    DAT_ORG_PASSWORD=secretref:dat-org-password \
    DAT_USER_EMAIL=secretref:dat-user-email \
    DAT_ORG_TOKEN_URL=secretref:dat-org-token-url \
    DAT_USER_TOKEN_URL=secretref:dat-user-token-url \
    DAT_RATE_LOOKUP_URL=secretref:dat-rate-lookup-url \
    DAT_FORECAST_URL=secretref:dat-forecast-url \
    GS_CLIENT_ID=secretref:gs-client-id \
    GS_CLIENT_SECRET=secretref:gs-client-secret \
    GS_AUTH_URL=secretref:gs-auth-url \
    GOOGLE_MAPS_API_KEY=secretref:google-maps-api-key \
    AZ_BLOB_ACCOUNT=secretref:az-blob-account \
    AZ_BLOB_CONTAINER=secretref:az-blob-container \
    AZ_BLOB_FILE=secretref:az-blob-file \
    AZ_BLOB_KEY=secretref:az-blob-key
```

### Step 7: Get the public URL

```bash
# Get the FQDN
APP_URL=$(az containerapp show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn -o tsv)

echo "🚀 API URL: https://$APP_URL"
echo "📚 Docs: https://$APP_URL/docs"
echo "🏥 Health: https://$APP_URL/health"
```

### Step 8: Test deployment

```bash
# Health check
curl https://$APP_URL/health

# Test pricing analysis
curl -X POST https://$APP_URL/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "proposed_price": 1500,
    "carrier_cost": "auto",
    "stops": [
      {"type": "PICKUP", "zip": "60160"},
      {"type": "DROP", "zip": "53703"}
    ],
    "customer_name": "SureBuilt",
    "equipment_type": "HOTSHOT",
    "weight": 6036
  }'
```

---

## 🔄 CI/CD with GitHub Actions

### Setup GitHub Secrets

Go to your repository → Settings → Secrets and variables → Actions

Add the following secrets:

```
AZURE_CREDENTIALS              # Azure Service Principal JSON
AZURE_REGISTRY_LOGIN_SERVER    # e.g., acrpricingagent.azurecr.io
AZURE_REGISTRY_USERNAME        # ACR username
AZURE_REGISTRY_PASSWORD        # ACR password
AZURE_RESOURCE_GROUP           # e.g., rg-pricing-agent
AZURE_CONTAINER_APP_NAME       # e.g., pricing-agent-api
AZURE_CONTAINER_APP_ENVIRONMENT # e.g., env-pricing-agent
```

### Create Azure Service Principal

```bash
az ad sp create-for-rbac \
  --name "pricing-agent-github" \
  --role contributor \
  --scopes /subscriptions/YOUR_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \
  --sdk-auth
```

Copy the entire JSON output and add it as `AZURE_CREDENTIALS` secret in GitHub.

### Automatic Deployment

Now every push to `main` branch will:
1. Build Docker image
2. Push to Azure Container Registry
3. Deploy to Azure Container Apps

---

## 📡 API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API information |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive API documentation |
| POST | `/api/v1/analyze` | Analyze freight pricing |
| GET | `/api/v1/unity/refresh` | Refresh Unity Catalog |
| GET | `/api/v1/config` | Get configuration (non-sensitive) |

### Example Request

```json
{
  "proposed_price": 1500,
  "carrier_cost": "auto",
  "stops": [
    {"type": "PICKUP", "zip": "60160"},
    {"type": "DROP", "zip": "53703"}
  ],
  "customer_name": "SureBuilt",
  "equipment_type": "HOTSHOT",
  "pickup_date": "2025-01-15",
  "delivery_date": "2025-01-17",
  "weight": 6036
}
```

### Example Response

```json
{
  "success": true,
  "timestamp": "2025-01-15T10:30:00",
  "analysis_results": {
    "final_rating": "GOOD",
    "combined_confidence": 75,
    "load_type": "SINGLE_STOP",
    "proposed_margin_pct": 18.5,
    "negotiation_range": {
      "target_rate": 1350.00,
      "carrier_cost": 1400.00,
      "max_buy": 1450.00
    },
    "suggested_price": 1520.00
  },
  "execution_time_seconds": 2.34
}
```

---

## 🔧 Configuration

Main configuration is in `config.py`:

- **SINGLE_ANALYSIS**: Default load parameters
- **HOTSHOT_CONFIG**: Hotshot equipment handling
- **MULTISTOP_CONFIG**: Multistop routing settings
- **NEGOTIATION_CONFIG**: Pricing range calculation
- **PRC_CONFIG**: Historical validation parameters
- **RATING_THRESHOLDS**: Accept/reject thresholds

---

## 📊 Monitoring

### View logs in Azure

```bash
# Stream logs
az containerapp logs show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --follow

# View recent logs
az containerapp logs show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --tail 100
```

### Metrics

```bash
# Get app status
az containerapp show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "properties.{status:runningStatus,replicas:template.scale.minReplicas,cpu:template.containers[0].resources.cpu,memory:template.containers[0].resources.memory}"
```

---

## 🛠️ Maintenance

### Update deployment

```bash
# Build new image
az acr build --registry $ACR_NAME --image pricing-agent:v2 .

# Update container app
az containerapp update \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --image $ACR_LOGIN_SERVER/pricing-agent:v2
```

### Scale manually

```bash
az containerapp update \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --min-replicas 2 \
  --max-replicas 5
```

---

## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/

# With coverage
pytest --cov=. tests/
```

---

## 📝 License

Internal DTS project - All rights reserved

---

## 👤 Author

**Manuel Gutierrez**  
Data Engineer @ Direct Traffic Solutions

---

## 🆘 Support

For issues or questions, contact the development team or create an issue in the repository.