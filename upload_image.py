import xlsxwriter
import requests
from io import BytesIO
from flask import Flask, request

app = Flask(__name__)

@app.route('/generate_report', methods=['POST'])
def create_risk_exposure_report():
    data = request.form
    file = request.files.get('image')
    
    filename = "Risk_Exposure_Report.xlsx"
    client_name = data.get("client_name", "XYZ")
    currency_code = data.get("currency_code", "GBP")
    from_date = data.get("from_date", "1/1/2025")
    to_date = data.get("to_date", "1/2/2025")
    total_value = data.get("total_value", "100%")
    amount_sent = data.get("amount_sent", "40%")
    amount_not_sent = data.get("amount_not_sent", "60%")
    
    # Create a new Excel file and add a worksheet
    workbook = xlsxwriter.Workbook(filename)
    worksheet = workbook.add_worksheet()

    # Define formats
    bold_format = workbook.add_format({'bold': True})
    border_format = workbook.add_format({'border': 1})
    bold_border_format = workbook.add_format({'bold': True, 'border': 1})

    # Merge header cell
    worksheet.merge_range("A1:B1", "Risk Exposure Breakdown", bold_format)

    # Define table structure with variables
    table_data = [
        ["Client name", client_name],
        ["Currency code", currency_code],
        ["From Date", "To Date"],
        [from_date, to_date],
        ["Total Value", total_value],
        ["Amount sent to Trust", amount_sent],
        ["Amount not sent to Trust", amount_not_sent],
    ]

    # Write data into the worksheet
    row, col = 1, 0
    for item in table_data:
        worksheet.write(row, col, item[0], bold_border_format)
        worksheet.write(row, col + 1, item[1], border_format)
        row += 1

    # Adjust column width
    worksheet.set_column(0, 1, 25)

    # Insert image if provided
    if file:
        image_data = BytesIO(file.read())
        worksheet.insert_image("D2", "uploaded_image.png", {'image_data': image_data, 'x_scale': 0.5, 'y_scale': 0.5})
    
    # Close workbook
    workbook.close()
    return {"message": f"Report '{filename}' created successfully!"}

if __name__ == '__main__':
    app.run(debug=True)
