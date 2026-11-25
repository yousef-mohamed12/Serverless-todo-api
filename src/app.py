"""CRUD handler for the to-do API. Every item is scoped to the caller's Cognito `sub`."""
import json, os, time, uuid, decimal
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

try:  # X-Ray subsegments for every DynamoDB call
    from aws_xray_sdk.core import patch_all
    patch_all()
except ImportError:
    pass

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
STATUSES = {"open", "done"}


def _json(o):
    if isinstance(o, decimal.Decimal):
        return int(o) if o == o.to_integral() else float(o)
    raise TypeError


def resp(code, body=None):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json) if body is not None else "",
    }


def handler(event, context):
    user = event["requestContext"]["authorizer"]["claims"]["sub"]
    method = event["httpMethod"]
    todo_id = (event.get("pathParameters") or {}).get("id")
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return resp(400, {"error": "Request body must be valid JSON"})

    if method == "GET" and not todo_id:
        status = (event.get("queryStringParameters") or {}).get("status")
        if status:  # uses the status-index GSI
            q = table.query(IndexName="status-index",
                            KeyConditionExpression=Key("userId").eq(user) & Key("status").eq(status))
        else:
            q = table.query(KeyConditionExpression=Key("userId").eq(user), ScanIndexForward=False)
        return resp(200, q["Items"])

    if method == "POST":
        title = str(body.get("title", "")).strip()
        if not title or len(title) > 200:
            return resp(400, {"error": "title is required and must be 1-200 characters"})
        item = {"userId": user, "todoId": f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:6]}",
                "title": title, "status": "open", "createdAt": int(time.time())}
        table.put_item(Item=item)
        return resp(201, item)

    if todo_id and method == "GET":
        item = table.get_item(Key={"userId": user, "todoId": todo_id}).get("Item")
        return resp(200, item) if item else resp(404, {"error": "Not found"})

    try:
        if todo_id and method == "PUT":
            sets, names, values = [], {}, {}
            if "title" in body:
                title = str(body["title"]).strip()
                if not title or len(title) > 200:
                    return resp(400, {"error": "title must be 1-200 characters"})
                sets.append("#t = :t"); names["#t"] = "title"; values[":t"] = title
            if "status" in body:
                if body["status"] not in STATUSES:
                    return resp(400, {"error": "status must be 'open' or 'done'"})
                sets.append("#s = :s"); names["#s"] = "status"; values[":s"] = body["status"]
            if not sets:
                return resp(400, {"error": "Nothing to update"})
            r = table.update_item(
                Key={"userId": user, "todoId": todo_id},
                UpdateExpression="SET " + ", ".join(sets),
                ConditionExpression="attribute_exists(todoId)",
                ExpressionAttributeNames=names, ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW")
            return resp(200, r["Attributes"])

        if todo_id and method == "DELETE":
            table.delete_item(Key={"userId": user, "todoId": todo_id},
                              ConditionExpression="attribute_exists(todoId)")
            return resp(204)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return resp(404, {"error": "Not found"})
        raise

    return resp(405, {"error": "Method not allowed"})
