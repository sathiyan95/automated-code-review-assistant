import json
import os
import boto3
import urllib.request

s3_client = boto3.client('s3')
GENAI_API_KEY = os.environ.get('GENAI_API_KEY')
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GENAI_API_KEY}"

def analyze_code_with_genai(code_snippet):
    if not GENAI_API_KEY:
        return {"error": "GenAI API key is missing."}
        
    prompt = (
        "You are an expert technical code reviewer. Provide a performance and logic review of the following repository code. "
        "Give suggestions to improve, and provide the 'improved_code'. "
        "Return ONLY a raw JSON string like this:\n"
        "{\"score\": 85, \"reviews\": [{\"type\": \"Performance Bottleneck\", \"message\": \"Use generators instead of lists.\", \"snippet\": \"bad_code()\", \"improved_code\": \"good_code()\", \"isDanger\": true}]}\n\n"
        f"Code CPU to review:\n{code_snippet[:10000]}"
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(GEMINI_API_URL, method="POST")
    req.add_header('Content-Type', 'application/json')
    
    try:
        response = urllib.request.urlopen(req, data=json.dumps(payload).encode('utf-8'))
        response_body = response.read().decode('utf-8')
        result = json.loads(response_body)
        
        generated_text = result['candidates'][0]['content']['parts'][0]['text']
        if generated_text.startswith("```json"):
            generated_text = generated_text[7:-3]
        elif generated_text.startswith("```"):
            generated_text = generated_text[3:-3]
            
        return json.loads(generated_text.strip())
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return {"error": str(e), "reviews": [], "score": 80}

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    repo_path = event.get('repo_path')
    reports_bucket = event.get('reports_bucket')
    run_id = event.get('run_id', 'latest')
    
    sample_code = ""
    if repo_path:
        req_tree = urllib.request.Request(
            f"https://api.github.com/repos/{repo_path}/git/trees/main?recursive=1", 
            headers={'User-Agent': 'Automated-Code-Review-Assistant'}
        )
        gh_token = os.environ.get('GITHUB_TOKEN')
        if gh_token:
            req_tree.add_header("Authorization", f"Bearer {gh_token}")
        
        try:
            resp_tree = urllib.request.urlopen(req_tree)
            tree_data = json.loads(resp_tree.read().decode('utf-8'))
            files_to_check = [item['path'] for item in tree_data.get('tree', []) if item['type'] == 'blob' and item['path'].endswith((".py", ".js", ".ts", ".html", ".css", ".java", ".go"))]
            
            chars_read = 0
            for filepath in files_to_check[:5]:
                try:
                    raw_url = f"https://raw.githubusercontent.com/{repo_path}/main/{filepath}"
                    req_file = urllib.request.Request(raw_url, headers={'User-Agent': 'Automated-Code-Review-Assistant'})
                    content = urllib.request.urlopen(req_file).read().decode('utf-8')
                    sample_code += f"\n--- {filepath} ---\n{content}\n"
                    chars_read += len(content)
                    if chars_read > 10000:
                        break
                except:
                    pass
        except Exception as e:
            print("Failed to fetch tree:", e)
    
    if not sample_code:
        sample_code = "print('No matching code found or rate limit hit.')"
        
    review_report = analyze_code_with_genai(sample_code)
    
    if reports_bucket:
        try:
            s3_client.put_object(
                Bucket=reports_bucket,
                Key=f"reports/code_review_{run_id}.json",
                Body=json.dumps(review_report),
                ContentType='application/json'
            )
            # Latest file without cache for frontend
            s3_client.put_object(
                Bucket=reports_bucket,
                Key=f"reports/code_review_latest.json",
                Body=json.dumps(review_report),
                ContentType='application/json',
                CacheControl='no-cache'
            )
        except Exception as e:
            print("Failed to save to S3:", e)
            
    return {"statusCode": 200, "body": json.dumps("Review Success")}
