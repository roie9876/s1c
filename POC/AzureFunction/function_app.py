import azure.functions as func
import json
import logging
import os
import uuid

from azure.cosmos import CosmosClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Cosmos DB configuration
ENDPOINT = os.environ.get("COSMOS_ENDPOINT")
KEY = os.environ.get("COSMOS_KEY")
DATABASE_NAME = os.environ.get("COSMOS_DATABASE")
CONTAINER_NAME = os.environ.get("COSMOS_CONTAINER")

_cosmos_client = None


def get_container():
    global _cosmos_client

    if not ENDPOINT or not KEY or not DATABASE_NAME or not CONTAINER_NAME:
        raise ValueError(
            "Missing Cosmos DB configuration. Ensure COSMOS_ENDPOINT, COSMOS_KEY, COSMOS_DATABASE, COSMOS_CONTAINER are set."
        )

    if _cosmos_client is None:
        _cosmos_client = CosmosClient(ENDPOINT, KEY)

    database = _cosmos_client.get_database_client(DATABASE_NAME)
    return database.get_container_client(CONTAINER_NAME)


@app.route(route="queue_connection", methods=["POST"])
def queue_connection(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing queue_connection request")

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    user_id = req_body.get("userId")
    if not user_id:
        return func.HttpResponse("Missing 'userId'", status_code=400)

    item = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "targetIp": req_body.get("targetIp"),
        "username": req_body.get("username"),
        "password": req_body.get("password"),
        "status": "PENDING",
        # Short-lived TTL (seconds). Container must have TTL enabled.
        "ttl": 60,
    }

    try:
        container = get_container()
        container.create_item(body=item)
        return func.HttpResponse(
            json.dumps({"message": "Request queued", "id": item["id"]}),
            mimetype="application/json",
            status_code=201,
        )
    except Exception as e:
        logging.error(f"Error writing to Cosmos DB: {str(e)}")
        return func.HttpResponse(f"Internal Server Error: {str(e)}", status_code=500)


@app.route(route="fetch_connection", methods=["GET"])
def fetch_connection(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Processing fetch_connection request")

    user_id = req.params.get("userId")
    if not user_id:
        return func.HttpResponse("Missing 'userId' query parameter", status_code=400)

    try:
        container = get_container()
        query = "SELECT * FROM c WHERE c.userId = @userId AND c.status = 'PENDING'"
        parameters = [{"name": "@userId", "value": user_id}]

        items = list(
            container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=False,
            )
        )

        if not items:
            return func.HttpResponse("No pending connection found", status_code=404)

        item = items[0]
        container.delete_item(item=item["id"], partition_key=user_id)

        response_payload = {
            "targetIp": item.get("targetIp"),
            "username": item.get("username"),
            "password": item.get("password"),
        }

        return func.HttpResponse(
            json.dumps(response_payload),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        logging.error(f"Error accessing Cosmos DB: {str(e)}")
        return func.HttpResponse(f"Internal Server Error: {str(e)}", status_code=500)
