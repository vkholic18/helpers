"""
Script to create inventory_data.xlsx file with sample data
Run this script to generate the Excel file needed for reconciliation
"""
import openpyxl
from openpyxl import Workbook

# Create a new workbook
wb = Workbook()
ws = wb.active

# Add headers
headers = [
    "data_center",
    "ip_address", 
    "environment",
    "platform",
    "host_type",
    "workload_domain",
    "vcd_org",
    "fqdn",
    "category"
]

ws.append(headers)

# Add sample data rows (you can add more rows here)
sample_data = [
    ["tok05", "172.31.255.3", "Test", "Linux", "VCFaaS", "w381", "w381", "host01.example.com", "Reserved"],
    # Add more rows as needed:
    # ["dal10", "10.10.10.100", "Production", "Windows", "VCFaaS", "w382", "w382", "host02.example.com", "Reserved"],
]

for row in sample_data:
    ws.append(row)

# Save the file
filename = "inventory_data.xlsx"
wb.save(filename)
print(f"✓ Successfully created {filename}")
print(f"  Location: {filename}")
print(f"  Rows added: {len(sample_data)}")
print("\nYou can now edit this file to add your actual host data!")
