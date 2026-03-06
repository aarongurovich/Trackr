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
    """
    Main handler for fetching emails. 
    Supports both daily incremental scans and historical deep scans.
    """
    # Determine the target user. Defaults to hardcoded ID if not in event.
    user_id = event.get("user_id")
    
    # Check if debug mode is enabled
    is_debug = event.get("debug") is True

    # 1. Debug Mode: Send static test records for development
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

        print(f"DEBUG MODE ENABLED: Sending {len(test_cases)} fake emails to SQS for user {user_id}.")
        for i, text in enumerate(test_cases):
            payload = {
                "email_body": text,
                "source_email_id": f"test-1234{i}",
                "user_id": user_id,
                "applied_date": datetime.now().strftime('%Y-%m-%d')
            }
            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload))
        
        return {"statusCode": 200, "body": "Debug mode: 10 fake emails sent to SQS"}

    # 2. Production Mode: Fetch real emails from Gmail
    try:
        # Fetch user's refresh token and historical scan preference from Supabase
        user_resp = supabase.table("users").select("refresh_token, scan_history_months").eq("id", user_id).single().execute()
        refresh_token = user_resp.data.get('refresh_token')
        months = user_resp.data.get('scan_history_months', 0)

        # Build Gmail search query. 
        # If months > 0, we scan a deep historical range; otherwise, scan the last 24 hours.
        time_query = f"{months * 30}d" if months > 0 else "1d"
        gmail_q = f"newer_than:{time_query}"

        if refresh_token:
            print(f"PRODUCTION MODE: Fetching emails for user: {user_id} with query: {gmail_q}")
            access_token = get_access_token(refresh_token)
            headers = {'Authorization': f'Bearer {access_token}'}
            
            # Fetch message list matching the time query
            msgs_resp = requests.get(
                f"https://www.googleapis.com/gmail/v1/users/me/messages?q={gmail_q}", 
                headers=headers
            ).json()
            
            messages = msgs_resp.get('messages', [])
            for msg_meta in messages:
                # Fetch specific content for each message found
                msg_data = requests.get(
                    f"https://www.googleapis.com/gmail/v1/users/me/messages/{msg_meta['id']}", 
                    headers=headers
                ).json()
                
                payload = {
                    "email_body": msg_data.get('snippet', ''),
                    "source_email_id": msg_meta['id'],
                    "user_id": user_id,
                    "applied_date": datetime.now().strftime('%Y-%m-%d')
                }
                
                # Push email data to SQS for classification
                sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload))
            
            # If a historical scan was requested, reset the preference column to 0
            if months > 0:
                print(f"Resetting scan_history_months for user {user_id} after deep scan.")
                supabase.table("users").update({"scan_history_months": 0}).eq("id", user_id).execute()
            
            print(f"Sent {len(messages)} real emails to SQS.")
            return {"statusCode": 200, "body": f"Production mode: {len(messages)} real emails processed"}
            
        else:
            print(f"No refresh_token found for user {user_id}. Cannot fetch emails.")
            return {"statusCode": 404, "body": "Error: User refresh token not found"}

    except Exception as e:
        print(f"Error fetching real emails for user {user_id}: {str(e)}")
        return {"statusCode": 500, "body": f"Error: {str(e)}"}