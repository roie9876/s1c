#!/bin/bash

# Variables
RESOURCE_GROUP="S1C-Migration-RG"
LOCATION="eastus2"
# Generate a random suffix for globally unique names
SUFFIX=$RANDOM
COSMOS_ACCOUNT="s1c-cosmos-$SUFFIX"
STORAGE_ACCOUNT="s1cstorage$SUFFIX"
FUNCTION_APP="s1c-function-$SUFFIX"
DATABASE_NAME="S1C_Migration"
CONTAINER_NAME="ConnectionRequests"

echo "Starting Azure Resource Creation..."
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Cosmos Account: $COSMOS_ACCOUNT"
echo "Storage Account: $STORAGE_ACCOUNT"
echo "Function App: $FUNCTION_APP"

# 1. Create Resource Group
echo "Creating Resource Group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

# 2. Create Cosmos DB Account (NoSQL)
echo "Creating Cosmos DB Account (this may take a few minutes)..."
az cosmosdb create --name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --kind GlobalDocumentDB --locations regionName=$LOCATION failoverPriority=0 isZoneRedundant=False

# 3. Create Cosmos DB Database
echo "Creating Cosmos DB Database..."
az cosmosdb sql database create --account-name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --name $DATABASE_NAME

# 4. Create Cosmos DB Container with TTL and Partition Key
echo "Creating Cosmos DB Container..."
az cosmosdb sql container create --account-name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --database-name $DATABASE_NAME --name $CONTAINER_NAME --partition-key-path "/userId" --ttl 60

# 5. Create Storage Account (Required for Function App)
echo "Creating Storage Account..."
az storage account create --name $STORAGE_ACCOUNT --location $LOCATION --resource-group $RESOURCE_GROUP --sku Standard_LRS

# 6. Create Function App (Python, Consumption Plan)
echo "Creating Function App..."
az functionapp create --resource-group $RESOURCE_GROUP --consumption-plan-location $LOCATION --runtime python --runtime-version 3.10 --functions-version 4 --name $FUNCTION_APP --os-type linux --storage-account $STORAGE_ACCOUNT

# 7. Retrieve and Configure Cosmos DB Connection String
echo "Configuring Function App Settings..."
COSMOS_ENDPOINT=$(az cosmosdb show --name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --query documentEndpoint --output tsv)
COSMOS_KEY=$(az cosmosdb keys list --name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --query primaryMasterKey --output tsv)

az functionapp config appsettings set --name $FUNCTION_APP --resource-group $RESOURCE_GROUP --settings \
    COSMOS_ENDPOINT=$COSMOS_ENDPOINT \
    COSMOS_KEY=$COSMOS_KEY \
    COSMOS_DATABASE=$DATABASE_NAME \
    COSMOS_CONTAINER=$CONTAINER_NAME \
    AzureWebJobsStorage__accountName=$STORAGE_ACCOUNT

echo "--------------------------------------------------"
echo "Deployment Complete!"
echo "Function App Name: $FUNCTION_APP"
echo "Cosmos DB Account: $COSMOS_ACCOUNT"
echo "--------------------------------------------------"
