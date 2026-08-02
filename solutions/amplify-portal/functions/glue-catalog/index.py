import os
import boto3

region = os.environ.get("AWS_REGION", "ap-northeast-1")
glue = boto3.client("glue", region_name=region)


def handler(event, context):
    """Browse Glue Data Catalog — databases, tables, and schema."""
    action = event.get("action", "listDatabases")
    database = event.get("database", "")
    table = event.get("table", "")

    try:
        if action == "listDatabases":
            response = glue.get_databases(MaxResults=50)
            databases = [
                {"name": db["Name"], "description": db.get("Description", "")} for db in response["DatabaseList"]
            ]
            return {"databases": databases, "error": None}

        elif action == "listTables":
            if not database:
                return {"tables": [], "error": "database required"}
            response = glue.get_tables(DatabaseName=database, MaxResults=50)
            tables = [
                {
                    "name": t["Name"],
                    "description": t.get("Description", ""),
                    "columns": len(t.get("StorageDescriptor", {}).get("Columns", [])),
                    "location": t.get("StorageDescriptor", {}).get("Location", ""),
                }
                for t in response["TableList"]
            ]
            return {"tables": tables, "error": None}

        elif action == "getSchema":
            if not database or not table:
                return {"schema": [], "error": "database and table required"}
            response = glue.get_table(DatabaseName=database, Name=table)
            columns = [
                {"name": c["Name"], "type": c["Type"], "comment": c.get("Comment", "")}
                for c in response["Table"].get("StorageDescriptor", {}).get("Columns", [])
            ]
            partition_keys = [
                {"name": p["Name"], "type": p["Type"]} for p in response["Table"].get("PartitionKeys", [])
            ]
            return {
                "schema": columns,
                "partitionKeys": partition_keys,
                "location": response["Table"].get("StorageDescriptor", {}).get("Location", ""),
                "error": None,
            }

        return {"error": f"Unknown action: {action}"}

    except Exception as e:
        return {"error": str(e)}
