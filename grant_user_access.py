# aws_mcp_tool.py
from mcp.server.fastmcp import FastMCP
import subprocess
import re
import sys
import time

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
# Initialize MCP server
mcp = FastMCP("AWSAccessTool")

# AWS client initialization
def get_sso_admin_client():
    return boto3.client('sso-admin', region_name='us-east-1')

def get_identitystore_client():
    return boto3.client('identitystore', region_name='us-east-1')

# Helper function to find user ID by email
def get_user_id(identity_store_id, email):
    client = get_identitystore_client()
    response = client.list_users(
        IdentityStoreId=identity_store_id,
        Filters=[{"AttributePath": "UserName", "AttributeValue": email}]
    )
    users = response.get('Users', [])
    return users[0]['UserId'] if users else None

# MCP Tool to grant access
@mcp.tool()
def grant_access(request: str) -> str:
    """
    Grant a user access to AWS account via IAM Identity Center based on natural language input.
    List all available permission sets in the SSO instance and assign the specified one to the user.

    Example request:
    "grant user user@example.com user access to aws account number 123456789012 with adminaccess permission set"
    """
    # Extract details using regex
    pattern = (r"grant user (\S+) user access to aws account number (\d{12}) "
               r"with ([\w-]+) permission set")

    match = re.match(pattern, request, re.IGNORECASE)

    if not match:
        return "Invalid request format. Please follow: grant user [email] user access to aws account number [account] with [permission_set] permission set."

    email, account_id, permission_set_name = match.groups()
    print(f"Extracted email: {email}, account_id: {account_id}, permission_set_name: {permission_set_name}", file=sys.stderr)

    identity_store_id = "<store-id>"  # Replace with your actual Identity Store ID
    instance_arn = "<arn>"  # Replace with your SSO instance ARN

    # Get user ID from Identity Store
    user_id = get_user_id(identity_store_id, email)
    if not user_id:
        return f"User {email} not found in identity store."

    sso_client = get_sso_admin_client()

    # Fetch permission set ARN
    # perm_sets = sso_client.list_permission_sets(InstanceArn=instance_arn)['PermissionSets']
    paginator = sso_client.get_paginator('list_permission_sets')
    page_iterator = paginator.paginate(InstanceArn=instance_arn)

    perm_sets = []
    for page in page_iterator:
        perm_sets.extend(page['PermissionSets'])
    perm_set_arn = None

    for perm in perm_sets:
        desc = sso_client.describe_permission_set(InstanceArn=instance_arn, PermissionSetArn=perm)
        print(f"desc: {desc}", file=sys.stderr)
        print(f"permission_set_name: {permission_set_name}", file=sys.stderr)
        if desc['PermissionSet']['Name'].lower() == permission_set_name.lower():
            perm_set_arn = perm
            print(f"perm_set_arn: {perm_set_arn}", file=sys.stderr)
            break

    if perm_set_arn is None:
        return f"Permission set '{permission_set_name}' not found."

    # Provision access
    try:
        print(f"came to access provisioning line", file=sys.stderr)
        response=sso_client.create_account_assignment(
            InstanceArn=instance_arn,
            TargetId=account_id,
            TargetType='AWS_ACCOUNT',
            PermissionSetArn=perm_set_arn,
            PrincipalType='USER',
            PrincipalId=user_id
        )
        request_id = response['AccountAssignmentCreationStatus']['RequestId']
        # Poll for the assignment to reach SUCCEEDED status
        status = 'IN_PROGRESS'
        while status == 'IN_PROGRESS':
            time.sleep(2)  # Wait for 2 seconds before checking again
            status_response = sso_client.describe_account_assignment_creation_status(
                InstanceArn=instance_arn,
                AccountAssignmentCreationRequestId=request_id
            )
            print(f"status_response: {status_response}", file=sys.stderr)
            status = status_response['AccountAssignmentCreationStatus']['Status']

        if status != 'SUCCEEDED':
            reason = status_response['AccountAssignmentCreationStatus'].get('FailureReason', 'Unknown error')
            return f"Failed to assign permission: {reason}"
        print(f"AWS API Response: {response}", file=sys.stderr)
    except Exception as e:
        print(f"API call error: {str(e)}", file=sys.stderr)
        return f"Failed to assign permission: {str(e)}"

    return f"Successfully granted {email} access to account {account_id} with permission set '{permission_set_name}'."

# Start the MCP server
if __name__ == "__main__":
    mcp.run()
