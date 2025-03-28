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

    # Find necessary columns dynamically
    col_first_name = find_column(headers, "First Name")
    col_second_name = find_column(headers, "Second Name", optional=True)  # Optional
    col_last_name = find_column(headers, "Last Name")
    col_birthday = find_column(headers, "Birthday")
    col_departure = find_column(headers, "Departure date")
    col_check_out = find_column(headers, "Check-out date")
    col_medical_conditions = find_column(headers, "Medical Conditions we should be aware of")
    col_accessibility_needs = find_column(headers, "Accessibility needs")

    if not col_first_name or not col_last_name or not col_birthday:
        return jsonify({"error": "Required columns not found in sheet"}), 500

    for attendee in attendees:
        stored_first_name = attendee.get(col_first_name, "").strip().lower()
        stored_second_name = attendee.get(col_second_name, "").strip().lower() if col_second_name else ""
        stored_last_name = attendee.get(col_last_name, "").strip().lower()
        stored_birthday = attendee.get(col_birthday, "").strip()

        # Convert Birthday format
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

            # Convert Departure & Check-out Dates (fix missing values)
            stored_departure = attendee.get(col_departure, "").strip()
            stored_check_out = attendee.get(col_check_out, "").strip()

            try:
                stored_departure = datetime.datetime.strptime(stored_departure, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                stored_departure = ""  # Keep empty if invalid

            try:
                stored_check_out = datetime.datetime.strptime(stored_check_out, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                stored_check_out = ""  # Keep empty if invalid

            # Medical Conditions & Accessibility Needs
            stored_medical_conditions = attendee.get(col_medical_conditions, "").strip()
            stored_accessibility_needs = attendee.get(col_accessibility_needs, "").strip()

            # Generate Passport & Flight Details URLs
            formatted_birthday = datetime.datetime.strptime(birthday, "%Y-%m-%d").strftime("%m%d%Y")
            passport_filename = f"{first_name}{last_name}_{formatted_birthday}.jpg"
            passport_file_id = search_passport(passport_filename)
            passport_url = f"/passport/{passport_file_id}" if passport_file_id else None

            flight_details_filename = f"{first_name}{last_name}_{formatted_birthday}_flight.pdf"
            flight_details_file_id = search_flight_details(flight_details_filename)
            flight_details_url = f"/flight_details/{flight_details_file_id}" if flight_details_file_id else None

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
                "Check-out Date": stored_check_out,  
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
            })

    return jsonify({"error": "Attendee not found"}), 404


def find_column(headers, column_name, optional=False):
    """
    Find the exact column name dynamically.
    If optional=True, return None if not found.
    """
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

def search_passport(filename):
    query = f"name contains '{filename}' and '{PASSPORT_DRIVE_FOLDER_ID}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]
    return None

def search_flight_details(filename):
    query = f"name contains '{filename}' and '{FLIGHT_DETAILS_DRIVE_FOLDER_ID}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]
    return None

@app.route("/passport/<file_id>")
def get_passport_image(file_id):
    file_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}

    response = requests.get(file_url, headers=headers)
    if response.status_code == 200:
        return send_file(BytesIO(response.content), mimetype="image/jpeg")

    return jsonify({"error": "Image not found"}), 404

@app.route("/flight_details/<file_id>")
def download_flight_details(file_id):
    try:
        file_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        headers = {"Authorization": f"Bearer {creds.token}"}

        response = requests.get(file_url, headers=headers)
        if response.status_code == 200:
            return send_file(
                BytesIO(response.content), 
                mimetype="application/pdf", 
                as_attachment=True, 
                download_name="flight_details.pdf"
            )

        return jsonify({"error": "Flight details not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
