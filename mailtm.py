import requests
import time
import json
import aio_msgpack_rpc

MAILTM_HEADERS = {   
    "Accept": "application/json",
    "Content-Type": "application/json" 
}

class MailTmError(Exception):
    pass

def _make_mailtm_request(request_fn, timeout = 600):
    tstart = time.monotonic()
    error = None
    status_code = None
    while time.monotonic() - tstart < timeout:
        try:
            r = request_fn()
            status_code = r.status_code
            if status_code == 200 or status_code == 201:
                return r.json()
            if status_code != 429:
                break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            error = e
        time.sleep(1.0)
    
    if error is not None:
        raise MailTmError(error) from error
    if status_code is not None:
        raise MailTmError(f"Status code: {status_code}")
    if time.monotonic() - tstart >= timeout:
        raise MailTmError("timeout")
    raise MailTmError("unknown error")

def get_mailtm_domains():
    def _domain_req():
        return requests.get("https://api.mail.tm/domains", headers = MAILTM_HEADERS)
    
    r = _make_mailtm_request(_domain_req)

    return [ x['domain'] for x in r ]

def create_mailtm_account(address, password):
    account = json.dumps({"address": address, "password": password})   
    def _acc_req():
        return requests.post("https://api.mail.tm/accounts", data=account, headers=MAILTM_HEADERS)

    r = _make_mailtm_request(_acc_req)
    assert len(r['id']) > 0

seen_email_ids = set()

def list_email_headers(token, page=1):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"https://api.mail.tm/messages?page={page}", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise MailTmError(f"Error fetching emails: {response.status_code}")

def read_email(token, email_id):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"https://api.mail.tm/messages/{email_id}", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise MailTmError(f"Error reading email: {response.status_code}")
    
def authenticate(email, password):
    payload = json.dumps({"address": email, "password": password})
    response = requests.post("https://api.mail.tm/token", data=payload, headers=MAILTM_HEADERS)
    if response.status_code == 200:
        return response.json()['token']
    else:
        raise MailTmError(f"Error during authentication: {response.status_code}")
    
def check_for_new_emails(token):
    global seen_email_ids
    new_emails = []
    emails = list_email_headers(token)['hydra:member']
    
    for email in emails:
        if email['id'] not in seen_email_ids:
            new_emails.append(email)
            seen_email_ids.add(email['id'])

    return new_emails

async def notify_server(title, body):
    client = aio_msgpack_rpc.Client("localhost", 18000)
    await client.call('on_new_mail', title, body)
    await client.stop()

def process_new_emails(new_emails):
    # Loop through new emails and notify the server
    for email in new_emails:
        asyncio.run(notify_server(email['title'], email['body']))

if __name__ == '__main__':
    print("Main execution started.")
    domains = get_mailtm_domains()
    print(f"Domains retrieved: {domains}")

    if domains:
        email = f'testuser123@{domains[0]}'
        password = 'MayaMulei25*@123457890'
        print("Creating authentication token...")
        token = authenticate(email, password)
        print(f"Token obtained: {token}")

        while True:
            print("Checking for new emails...")
            new_emails = check_for_new_emails(token)
            if new_emails:
                print(f"New emails found: {new_emails}")
                process_new_emails(new_emails)
            else:
                print("No new emails found.")
            print("Waiting for 60 seconds before next check.")
            time.sleep(60)  # Check every minute


