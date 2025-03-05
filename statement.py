import json
import xlsxwriter
from datetime import datetime
from flask import Flask, request, send_file

app = Flask(__name__)

# Sample function to generate Excel
def generate_excel(data, from_date, to_date):
    # Convert date strings to datetime objects for comparison
    from_date = datetime.strptime(from_date, "%Y-%m-%d")
    to_date = datetime.strptime(to_date, "%Y-%m-%d")

    # Extract transaction data
    transactions = data["data"]["attributes"]["transactionHistoryDetails"][0]["transactions"]

    # Filter transactions based on valueDateTime
    credit_transactions = []
    debit_transactions = []

    for txn in transactions:
        txn_date = datetime.strptime(txn["valueDateTime"].split("T")[0], "%Y-%m-%d")

        if from_date <= txn_date <= to_date:
            if txn["creditDebitIndicator"] == "Credit":
                credit_transactions.append(txn)
            else:
                debit_transactions.append(txn)

    # Create Excel file
    file_path = "transactions.xlsx"
    workbook = xlsxwriter.Workbook(file_path)
    
    # Add sheets
    credit_sheet = workbook.add_worksheet("Credit Transactions")
    debit_sheet = workbook.add_worksheet("Debit Transactions")

    headers = ["Transaction ID", "Amount", "Currency", "Booking Date", "Value Date", "Balance", "Transaction Info"]

    # Write headers
    for col, header in enumerate(headers):
        credit_sheet.write(0, col, header)
        debit_sheet.write(0, col, header)

    # Write credit transactions
    for row, txn in enumerate(credit_transactions, start=1):
        credit_sheet.write(row, 0, txn["transactionId"])
        credit_sheet.write(row, 1, txn["amount"]["amount"])
        credit_sheet.write(row, 2, txn["amount"]["currency"])
        credit_sheet.write(row, 3, txn["bookingDateTime"])
        credit_sheet.write(row, 4, txn["valueDateTime"])
        credit_sheet.write(row, 5, txn["balance"]["amount"]["amount"])
        credit_sheet.write(row, 6, txn["transactionInformation"])

    # Write debit transactions
    for row, txn in enumerate(debit_transactions, start=1):
        debit_sheet.write(row, 0, txn["transactionId"])
        debit_sheet.write(row, 1, txn["amount"]["amount"])
        debit_sheet.write(row, 2, txn["amount"]["currency"])
        debit_sheet.write(row, 3, txn["bookingDateTime"])
        debit_sheet.write(row, 4, txn["valueDateTime"])
        debit_sheet.write(row, 5, txn["balance"]["amount"]["amount"])
        debit_sheet.write(row, 6, txn["transactionInformation"])

    # Close workbook
    workbook.close()
    return file_path

@app.route("/download_transactions", methods=["GET"])
def download_transactions():
    # Read JSON file (replace with your actual data source)
    with open("transactions.json") as f:
        data = json.load(f)

    # Get query params
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if not from_date or not to_date:
        return {"error": "Please provide from_date and to_date in YYYY-MM-DD format"}, 400

    # Generate Excel file
    file_path = generate_excel(data, from_date, to_date)

    # Return file as response
    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
