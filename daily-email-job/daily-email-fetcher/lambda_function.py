import os
import json
import boto3
import requests
from datetime import datetime
from supabase import create_client, Client

# --- 1. Global Config ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
QUEUE_URL = os.environ.get("SQS_QUEUE_URL")

# --- 2. Initializations ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
sqs = boto3.client('sqs')

def get_access_token(refresh_token):
    """Refreshes the Google OAuth access token."""
    response = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    })
    return response.json().get('access_token')

def handler(event, context):
    # Hardcoded ID for Aaron Gurovich
    USER_ID = "5e2b7b41-f662-44ef-8ee0-0c6a010fdf4a"
    
    # Check if debug mode is enabled in the event object
    is_debug = event.get("debug") is True

    # 1. Debug Mode: Send ONLY static test records
    if is_debug:
        test_cases = [
            "Dear Aaron Gurovich, we are pleased to offer you the position of Software Engineer at Tech Corp!",
            "Hi Aaron Gurovich, you have an interview for the Production Engineer role at Meta.",
            "Regretfully, Amazon is not moving forward with your application for SDE1.",
            "Congratulations! We are pleased to offer you the Data Scientist role at NVIDIA.",
            "Your weekly LinkedIn job alerts: 15 new Software Engineer roles in Lubbock, TX.",
            "Hey Aaron, want to grab lunch today? Let me know if you're free.",
            "Update from Tesla: Your interview for the Firmware Intern role is confirmed.",
            "Netflix: Your subscription has been renewed.",
            "Application Received: Full-stack Developer at Stripe.",
            "Hi, this is a recruiter from OpenAI. We saw your GitHub and want to chat."
        ]

        print(f"DEBUG MODE ENABLED: Sending {len(test_cases)} fake emails to SQS.")
        for i, text in enumerate(test_cases):
            payload = {
                "email_body": text,
                "source_email_id": f"test-1234{i}",
                "user_id": USER_ID,
                "applied_date": datetime.now().strftime('%Y-%m-%d')
            }
            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload))
        
        return {"statusCode": 200, "body": "Debug mode: 10 fake emails sent to SQS"}

    # 2. Production Mode: Fetch ONLY real emails from Gmail
    try:
        user_resp = supabase.table("users").select("refresh_token").eq("id", USER_ID).single().execute()
        refresh_token = user_resp.data.get('refresh_token')

        if refresh_token:
            print(f"PRODUCTION MODE: Fetching real emails for user: {USER_ID}")
            access_token = get_access_token(refresh_token)
            headers = {'Authorization': f'Bearer {access_token}'}
            
            # Query for emails from the last 24 hours
            msgs_resp = requests.get(
                "https://www.googleapis.com/gmail/v1/users/me/messages?q=newer_than:1d", 
                headers=headers
            ).json()
            
            messages = msgs_resp.get('messages', [])
            for msg_meta in messages:
                msg_data = requests.get(
                    f"https://www.googleapis.com/gmail/v1/users/me/messages/{msg_meta['id']}", 
                    headers=headers
                ).json()
                
                payload = {
                    "email_body": msg_data.get('snippet', ''),
                    "source_email_id": msg_meta['id'],
                    "user_id": USER_ID,
                    "applied_date": datetime.now().strftime('%Y-%m-%d')
                }
                
                sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload))
            
            print(f"Sent {len(messages)} real emails to SQS.")
            return {"statusCode": 200, "body": f"Production mode: {len(messages)} real emails processed"}
            
        else:
            print("No refresh_token found. Cannot fetch real emails.")
            return {"statusCode": 404, "body": "Error: User refresh token not found"}

    except Exception as e:
        print(f"Error fetching real emails: {str(e)}")
        return {"statusCode": 500, "body": f"Error: {str(e)}"}