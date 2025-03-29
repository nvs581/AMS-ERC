from flask import Flask, request, jsonify, render_template, send_file
import gspread
from google.oauth2.service_account import Credentials
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

    attendees = sheet.get_all_records()
    headers = sheet.row_values(1)

    col_first_name = find_column(headers, "First Name")
    col_second_name = find_column(headers, "Second Name", optional=True)
    col_last_name = find_column(headers, "Last Name")
    col_birthday = find_column(headers, "Birthday")
    col_departure = find_column(headers, "Departure date")
    col_Return = find_column(headers, "Return date")
    col_medical_conditions = find_column(headers, "Medical Conditions we should be aware of")
    col_accessibility_needs = find_column(headers, "Accessibility needs")
    col_submission_id = find_column(headers, "Submission ID")
    col_respondent_id = find_column(headers, "Respondent ID")
    col_passport_url = find_column(headers, "Passport URL")
    col_flight_details_url = find_column(headers, "Flight Details URL")

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
            stored_Return = attendee.get(col_Return, "").strip()

            try:
                stored_departure = datetime.datetime.strptime(stored_departure, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                stored_departure = ""

            try:
                stored_Return = datetime.datetime.strptime(stored_Return, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                stored_Return = ""

            stored_medical_conditions = attendee.get(col_medical_conditions, "").strip()
            stored_accessibility_needs = attendee.get(col_accessibility_needs, "").strip()
            submission_id = attendee.get(col_submission_id, "")
            respondent_id = attendee.get(col_respondent_id, "")
            passport_url = attendee.get(col_passport_url, "")
            flight_details_url = attendee.get(col_flight_details_url, "")

            return jsonify({
                "First Name": stored_first_name,
                "Second Name": stored_second_name,
                "Last Name": stored_last_name,
                "Full Name": full_name,
                "Birthday": stored_birthday,
                "Email Address": attendee.get("Email Address", ""),
                "Event Name": attendee.get("Event Name", ""),
                "Hotel Name": attendee.get("Hotel Name", ""),
                "Departure Date": stored_departure,  
                "Return Date": stored_Return,  
                "Emergency Contact Name": attendee.get("Emergency Contact Name", ""),
                "Emergency Contact Number": attendee.get("Emergency Contact Number", ""),
                "Relationship to Emergency Contact": attendee.get("Relationship to Emergency Contact", ""),
                "Food Allergies and Dietary Restrictions": attendee.get("Food Allergies and Dietary Restrictions", ""),
                "Medical Conditions We Should be Aware Of": stored_medical_conditions,  
                "Accessibility Needs": stored_accessibility_needs,  
                "Consent Privacy Policy": attendee.get("I agree to the event’s privacy policy and consent to the collection of my information for event purposes.", ""),
                "Consent Data Usage": attendee.get("By checking this box, you confirm that you consent to the use of your data for event planning.", ""),
                "Consent Event Photography": attendee.get("I grant permission for event photography and video recordings that may include my image.", ""),
                "Consent Promotional Photos": attendee.get("Choose ‘Yes’ if you allow photos and videos of you to be taken during the event for promotional purposes.", ""),
                "Passport URL": passport_url,
                "Flight Details URL": flight_details_url,
                "Submission ID": submission_id,
                "Respondent ID": respondent_id
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
