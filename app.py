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
    col_second_name = find_column(headers, "Second Name", optional=True)  # Optional
    col_last_name = find_column(headers, "Last Name")
    col_birthday = find_column(headers, "Birthday")
    col_departure = find_column(headers, "Departure Date")
    col_return = find_column(headers, "Return Date")
    col_medical_conditions = find_column(headers, "Medical Conditions We Should be Aware Of", optional=True)
    col_accessibility_needs = find_column(headers, "Accessibility Needs", optional=True)

    if not col_first_name or not col_last_name or not col_birthday:
        return jsonify({"error": "Required columns not found in sheet"}), 500

    for attendee in attendees:
        stored_first_name = attendee.get(col_first_name, "").strip().lower()
        stored_second_name = attendee.get(col_second_name, "").strip().lower() if col_second_name else ""
        stored_last_name = attendee.get(col_last_name, "").strip().lower()
        stored_birthday = attendee.get(col_birthday, "").strip()

        try:
            stored_birthday = datetime.datetime.strptime(stored_birthday, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass  

        if stored_first_name == first_name and stored_last_name == last_name and stored_birthday == birthday:
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

            stored_medical_conditions = attendee.get(col_medical_conditions, "").strip()
            stored_accessibility_needs = attendee.get(col_accessibility_needs, "").strip()

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
                "Departure Date": stored_departure,  
                "Return Date": stored_return,  
                "Medical Conditions": stored_medical_conditions,  
                "Accessibility Needs": stored_accessibility_needs,  
                "Passport URL": passport_url,
                "Flight Details URL": flight_details_url,
            })

    return jsonify({"error": "Attendee not found"}), 404

def find_column(headers, column_name, optional=False):
    for header in headers:
        if header.lower() == column_name.lower():
            return header
    return None if optional else column_name

if __name__ == "__main__":
    app.run(debug=True)
