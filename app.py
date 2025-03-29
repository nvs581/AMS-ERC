from flask import Flask, request, jsonify, render_template, send_file
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime
import requests
from io import BytesIO
import os

app = Flask(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",  
    "https://www.googleapis.com/auth/drive.metadata.readonly",  
    "https://www.googleapis.com/auth/drive.readonly" 
]

CREDENTIALS_FILE = "/etc/secrets/credentials.json"
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
ACCESS_PASSCODE = os.getenv("ACCESS_PASSCODE")

creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open(SPREADSHEET_NAME).sheet1  
drive_service = build("drive", "v3", credentials=creds)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/search", methods=["GET"])
def search_attendee():
    first_name = request.args.get("first_name", "").strip().lower()
    last_name = request.args.get("last_name", "").strip().lower()
    birthday = request.args.get("birthday", "").strip()

    if not first_name or not last_name or not birthday:
        return jsonify({"error": "Missing first name, last name, or birthday"}), 400

    headers = sheet.row_values(1)
    unique_headers = []
    seen = {}
    for header in headers:
        if header in seen:
            seen[header] += 1
            new_header = f"{header}_{seen[header]}"
        else:
            seen[header] = 0
            new_header = header
        unique_headers.append(new_header)

    attendees = sheet.get_all_records(expected_headers=unique_headers)
    
    col_first_name = find_column(unique_headers, "First Name")
    col_second_name = find_column(unique_headers, "Second Name", optional=True)
    col_last_name = find_column(unique_headers, "Last Name")
    col_birthday = find_column(unique_headers, "Birthday")
    col_departure = find_column(unique_headers, "Departure Date")
    col_return = find_column(unique_headers, "Return Date")
    col_medical_conditions = find_column(unique_headers, "Medical Conditions we should be aware of")
    col_accessibility_needs = find_column(unique_headers, "Accessibility needs")
    col_submission_id = find_column(unique_headers, "Submission ID")
    col_respondent_id = find_column(unique_headers, "Respondent ID")
    col_passport_url = find_column(unique_headers, "Passport")
    col_flight_details_url = find_column(unique_headers, "Flight Details")

    if not col_first_name or not col_last_name or not col_birthday:
        return jsonify({"error": "Required columns not found in sheet"}), 500

    for attendee in attendees:
        stored_first_name = attendee.get(col_first_name, "").strip().lower()
        stored_second_name = attendee.get(col_second_name, "").strip().lower() if col_second_name else ""
        stored_last_name = attendee.get(col_last_name, "").strip().lower()
        stored_birthday = attendee.get(col_birthday, "").strip()

        try:
            stored_birthday = datetime.datetime.strptime(stored_birthday, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass  

        if (
            stored_first_name == first_name
            and stored_last_name == last_name
            and stored_birthday == birthday
        ):
            full_name = f"{stored_first_name} {stored_second_name} {stored_last_name}".strip()

            stored_departure = attendee.get(col_departure, "").strip()
            stored_return = attendee.get(col_return, "").strip()

            try:
                stored_departure = datetime.datetime.strptime(stored_departure, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                stored_departure = ""

            try:
                stored_return = datetime.datetime.strptime(stored_return, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                stored_return = ""

            return jsonify({
                "First Name": stored_first_name,
                "Second Name": stored_second_name,
                "Last Name": stored_last_name,
                "Full Name": full_name,
                "Birthday": stored_birthday,
                "Departure Date": stored_departure,
                "Return Date": stored_return,
                "Medical Conditions": attendee.get(col_medical_conditions, ""),
                "Accessibility Needs": attendee.get(col_accessibility_needs, ""),
                "Submission ID": attendee.get(col_submission_id, ""),
                "Respondent ID": attendee.get(col_respondent_id, ""),
                "Passport URL": attendee.get(col_passport_url, ""),
                "Flight Details URL": attendee.get(col_flight_details_url, "")
            })

    return jsonify({"error": "Attendee not found"}), 404

def find_column(headers, column_name, optional=False):
    for header in headers:
        if header.lower() == column_name.lower():
            return header
    return None if optional else column_name

@app.route("/validate_passcode", methods=["POST"])
def validate_passcode():
    data = request.json
    entered_passcode = data.get("passcode")

    if entered_passcode == ACCESS_PASSCODE:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Incorrect passcode"}), 403

if __name__ == "__main__":
    app.run(debug=True)
