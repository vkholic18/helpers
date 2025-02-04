import xlsxwriter

def create_risk_exposure_report(
    filename="Risk_Exposure_Report.xlsx",
    client_name="XYZ",
    currency_code="GBP",
    from_date="1/1/2025",
    to_date="1/2/2025",
    total_value="100%",
    amount_sent="40%",
    amount_not_sent="60%"
):
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
    data = [
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
    for item in data:
        worksheet.write(row, col, item[0], bold_border_format)
        worksheet.write(row, col + 1, item[1], border_format)
        row += 1

    # Adjust column width
    worksheet.set_column(0, 1, 25)

    # Close workbook
    workbook.close()
    print(f"Report '{filename}' created successfully!")

# Example Usage
create_risk_exposure_report(
    client_name="ABC Corp",
    currency_code="USD",
    from_date="01/05/2025",
    to_date="02/06/2025",
    total_value="500,000 USD",
    amount_sent="200,000 USD (40%)",
    amount_not_sent="300,000 USD (60%)"
)
