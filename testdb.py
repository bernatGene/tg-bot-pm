from oauth2client.service_account import ServiceAccountCredentials
import gspread



scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
credentials = ServiceAccountCredentials.from_json_keyfile_name("pm-db-371218-7f2376f866b4.json", scopes) 
ServiceAccountCredentials.from_json_keyfile_dict()
file = gspread.authorize(credentials) # authenticate the JSON key with gspread
sheet = file.open("TheTimeSink") #open sheet
sheet = sheet.sheet1.get("A1") #replace sheet_name with the name that corresponds to yours, e.g, it can be sheet1
print(sheet)

