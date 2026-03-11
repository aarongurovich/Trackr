import os
import json
import requests
import time
from supabase import create_client, Client

# --- 1. Global Config ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# --- 2. Structural Enforcement ---
DEFAULT_STRUCTURE = {
    "is_job_application": False,
    "company_name": None,
    "job_title": None,
    "role_type": "Unknown",
    "status": "applied",         
    "specific_stage": "Applied", 
    "location": None,
    "salary_estimate": None,
    "next_action": None,
    "action_deadline": None,
    "summary": None
}

def analyze_email_with_ai(email_body, received_date):
    print(f"Requesting AI analysis for email received on: {received_date}")
    
    system_message = (
        "You are a career data extraction engine. You must return ONLY a JSON object. "
        "If a value is unknown, use null. Strictly follow this schema:\n"
        "{\n"
        "  \"is_job_application\": boolean,\n"
        "  \"company_name\": string (Required if is_job_application is true),\n"
        "  \"job_title\": string,\n"
        "  \"role_type\": \"Full-time\" | \"Internship\" | \"Contract\" | \"Co-op\" | \"Unknown\",\n"
        "  \"status\": \"applied\" | \"interview\" | \"offer\" | \"rejected\",\n"
        "  \"specific_stage\": string (e.g., \"Round 1\", \"Technical Screen\", \"Final Round\"),\n"
        "  \"location\": string (e.g., \"Remote\", \"San Francisco, CA\"),\n"
        "  \"salary_estimate\": string,\n"
        "  \"next_action\": string (Concise next step for the user),\n"
        "  \"action_deadline\": string (ISO 8601 date if mentioned, relative to the received_date),\n"
        "  \"summary\": string (1-sentence overview)\n"
        "}"
    )

    user_content = f"Email Received Date: {received_date}\n\nEmail Content:\n{email_body}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": "stepfun/step-3.5-flash:free",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_content}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1 
                })
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            ai_json = json.loads(content)
            
            return {**DEFAULT_STRUCTURE, **ai_json}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                print(f"Rate limited (429). Retrying in {2 ** attempt} seconds...")
                time.sleep(2 ** attempt)
                continue
            print(f"AI Analysis failed: {str(e)}")
            return DEFAULT_STRUCTURE
        except Exception as e:
            print(f"AI Analysis failed: {str(e)}")
            return DEFAULT_STRUCTURE

def handler(event, context):
    print(f"Initializing Classifier for Supabase: {SUPABASE_URL}")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    records = event.get('Records', [])
    print(f"Processing batch of {len(records)} SQS records.")

    for record in records:
        try:
            payload = json.loads(record['body'])
            email_body = payload.get('email_body')
            user_id = payload.get('user_id')
            received_date = payload.get('applied_date')
            
            if not email_body or not user_id:
                continue

            ai_result = analyze_email_with_ai(email_body, received_date)

            if ai_result.get("is_job_application") and ai_result.get("company_name"):
                data = {
                    "user_id": user_id,
                    "company_name": ai_result["company_name"],
                    "job_title": ai_result["job_title"],
                    "role_type": ai_result["role_type"] or "Full-time",
                    "status": ai_result["status"] or "applied",
                    "specific_stage": ai_result["specific_stage"],
                    "location": ai_result["location"],
                    "salary_estimate": ai_result["salary_estimate"],
                    "next_action": ai_result["next_action"],
                    "action_deadline": ai_result["action_deadline"],
                    "summary": ai_result["summary"],
                    "source_email_id": payload.get('source_email_id'),
                    "applied_date": received_date
                }
                
                print(f"Inserting {data['company_name']} ({data['specific_stage']}) for User {user_id}")
                supabase.table("ai_classifications").insert(data).execute()
            
            time.sleep(1)
                
        except Exception as e:
            print(f"Error processing SQS record: {str(e)}")
            continue
            
    return {"statusCode": 200, "body": "Batch processing complete"}