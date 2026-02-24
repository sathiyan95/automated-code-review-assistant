import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
import json
import urllib.request
import boto3

args = getResolvedOptions(sys.argv, ['JOB_NAME', 'GENAI_API_KEY', 'OUTPUT_BUCKET', 'COMMITS_KEY', 'RUN_ID'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

GENAI_API_KEY = args['GENAI_API_KEY']
OUTPUT_BUCKET = args['OUTPUT_BUCKET']
COMMITS_KEY = args['COMMITS_KEY']
RUN_ID = args['RUN_ID']
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GENAI_API_KEY}"

s3_client = boto3.client('s3')

def call_gemini_api(commit_data):
    prompt = (
        "You are an AI architect analyzing repository history. "
        "Review the following commit data (representing the last 100 commits). "
        "Identify modules that have high churn, bug fixes, or complex changes, and estimate their 'Refactoring Urgency' (0-100 score). "
        "Return ONLY a raw JSON format like this:\n"
        "{\"techDebtScore\": 110, \"modules\": [{\"name\": \"backend/auth.py\", \"urgency\": 85, \"reason\": \"High churn\"}]}\n\n"
        f"Commit Data:\n{commit_data[:10000]}"
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(GEMINI_API_URL, method="POST")
    req.add_header('Content-Type', 'application/json')
    
    try:
        response = urllib.request.urlopen(req, data=json.dumps(payload).encode('utf-8'))
        response_body = response.read().decode('utf-8')
        result = json.loads(response_body)
        
        generated_text = result['candidates'][0]['content']['parts'][0]['text']
        if generated_text.startswith("```json"): return generated_text[7:-3]
        if generated_text.startswith("```"): return generated_text[3:-3]
        return generated_text.strip()
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return json.dumps({"techDebtScore": 0, "modules": [], "error": str(e)})

try:
    # Read the historical commit data from S3
    response = s3_client.get_object(Bucket=OUTPUT_BUCKET, Key=COMMITS_KEY)
    commit_history_json = json.loads(response['Body'].read().decode('utf-8'))
    commit_data_str = commit_history_json.get('commit_text', '')
    
    analysis_result_schema_str = call_gemini_api(commit_data_str)
    
    # Write to specific run_id
    s3_client.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=f"reports/technical_debt_{RUN_ID}.json",
        Body=analysis_result_schema_str,
        ContentType='application/json'
    )
    # Write to latest
    s3_client.put_object(
        Bucket=OUTPUT_BUCKET,
        Key=f"reports/technical_debt_latest.json",
        Body=analysis_result_schema_str,
        ContentType='application/json',
        CacheControl='no-cache'
    )

except Exception as ex:
    print(f"Analyze Job failed: {ex}")

job.commit()
