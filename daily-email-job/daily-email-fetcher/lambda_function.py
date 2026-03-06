import os
import json
import boto3
import requests
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

# --- 1. Global Config ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
MICROSOFT_CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET")
QUEUE_URL = os.environ.get("SQS_QUEUE_URL")

# --- 2. Initializations ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
sqs = boto3.client('sqs')

def get_google_access_token(refresh_token):
    """Refreshes the Google OAuth access token."""
    try:
        response = requests.post('https://oauth2.googleapis.com/token', data={
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        })
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        print(f"Failed to refresh Google token: {e}")
        return None

def get_microsoft_access_token(refresh_token):
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'client_id': MICROSOFT_CLIENT_ID,
        'client_secret': MICROSOFT_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    response = requests.post('https://login.microsoftonline.com/common/oauth2/v2.0/token', headers=headers, data=data)
    return response.json().get('access_token')

def handler(event, context):
    """
    Main handler for fetching emails. 
    Supports both daily incremental scans and historical deep scans.
    """
    if "body" in event and event["body"]:
        try:
            body_data = json.loads(event["body"])
            user_id = body_data.get("user_id")
            is_debug = body_data.get("debug") is True
        except Exception:
            user_id = None
            is_debug = False
    else:
        user_id = event.get("user_id")
        is_debug = event.get("debug") is True
    
    if not user_id:
        print("No user_id provided. Exiting.")
        return {"statusCode": 400, "body": "Error: user_id is required."}

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

    try:
        user_resp = supabase.table("users").select("refresh_token, outlook_refresh_token, preferred_provider, scan_history_months").eq("id", user_id).single().execute()
        
        provider = user_resp.data.get('preferred_provider', 'google')
        months = user_resp.data.get('scan_history_months', 0) or 0
        messages_processed = 0
        MAX_EMAILS = 500

        # ==========================================
        # MICROSOFT OUTLOOK LOGIC
        # ==========================================
        if provider == 'outlook':
            refresh_token = user_resp.data.get('outlook_refresh_token')
            if not refresh_token:
                print(f"No outlook_refresh_token found for user {user_id}. Cannot fetch emails.")
                return {"statusCode": 404, "body": "Error: User outlook refresh token not found"}
                
            print(f"PRODUCTION MODE (OUTLOOK): Fetching emails for user: {user_id}")
            access_token = get_microsoft_access_token(refresh_token)
            
            if not access_token:
                 print(f"CRITICAL: Failed to get access token for user {user_id}. Exiting.")
                 return {"statusCode": 401, "body": "Error: Failed to obtain Microsoft access token."}

            headers = {'Authorization': f'Bearer {access_token}'}
            
            if months > 0:
                past_date = datetime.now(timezone.utc) - timedelta(days=months*30)
                print(f"NEW USER DETECTED: Performing one-time {months} month historical scan for {user_id}")
            else:
                past_date = datetime.now(timezone.utc) - timedelta(days=1)
                print(f"EXISTING USER: Performing standard 24-hour incremental scan for {user_id}")
                
            date_str = past_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            graph_url = f"https://graph.microsoft.com/v1.0/me/messages?$filter=receivedDateTime ge {date_str}&$select=id,bodyPreview,receivedDateTime&$top=50"
            
            # Loop for pagination
            while graph_url and messages_processed < MAX_EMAILS:
                msgs_resp = requests.get(graph_url, headers=headers)
                msgs_resp.raise_for_status()
                data = msgs_resp.json()
                messages = data.get('value', [])
                
                for msg_data in messages:
                    if messages_processed >= MAX_EMAILS:
                        break
                    
                    # Convert Outlook ISO timestamp to YYYY-MM-DD
                    raw_date = msg_data.get('receivedDateTime', '')
                    formatted_date = raw_date[:10] if raw_date else datetime.now().strftime('%Y-%m-%d')
                    
                    payload = {
                        "email_body": msg_data.get('bodyPreview', ''),
                        "source_email_id": msg_data.get('id'),
                        "user_id": user_id,
                        "applied_date": formatted_date
                    }
                    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload))
                    messages_processed += 1
                
                # Check for the next page link
                graph_url = data.get('@odata.nextLink')

        # ==========================================
        # GOOGLE GMAIL LOGIC
        # ==========================================
        else:
            refresh_token = user_resp.data.get('refresh_token')
            if not refresh_token:
                print(f"No refresh_token found for user {user_id}. Cannot fetch emails.")
                return {"statusCode": 404, "body": "Error: User refresh token not found"}

            if months > 0:
                time_query = f"{months * 30}d"
                print(f"NEW USER DETECTED: Performing one-time {months} month historical scan for {user_id}")
            else:
                time_query = "1d"
                print(f"EXISTING USER: Performing standard 24-hour incremental scan for {user_id}")
                
            gmail_q = f"newer_than:{time_query}"
            
            print(f"PRODUCTION MODE (GMAIL): Fetching emails for user: {user_id} with query: {gmail_q}")
            access_token = get_google_access_token(refresh_token)
            
            if not access_token:
                 print(f"CRITICAL: Failed to get access token for user {user_id}. Exiting.")
                 return {"statusCode": 401, "body": "Error: Failed to obtain Google access token."}

            headers = {'Authorization': f'Bearer {access_token}'}
            next_page_token = None
            
            # Loop for pagination
            while messages_processed < MAX_EMAILS:
                list_url = f"https://www.googleapis.com/gmail/v1/users/me/messages?q={gmail_q}&maxResults=100"
                if next_page_token:
                    list_url += f"&pageToken={next_page_token}"
                    
                msgs_resp = requests.get(list_url, headers=headers)
                msgs_resp.raise_for_status()
                data = msgs_resp.json()
                messages = data.get('messages', [])
                
                if not messages:
                    break

                for msg_meta in messages:
                    if messages_processed >= MAX_EMAILS:
                        break
                        
                    msg_data = requests.get(
                        f"https://www.googleapis.com/gmail/v1/users/me/messages/{msg_meta['id']}", 
                        headers=headers
                    ).json()
                    
                    # Convert Gmail internalDate (ms) to YYYY-MM-DD
                    ms_timestamp = int(msg_data.get('internalDate', 0))
                    formatted_date = datetime.fromtimestamp(ms_timestamp / 1000.0).strftime('%Y-%m-%d') if ms_timestamp else datetime.now().strftime('%Y-%m-%d')
                    
                    payload = {
                        "email_body": msg_data.get('snippet', ''),
                        "source_email_id": msg_meta['id'],
                        "user_id": user_id,
                        "applied_date": formatted_date
                    }
                    
                    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload))
                    messages_processed += 1
                
                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break

        # ==========================================
        # POST-PROCESSING
        # ==========================================
        if months > 0:
            print(f"Resetting scan_history_months for user {user_id} after deep scan.")
            supabase.table("users").update({"scan_history_months": 0}).eq("id", user_id).execute()
        
        print(f"Sent {messages_processed} real emails to SQS.")
        return {"statusCode": 200, "body": f"Production mode: {messages_processed} real emails processed"}

    except requests.exceptions.HTTPError as he:
         print(f"HTTP Error fetching emails: {he}")
         if he.response is not None:
             print(f"Response Content: {he.response.text}")
         return {"statusCode": 500, "body": f"HTTP Error: {str(he)}"}
    except Exception as e:
        print(f"Error fetching real emails for user {user_id}: {str(e)}")
        return {"statusCode": 500, "body": f"Error: {str(e)}"}