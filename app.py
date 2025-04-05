from flask import Flask, request, jsonify, render_template, send_file
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime
import requests
from io import BytesIO
import os
from fuzzywuzzy import fuzz

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

def find_column(headers, column_name, optional=False):
    """
    Find the exact column name dynamically using unique format.
    If optional=True, return None if not found.
    """
    for header in headers:
        if column_name.lower() in header.lower():
            return header
    return None if optional else column_name

@app.route("/search_suggestions", methods=["GET"])
def search_suggestions():
    """
    New endpoint to provide autocomplete suggestions as user types
    """
    query = request.args.get("query", "").strip().lower()
    
    if not query or len(query) < 2:
        return jsonify([])
        
    attendees = sheet.get_all_records()
    headers = sheet.row_values(1)
    
    col_submission_id = find_column(headers, "Submission ID|hidden-1")
    col_first_name = find_column(headers, "First Name|name-1-first-name")
    col_middle_name = find_column(headers, "Middle Name|name-1-middle-name")
    col_last_name = find_column(headers, "Last Name|name-1-last-name")
    col_delegates_role = find_column(headers, "Category")
    
    suggestions = []
    
    for attendee in attendees:
        first_name = attendee.get(col_first_name, "").strip()
        middle_name = attendee.get(col_middle_name, "").strip() 
        last_name = attendee.get(col_last_name, "").strip()
        full_name = f"{first_name} {middle_name} {last_name}".strip()
        role = attendee.get(col_delegates_role, "Not Specified").strip()
        submission_id = str(attendee.get(col_submission_id, "")).strip()
        
        # Check if query matches any part of the name
        if (query in first_name.lower() or 
            query in middle_name.lower() or 
            query in last_name.lower() or
            query in full_name.lower()):
            
            # Add to suggestions
            suggestions.append({
                "name": full_name,
                "role": role,
                "submission_id": submission_id,
                "first_name": first_name.lower(),
                "middle_name": middle_name.lower().replace(".", "").replace(" ", ""),
                "last_name": last_name.lower()
            })
    
    return jsonify(suggestions)

@app.route("/search", methods=["GET"])
def search_attendee():
    """
    Updated search endpoint to handle both submission_id and name-based searches
    """
    # Check if searching by submission ID
    submission_id = str(request.args.get("submission_id", "").strip())
    
    # Get all records and headers once
    attendees = sheet.get_all_records()
    headers = sheet.row_values(1)
    
    # Find all column names
    col_submission_id = find_column(headers, "Submission ID|hidden-1")
    col_first_name = find_column(headers, "First Name|name-1-first-name")
    col_middle_name = find_column(headers, "Middle Name|name-1-middle-name")
    col_last_name = find_column(headers, "Last Name|name-1-last-name")
    col_birthday = find_column(headers, "Birthday|date-1")
    col_delegates_role = find_column(headers, "Category")
    col_departure = find_column(headers, "Departure Date|date-2")
    col_return = find_column(headers, "Return Date|date-3")
    col_medical_conditions = find_column(headers, "Medical Condition/s|textarea-2")
    col_accessibility_needs = find_column(headers, "Accessibility Need/s|textarea-3")
    col_email = find_column(headers, "Email Address|email-1")
    col_room_type = find_column(headers, "Room Type|select-1")
    col_emergency_contact_relationship = find_column(headers, "Relationship to Emergency Contact|text-2")
    col_emergency_contact_first_name = find_column(headers, "First Name|name-2-first-name")
    col_emergency_contact_last_name = find_column(headers, "Last Name|name-2-last-name")
    col_emergency_contact_phone = find_column(headers, "Phone Number|phone-1")
    col_food_allergies = find_column(headers, "Food Allergies and Dietary Restrictions|checkbox-1")
    col_other_dietary = find_column(headers, "Other Food and Dietary Restriction|textarea-1")
    col_privacy_policy = find_column(headers, "I agree to the event's privacy policy and consent to the collection of my information for event purposes.|radio-1")
    col_photography_consent = find_column(headers, "I grant permission for event photography and video recordings that may include my image.|radio-2")
    col_passport = find_column(headers, "Passport|upload-2")
    col_flight_details = find_column(headers, "Flight Details|upload-1")

    if not col_submission_id or not col_first_name or not col_middle_name or not col_last_name or not col_birthday:
        return jsonify({"error": "Required columns not found in sheet"}), 500
    
    # Search by submission ID if provided
    if submission_id:
        for attendee in attendees:
            stored_submission_id = str(attendee.get(col_submission_id, "")).strip()
            
            if stored_submission_id == submission_id:
                # Process this attendee's data
                return process_attendee_data(attendee, headers)
                
        return jsonify({"error": "Attendee not found"}), 404
    
    # Otherwise, search by name components (original functionality)
    first_name = request.args.get("first_name", "").strip().lower()
    middle_name = request.args.get("middle_name", "").strip().lower().replace(".", "").replace(" ", "")
    last_name = request.args.get("last_name", "").strip().lower()

    if not first_name or not last_name:
        return jsonify({"error": "Missing name information"}), 400
    
    title_prefixes = ["mr.", "ms.", "mrs.", "dr.", "prof.", "sir", "madam"]

    for attendee in attendees:
        stored_first_name = attendee.get(col_first_name, "").strip().lower()
        stored_middle_name = attendee.get(col_middle_name, "").strip().lower().replace(".", "").replace(" ", "")
        stored_last_name = attendee.get(col_last_name, "").strip().lower()

        name_parts = stored_first_name.split()
        if name_parts and name_parts[0] in title_prefixes:
            stored_first_name_cleaned = " ".join(name_parts[1:]) 
        else:
            stored_first_name_cleaned = stored_first_name 

        middle_name_match = fuzz.partial_ratio(stored_middle_name, middle_name) > 80

        if stored_first_name_cleaned == first_name and middle_name_match and stored_last_name == last_name:
            # Process this attendee's data
            return process_attendee_data(attendee, headers)

    return jsonify({"error": "Attendee not found"}), 404

def process_attendee_data(attendee, headers):
    """
    Process attendee data and return formatted JSON response
    Extracted to avoid code duplication
    """
    # Find all column names
    col_submission_id = find_column(headers, "Submission ID|hidden-1")
    col_first_name = find_column(headers, "First Name|name-1-first-name")
    col_middle_name = find_column(headers, "Middle Name|name-1-middle-name")
    col_last_name = find_column(headers, "Last Name|name-1-last-name")
    col_birthday = find_column(headers, "Birthday|date-1")
    col_delegates_role = find_column(headers, "Category")
    col_departure = find_column(headers, "Departure Date|date-2")
    col_return = find_column(headers, "Return Date|date-3")
    col_medical_conditions = find_column(headers, "Medical Condition/s|textarea-2")
    col_accessibility_needs = find_column(headers, "Accessibility Need/s|textarea-3")
    col_email = find_column(headers, "Email Address|email-1")
    col_room_type = find_column(headers, "Room Type|select-1")
    col_emergency_contact_relationship = find_column(headers, "Relationship to Emergency Contact|text-2")
    col_emergency_contact_first_name = find_column(headers, "First Name|name-2-first-name")
    col_emergency_contact_last_name = find_column(headers, "Last Name|name-2-last-name")
    col_emergency_contact_phone = find_column(headers, "Phone Number|phone-1")
    col_food_allergies = find_column(headers, "Food Allergies and Dietary Restrictions|checkbox-1")
    col_other_dietary = find_column(headers, "Other Food and Dietary Restriction|textarea-1")
    col_privacy_policy = find_column(headers, "I agree to the event’s privacy policy and consent to the collection of my information for event purposes.|radio-1")
    col_photography_consent = find_column(headers, "I grant permission for event photography and video recordings that may include my image.|radio-2")
    col_passport = find_column(headers, "Passport|upload-2")
    col_flight_details = find_column(headers, "Flight Details|upload-1")
    col_proof_of_payment = find_column(headers, "Proof of Payment|upload-3")

    # 
    col_airline_1 = find_column(headers, "Airline|air-line-1")
    col_flight_number_1 = find_column(headers, "Flight Number|fn-1")
    col_country_origin = find_column(headers, "Country of Origin")
    col_departure_time_1 = find_column(headers, "Departure Time|deptime-1")
    col_arrival_bali = find_column(headers, "arrival-bali")
    col_airline_2 = find_column(headers, "Airline|air-line-2")
    col_flight_number_2 = find_column(headers, "Flight Number|fn-2")
    col_departure_time_2 = find_column(headers, "Departure Time|deptime-2")

    
    # Basic attendee info
    stored_submission_id = str(attendee.get(col_submission_id, "")).strip()
    stored_first_name = attendee.get(col_first_name, "").strip()
    stored_middle_name = attendee.get(col_middle_name, "").strip()
    stored_last_name = attendee.get(col_last_name, "").strip()
    stored_birthday = attendee.get(col_birthday, "").strip()

    # 
    airline_1 = attendee.get(col_airline_1, "").strip()
    flight_number_1 = attendee.get(col_flight_number_1, "").strip()
    country_origin = attendee.get(col_country_origin, "").strip()
    departure_time_1 = attendee.get(col_departure_time_1, "").strip()
    arrival_bali = attendee.get(col_arrival_bali, "").strip()
    airline_2 = attendee.get(col_airline_2, "").strip()
    flight_number_2 = attendee.get(col_flight_number_2, "").strip()
    departure_time_2 = attendee.get(col_departure_time_2, "").strip()

    
    # Format full name
    full_name = f"{stored_first_name} {stored_middle_name} {stored_last_name}".strip()
    
    # Format birthday
    try:
        stored_birthday = datetime.datetime.strptime(stored_birthday, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        stored_birthday = ""
    
    # Format dates
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
    
    # Handle food allergies
    food_allergies = attendee.get(col_food_allergies, "").strip()
    other_dietary_restriction = attendee.get(col_other_dietary, "").strip()

    if "Others" in food_allergies:
        allergies_list = [item.strip() for item in food_allergies.split(",")]
        allergies_list = [other_dietary_restriction if item == "Others" else item for item in allergies_list]
        food_allergies = ", ".join(filter(None, allergies_list))
    
    # Handle file URLs
    stored_passport_url = attendee.get(col_passport, "").strip()
    stored_flight_details_url = attendee.get(col_flight_details, "").strip()
    stored_proof_of_payment_url = attendee.get(col_proof_of_payment, "").strip()

    passport_url = stored_passport_url if stored_passport_url and stored_submission_id else None
    flight_details_url = stored_flight_details_url if stored_flight_details_url and stored_submission_id else None
    proof_of_payment_url = stored_proof_of_payment_url if stored_proof_of_payment_url and stored_submission_id else None
    
    # Return formatted JSON
    return jsonify({
        "First Name": stored_first_name,
        "Middle Name": stored_middle_name,
        "Last Name": stored_last_name,
        "Full Name": full_name,
        "Birthday": stored_birthday,
        "Email Address": attendee.get(col_email, ""),
        "Room Type": attendee.get(col_room_type, ""),
        "Departure Date": stored_departure,  
        "Return Date": stored_return,  
        "Emergency Contact Relationship": attendee.get(col_emergency_contact_relationship, ""),
        "Emergency Contact First Name": attendee.get(col_emergency_contact_first_name, ""),
        "Emergency Contact Last Name": attendee.get(col_emergency_contact_last_name, ""),
        "Emergency Contact Phone": attendee.get(col_emergency_contact_phone, ""),
        "Food Allergies and Dietary Restrictions": food_allergies,  
        "Medical Conditions": attendee.get(col_medical_conditions, ""),  
        "Accessibility Needs": attendee.get(col_accessibility_needs, ""),  
        "Consent Privacy Policy": attendee.get(col_privacy_policy, ""),
        "Consent Photography": attendee.get(col_photography_consent, ""),
        "Passport URL": passport_url,
        "Flight Details URL": flight_details_url,
        "Proof of Payment URL": proof_of_payment_url,
        "Delegates Role": attendee.get(col_delegates_role, "Not Specified"),
        "Airline (Arrival)": airline_1,
        "Flight Number (Arrival)": flight_number_1,
        "Country of Origin": country_origin,
        "Departure Time (Arrival)": departure_time_1,
        "Arrival Time in Bali": arrival_bali,
        "Airline (Departure)": airline_2,
        "Flight Number (Departure)": flight_number_2,
        "Departure Time (Departure)": departure_time_2
    })

@app.route("/validate_passcode", methods=["POST"])
def validate_passcode():
    data = request.json
    entered_passcode = data.get("passcode")

    if entered_passcode == ACCESS_PASSCODE:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Incorrect passcode"}), 403

@app.route("/proof_of_payment/<submission_id>")
def download_proof_of_payment(submission_id):
    attendee = next((a for a in sheet.get_all_records() if str(a.get("Submission ID|hidden-1")) == submission_id), None)
    if not attendee:
        return jsonify({"error": "Attendee not found"}), 404

    proof_of_payment_url = attendee.get("Proof of Payment|upload-3", "").strip()
    if not proof_of_payment_url:
        return jsonify({"error": "Proof of Payment not found"}), 404

    response = requests.get(proof_of_payment_url)
    if response.status_code == 200:
        return send_file(
            BytesIO(response.content),
            mimetype="application/pdf",  # Or whatever mime type matches the file
            as_attachment=True,
            download_name="proof_of_payment.pdf"
        )
    return jsonify({"error": "Proof of Payment not found"}), 404

@app.route("/passport/<submission_id>")
def get_passport_image(submission_id):
    attendee = next((a for a in sheet.get_all_records() if str(a.get("Submission ID|hidden-1")) == submission_id), None)
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
    attendee = next((a for a in sheet.get_all_records() if str(a.get("Submission ID|hidden-1")) == submission_id), None)
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