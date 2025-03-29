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
PASSPORT_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_PASSPORT_FOLDER_ID")
FLIGHT_DETAILS_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FLIGHT_DETAILS_FOLDER_ID")
ACCESS_PASSCODE = os.getenv("ACCESS_PASSCODE")

creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open(SPREADSHEET_NAME).sheet1  
drive_service = build("drive", "v3", credentials=creds)

@app.route("/")
def home():
    return render_template("index.html")

from flask import Flask, request, jsonify
import datetime

@app.route("/search", methods=["GET"])
def search_attendee():
    first_name = request.args.get("first_name", "").strip().lower()
    last_name = request.args.get("last_name", "").strip().lower()
    birthday = request.args.get("birthday", "").strip()

    if not first_name or not last_name or not birthday:
        return jsonify({"error": "Missing first name, last name, or birthday"}), 400

    attendees = sheet.get_all_records()
    headers = sheet.row_values(1)

    # Column names using original format
    col_submission_id = find_column(headers, "Submission ID|hidden-1")
    col_first_name = find_column(headers, "First Name|name-1-first-name")
    col_last_name = find_column(headers, "Last Name|name-1-last-name")
    col_birthday = find_column(headers, "Birthday|date-1")
    col_departure = find_column(headers, "Departure Date|date-2")
    col_return = find_column(headers, "Return Date|date-3")
    col_medical_conditions = find_column(headers, "Medical Condition/s|textarea-2")
    col_accessibility_needs = find_column(headers, "Accessibility Need/s|textarea-3")
    col_email = find_column(headers, "Email Address|email-1")
    col_event_name = find_column(headers, "Event Name|select-1")
    col_hotel_name = find_column(headers, "Hotel Name|text-1")
    col_emergency_contact_relationship = find_column(headers, "Relationship to Emergency Contact|text-2")
    col_emergency_contact_first_name = find_column(headers, "First Name|name-2-first-name")
    col_emergency_contact_last_name = find_column(headers, "Last Name|name-2-last-name")
    col_emergency_contact_phone = find_column(headers, "Phone Number|phone-1")
    col_food_allergies = find_column(headers, "Food Allergies and Dietary Restrictions|checkbox-1")
    col_other_dietary = find_column(headers, "Other Food & Dietary Restriction|textarea-1")
    col_privacy_policy = find_column(headers, "I agree to the event’s privacy policy and consent to the collection of my information for event purposes.|radio-1")
    col_photography_consent = find_column(headers, "I grant permission for event photography and video recordings that may include my image.|radio-2")
    col_passport = find_column(headers, "Passport|upload-2")
    col_flight_details = find_column(headers, "Flight Details|upload-1")

    if not col_first_name or not col_last_name or not col_birthday or not col_submission_id:
        return jsonify({"error": "Required columns not found in sheet"}), 500

    for attendee in attendees:
        stored_submission_id = str(attendee.get(col_submission_id, "")).strip()
        stored_first_name = attendee.get(col_first_name, "").strip().lower()
        stored_last_name = attendee.get(col_last_name, "").strip().lower()
        stored_birthday = attendee.get(col_birthday, "").strip()

        # Convert Birthday format
        try:
            stored_birthday = datetime.datetime.strptime(stored_birthday, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass  

        if stored_first_name == first_name and stored_last_name == last_name and stored_birthday == birthday:
            full_name = f"{stored_first_name} {stored_last_name}".strip()

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

            # Ensure files belong to the correct Submission ID
            stored_passport_url = attendee.get(col_passport, "").strip()
            stored_flight_details_url = attendee.get(col_flight_details, "").strip()
            
            passport_url = stored_passport_url if stored_passport_url and stored_submission_id else None
            flight_details_url = stored_flight_details_url if stored_flight_details_url and stored_submission_id else None

            return jsonify({
                "First Name": stored_first_name,
                "Last Name": stored_last_name,
                "Full Name": full_name,
                "Birthday": stored_birthday,
                "Email Address": attendee.get(col_email, ""),
                "Event Name": attendee.get(col_event_name, ""),
                "Hotel Name": attendee.get(col_hotel_name, ""),
                "Departure Date": stored_departure,  
                "Return Date": stored_return,  
                "Emergency Contact Relationship": attendee.get(col_emergency_contact_relationship, ""),
                "Emergency Contact First Name": attendee.get(col_emergency_contact_first_name, ""),
                "Emergency Contact Last Name": attendee.get(col_emergency_contact_last_name, ""),
                "Emergency Contact Phone": attendee.get(col_emergency_contact_phone, ""),
                "Food Allergies and Dietary Restrictions": attendee.get(col_food_allergies, ""),
                "Other Food & Dietary Restriction": attendee.get(col_other_dietary, ""),
                "Medical Conditions": attendee.get(col_medical_conditions, ""),  
                "Accessibility Needs": attendee.get(col_accessibility_needs, ""),  
                "Consent Privacy Policy": attendee.get(col_privacy_policy, ""),
                "Consent Photography": attendee.get(col_photography_consent, ""),
                "Passport URL": attendee.get("Passport|upload-2", "").strip(),
                "Flight Details URL": attendee.get("Flight Details|upload-1", "").strip(),
            })

    return jsonify({"error": "Attendee not found"}), 404

def find_column(headers, column_name, optional=False):
    """
    Find the exact column name dynamically using unique format.
    If optional=True, return None if not found.
    """
    for header in headers:
        if header.split('|')[0].strip().lower() == column_name.lower():
            return header
    return None if optional else column_name

@app.route("/validate_passcode", methods=["POST"])
def validate_passcode():
    data = request.json
    entered_passcode = data.get("passcode")

    if entered_passcode == ACCESS_PASSCODE:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Incorrect passcode"}), 403

@app.route("/passport/<submission_id>")
def get_passport_image(submission_id):
    attendee = next((a for a in sheet.get_all_records() if a.get("Submission ID|hidden-1") == submission_id), None)
    if not attendee:
        return jsonify({"error": "Attendee not found"}), 404

    passport_url = attendee.get("Passport|upload-2", "").strip()
    if not passport_url:
        return jsonify({"error": "Passport image not found"}), 404

    response = requests.get(passport_url)
    if response.status_code == 200:
        return send_file(BytesIO(response.content), mimetype="image/jpeg")

    return jsonify({"error": "Image not found"}), 404

@app.route("/flight_details/<submission_id>")
def download_flight_details(submission_id):
    attendee = next((a for a in sheet.get_all_records() if a.get("Submission ID|hidden-1") == submission_id), None)
    if not attendee:
        return jsonify({"error": "Attendee not found"}), 404

    flight_details_url = attendee.get("Flight Details|upload-1", "").strip()
    if not flight_details_url:
        return jsonify({"error": "Flight details not found"}), 404

    response = requests.get(flight_details_url)
    if response.status_code == 200:
        return send_file(
            BytesIO(response.content), 
            mimetype="application/pdf", 
            as_attachment=True, 
            download_name="flight_details.pdf"
        )
    return jsonify({"error": "Flight details not found"}), 404

if __name__ == "__main__":
    app.run(debug=True)
