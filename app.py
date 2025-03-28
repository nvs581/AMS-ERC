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

CREDENTIALS_FILE01 = "/etc/secrets/CREDENTIALS_FILE01.json"
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
PASSPORT_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_PASSPORT_FOLDER_ID")
FLIGHT_DETAILS_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FLIGHT_DETAILS_FOLDER_ID")
ACCESS_PASSCODE = os.getenv("ACCESS_PASSCODE")

creds = Credentials.from_service_account_file(CREDENTIALS_FILE01, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open(SPREADSHEET_NAME).sheet1  
drive_service = build("drive", "v3", credentials=creds)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/search", methods=["GET"])
def search_attendee():
    first_name = request.args.get("first_name", "").strip()
    last_name = request.args.get("last_name", "").strip()
    birthday = request.args.get("birthday", "").strip()

    if not first_name or not last_name or not birthday:
        return jsonify({"error": "Missing first name, last name, or birthday"}), 400

    attendees = sheet.get_all_records()

    for attendee in attendees:
        stored_first_name = attendee.get("First Name", "").strip()
        stored_last_name = attendee.get("Last Name", "").strip()
        stored_birthday = attendee.get("Birthday", "").strip()

        try:
            stored_birthday = datetime.datetime.strptime(stored_birthday, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass  

        if (
            stored_first_name.lower() == first_name.lower() and
            stored_last_name.lower() == last_name.lower() and
            stored_birthday == birthday
        ):
            full_name = f"{stored_first_name} {stored_last_name}"
            formatted_birthday = datetime.datetime.strptime(birthday, "%Y-%m-%d").strftime("%m%d%Y")
            passport_filename = f"{first_name}{last_name}_{formatted_birthday}.jpg"
            passport_file_id = search_passport(passport_filename)
            passport_url = f"/passport/{passport_file_id}" if passport_file_id else None
            flight_details_filename = f"{first_name}{last_name}_{formatted_birthday}_flight.pdf"
            flight_details_file_id = search_flight_details(flight_details_filename)
            flight_details_url = f"/flight_details/{flight_details_file_id}" if flight_details_file_id else None

            return jsonify({
                "First Name": stored_first_name,
                "Last Name": stored_last_name,
                "Full Name": full_name,
                "Birthday": stored_birthday,
                "Event Name": attendee.get("Event Name", ""),
                "Hotel Name": attendee.get("Hotel Name", ""),
                "Passport URL": passport_url,
                "Flight Details URL": flight_details_url,
            })

    return jsonify({"error": "Attendee not found"}), 404

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
