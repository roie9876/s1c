# Recommended Prompts for this Project

Here are some useful prompts you can use with GitHub Copilot to assist with the migration project.

## Azure Functions Development
*   "Create a new Azure Function HTTP trigger in Python using the v2 model that accepts a JSON body with `userId`, `targetIp`, and `credentials`, and saves it to Cosmos DB."
*   "Write a Python function to query Cosmos DB for the latest pending connection request for a specific `userId` and update its status to 'CONSUMED'."
*   "Generate a `function_app.py` file that implements the `queue_connection` and `fetch_connection` endpoints described in the migration plan."

## PowerShell Launcher Development
*   "Write a PowerShell script that gets the current logged-in user's UPN."
*   "Create a PowerShell function that calls a REST API endpoint to fetch connection details, handling 404 and 500 errors gracefully."
*   "Show me how to launch `SmartConsole.exe` from PowerShell with command-line arguments for username, password, and target IP."

## Infrastructure as Code (Bicep/Terraform)
*   "Generate a Bicep file to deploy an Azure Cosmos DB account with a SQL API database named `S1C_Migration` and a container named `ConnectionRequests` with TTL enabled."
*   "Create a Terraform configuration for an Azure Function App on a Consumption plan with Python runtime."

## Testing & Debugging
*   "How can I run the Python Azure Function locally and test it with `curl`?"
*   "Write a unit test for the `fetch_connection` function using `pytest` and mocked Cosmos DB responses."
