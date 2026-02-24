import os
import json
import google.generativeai as genai

genai.configure(api_key=os.environ["GENAI_API_KEY"])

model = genai.GenerativeModel("gemini-pro")

def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    code = body.get("code", "")

    if not code:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "No code provided"})
        }

    prompt = f"""
    You are a senior software engineer.
    Review the following code and provide:
    - Issues
    - Improvements
    - Optimized version

    Code:
    {code}
    """

    response = model.generate_content(prompt)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "review": response.text
        })
    }
