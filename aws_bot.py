# aws_nl_query_tool.py
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
import subprocess
import json
import sys

# Ensure dependencies
def install(package):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", package],
        stdout=subprocess.DEVNULL,  # suppress stdout
        stderr=subprocess.DEVNULL   # suppress stderr
    )
    
try:
    import boto3
except ImportError:
    install('boto3')
    import boto3
    
mcp = FastMCP("AWSNaturalLanguageQuery")

# Prompt: Interpret natural language into AWS call structure
@mcp.prompt()
def interpret_aws_question(nl_input: str) -> dict:
    """
    Converts natural language AWS query into a structured boto3 call definition.
    Output format:
    {
        "service": "s3",
        "operation": "list_buckets",
        "params": {},
        "region": "us-west-2"  # optional
    }
    """
    return base.UserMessage(f"Please convert this natural AWS question into a boto3 API call structure with optional region override: {nl_input}")

# Tool: Executes interpreted AWS API call and returns results
@mcp.tool()
def execute_aws_query(service: str, operation: str, params: dict, region: str = "us-east-1") -> str:
    """
    Execute a Boto3 API call based on structured request.
    
    Example:
    service: "s3"
    operation: "list_buckets"
    params: {}
    region: "us-west-2"
    """
    try:
        print(f"Calling boto3: {service}.{operation}({params}) in region {region}", file=sys.stderr)
        client = boto3.client(service, region_name=region)
        operation_fn = getattr(client, operation)
        response = operation_fn(**params)
        formatted = json.dumps(response, indent=2, default=str)
        return f"Here is the result of {service}.{operation}():\n\n{formatted}"
    except AttributeError:
        return f"Error: '{operation}' is not a valid operation for the '{service}' service."
    except Exception as e:
        return f"Failed to execute {service}.{operation} in region {region} with params {params}: {str(e)}"

if __name__ == "__main__":
    mcp.run()
