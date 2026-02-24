import json
import os
import boto3
import urllib.request
import uuid

# AWS Clients
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')
glue_client = boto3.client('glue')

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    
    # Handle CORS preflight for HTTP API
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return _cors_response(200, "OK")
    
    try:
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')
            
        body = json.loads(body_str)
        repo_url = body.get('repo_url')
        
        # Determine github path
        repo_path = None
        if repo_url and repo_url.startswith('https://github.com/'):
            repo_path = repo_url.split("github.com/")[1].strip("/")
            
        if not repo_path:
            return _cors_response(400, "Invalid repository URL. Must start with https://github.com/")
        
        # 1. Fetch last 100 commits from GitHub
        req_commits = urllib.request.Request(
            f"https://api.github.com/repos/{repo_path}/commits?per_page=100", 
            headers={'User-Agent': 'Automated-Code-Review-Assistant'}
        )
        gh_token = os.environ.get('GITHUB_TOKEN')
        if gh_token:
            req_commits.add_header("Authorization", f"Bearer {gh_token}")
            
        try:
            resp_commits = urllib.request.urlopen(req_commits)
            commits_raw = json.loads(resp_commits.read().decode('utf-8'))
            commit_data = ""
            for c in commits_raw:
                sha = c.get('sha', '')
                author = c.get('commit', {}).get('author', {}).get('name', '')
                date = c.get('commit', {}).get('author', {}).get('date', '')
                msg = c.get('commit', {}).get('message', '').replace('\n', ' ')
                commit_data += f"{sha}|{author}|{date}|{msg}\n"
        except Exception as e:
            print("Error fetching commits:", e)
            commit_data = f"dummy|author|date|Fallback commit due to error: {e}"
            
        # 2. Store commits.json in S3
        reports_bucket = os.environ.get('REPORTS_BUCKET')
        run_id = str(uuid.uuid4())
        commits_key = f"data/commits_{run_id}.json"
        
        s3_client.put_object(
            Bucket=reports_bucket,
            Key=commits_key,
            Body=json.dumps({"commit_text": commit_data}),
            ContentType='application/json'
        )
        
        # 3. Asynchronously invoke Review Lambda
        review_lambda_name = os.environ.get('REVIEW_LAMBDA_NAME')
        if review_lambda_name:
            lambda_client.invoke(
                FunctionName=review_lambda_name,
                InvocationType='Event',
                Payload=json.dumps({"repo_path": repo_path, "run_id": run_id, "reports_bucket": reports_bucket})
            )
            
        # 4. Asynchronously invoke Glue Job
        glue_job_name = os.environ.get('GLUE_JOB_NAME')
        if glue_job_name:
            glue_client.start_job_run(
                JobName=glue_job_name,
                Arguments={
                    '--COMMITS_KEY': commits_key,
                    '--RUN_ID': run_id
                }
            )
            
        # Also create initial placeholders in S3 for frontend polling
        s3_client.put_object(Bucket=reports_bucket, Key="reports/technical_debt_latest.json", Body=json.dumps({"status": "processing"}), ContentType='application/json', CacheControl='no-cache')
        s3_client.put_object(Bucket=reports_bucket, Key="reports/code_review_latest.json", Body=json.dumps({"status": "processing"}), ContentType='application/json', CacheControl='no-cache')
            
        return _cors_response(200, {
            "status": "success",
            "message": "Analysis started asynchronously.",
            "run_id": run_id,
            "reports_bucket": reports_bucket,
            "region": os.environ.get('AWS_REGION')
        })
        
    except Exception as e:
        print("Internal error:", e)
        return _cors_response(500, f"Internal server error: {str(e)}")

def _cors_response(status_code, body):
    if not isinstance(body, str):
        body = json.dumps(body)
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
            'Content-Type': 'application/json'
        },
        'body': body
    }
