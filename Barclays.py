from flask import Flask, request, jsonify
import json
import datetime

app = Flask(__name__)

# Load transaction data from JSON file
def load_transactions():
    with open("Hertitage.json", "r") as file:
        return json.load(file)

# Function to process transactions based on business rules
def process_transactions(from_date, to_date, account_number):
    transactions = load_transactions()
    from_date = datetime.datetime.strptime(from_date, "%Y-%m-%d")
    to_date = datetime.datetime.strptime(to_date, "%Y-%m-%d")
    
    total_credit = 0
    total_debit = 0
    
    for transaction in transactions:
        trans_date = datetime.datetime.strptime(transaction["valueDateTime"], "%Y-%m-%d")
        if from_date <= trans_date <= to_date and transaction["accountNumber"] == account_number:
            if transaction["creditDebitIndicator"] == "Credit" and "Claim" in transaction["transactionInformation"]:
                total_credit += float(transaction["amount"])
            elif transaction["creditDebitIndicator"] == "Debit" and transaction["transactionInformation"].startswith("BX"):
                total_debit += float(transaction["amount"])
    
    # If only receive transaction exists, set paid out to zero
    if total_credit > 0 and total_debit == 0:
        total_debit = 0
    elif total_debit > 0 and total_credit == 0:
        total_credit = 0
    
    return {
        "total_amount_paid_in": total_credit,
        "total_amount_paid_out": total_debit
    }

# API endpoint
@app.route("/transactions", methods=["GET"])
def get_transactions():
    from_date = request.args.get("fromDate")
    to_date = request.args.get("toDate")
    account_number = request.args.get("accountNumber")
    
    if not from_date or not to_date or not account_number:
        return jsonify({"error": "Missing required parameters"}), 400
    
    response = process_transactions(from_date, to_date, account_number)
    return jsonify(response)

if __name__ == "__main__":
    app.run(debug=True)















transactions_data = data.get("data", {}).get("attributes", {}).get("transactionHistoryDetails", [])

for account in transactions_data:
    for transaction in account.get("transactions", []):
        # Process each transaction
        value_date = transaction.get("valueDateTime")
        credit_debit = transaction.get("creditDebitIndicator")
        transaction_info = transaction.get("transactionInformation", "")
        amount = transaction.get("amount", {}).get("amount", 0)

        # Apply filtering conditions
        if from_date <= value_date <= to_date and account_number == account.get("accountId"):
            if credit_debit == "Credit" and "Claim" in transaction_info:
                total_amount_paid_in += amount
            elif credit_debit == "Debit" and transaction_info.startswith("BX"):
                total_amount_paid_out += amount

