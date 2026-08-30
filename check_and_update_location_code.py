import asyncio
import os
import json
import re
import csv
# pyrefly: ignore [missing-import]
from playwright.async_api import async_playwright
from tools import tax_rate_lookup, dismiss_fieldedge_popup

# ── Highway address detection & cleaning ──────────────────────────────────────
_HIGHWAY_STRIP_PATTERN = re.compile(
    r'\b(state\s+route|state\s+rd|highway|route|hwy|sr)(?=\s*\d)',
    flags=re.IGNORECASE
)

def is_highway_address(address: str) -> bool:
    """Return True if the address contains a highway/route keyword."""
    return bool(_HIGHWAY_STRIP_PATTERN.search(address))

def strip_highway_keywords(address: str) -> str:
    """
    Remove highway designation words from an address and collapse extra spaces.
    Examples:
      "8120 State Route 162 E"  ->  "8120 162 E"
      "8120 SR 162 E"           ->  "8120 162 E"
      "8120 HWY 410"            ->  "8120 410"
    """
    cleaned = _HIGHWAY_STRIP_PATTERN.sub('', address)
    # Collapse multiple spaces left by the removal
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

async def init_scraper_session(playwright):
    """Launch browser and log in. Returns (browser, context, page)."""
    # Read credentials from credentials.json if available
    email = "taylor@sterlingsepticandplumbing.com"
    password = "Advertising1!"
    if os.path.exists("credentials.json"):
        try:
            with open("credentials.json", "r") as f:
                creds = json.load(f)
                email = creds.get("email") or email
                password = creds.get("password") or password
                print("Loaded credentials from credentials.json")
        except Exception as e:
            print(f"⚠️ Failed to read credentials.json: {e}")

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        accept_downloads=True,
        viewport={"width": 1920, "height": 1080}
    )
    context.set_default_timeout(60000)
    page = await context.new_page()
    page.set_default_timeout(60000)

    print(f"Navigating to login page...")
    await page.goto("https://login.fieldedge.com/#/List/0")
    await asyncio.sleep(2)
    try:
        if await page.locator("input[name='UserName']").is_visible():
            print(f"Logging in with {email}...")
            await page.locator("input[name='UserName']").fill(email)
            await page.locator("input[name='Password']").fill(password)
            await page.locator("input[type='submit'][value='Sign in to your account']").click()
    except Exception as e:
        print(f"⚠️ Login form filling encountered an issue: {e}")
    
    try:
        await page.wait_for_url("**/Dashboard/**", timeout=15000)
    except Exception:
        print("URL didn't strictly match Dashboard, continuing anyway...")
    
    # Dismiss any popup that appears after initial login/load
    await dismiss_fieldedge_popup(page)
    return browser, context, page

async def process_work_orders():
    csv_file = "tax_code_update_report.csv"
    processed_wos = {}
    
    # Read existing CSV report if it exists to build a state map of completed tasks
    if os.path.exists(csv_file):
        try:
            with open(csv_file, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader, None)  # Skip header row
                if headers:
                    for row in reader:
                        if len(row) >= 4:
                            wo_num = row[0].strip()
                            status = row[3].strip()
                            processed_wos[wo_num] = status
            print(f"Loaded {len(processed_wos)} previous records from CSV.")
        except Exception as e:
            print(f"⚠️ Failed to read existing CSV report: {e}")
            
    # Initialize report CSV file with headers if it doesn't exist
    if not os.path.exists(csv_file):
        try:
            with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["workorder num", "actual code", "exsisting code", "update status"])
            print(f"Created new CSV report: {csv_file}")
        except Exception as e:
            print(f"⚠️ Failed to initialize CSV report: {e}")

    async with async_playwright() as p:
        browser, context, page = await init_scraper_session(p)
        try:
            # Step 1: Navigating to Work Orders
            print("Step 1: Navigating to Work Orders...")
            await page.locator("//a[@class='work-orders']").click()
            print("Waiting for work orders table to appear...")
            await page.wait_for_selector("tbody.fixed-body", state="visible", timeout=60000)
            await asyncio.sleep(2)

            # Step 2: Click Today's WO filter and intercept network response
            print("Clicking Today's WO filter and intercepting its final API response...")
            dispatch_mapping = {}
            async with page.expect_response(
                lambda response: "List/Get" in response.url and response.request.method == "POST",
                timeout=60000
            ) as response_info:
                await page.locator("//div[@data-automation-id='TOTAL-WORKORDERS-HOMESALE-&-PUMPING-filter-container']").click()

            list_response = await response_info.value
            try:
                json_data = await list_response.json()
                records = []
                if isinstance(json_data, dict):
                    if "data" in json_data:
                        records = json_data["data"]
                    elif "Data" in json_data:
                        records = json_data["Data"]
                elif isinstance(json_data, list):
                    records = json_data

                for record in records:
                    if isinstance(record, dict):
                        wo_num = str(record.get("WorkOrder") or record.get("WorkOrderNumber") or record.get("Number") or record.get("WorkOrderNo") or "")
                        disp_id = record.get("DispatchID")
                        disp_task_id = record.get("DispatchTaskID")
                        if wo_num and disp_id is not None and disp_task_id is not None:
                            dispatch_mapping[wo_num] = (disp_id, disp_task_id)
                print(f"✅ Successfully captured {len(dispatch_mapping)} Dispatch IDs from the final API call!")
            except Exception as e:
                print(f"⚠️ Failed to parse List/Get API response: {e}")

            print("Waiting 5 seconds for the table UI to finish rendering...")
            await asyncio.sleep(5)

            # Find all the work orders rows from table
            all_table_rows = await page.locator("//tbody[@class='fixed-body']/tr").all()
            row_count = len(all_table_rows) - 1

            # Get the actual row count
            try:
                actual_row_count_text = await page.locator("//div[@class='group-amount group-selected']").inner_text()
                actual_row_count_text = actual_row_count_text.replace("\xa0", " ").replace("\u00A0", " ").replace("(", "").replace(")", "").strip()
                actual_row_count = int(actual_row_count_text)
            except Exception as e:
                print(f"⚠️ Could not parse actual row count, defaulting to {row_count}. Error: {e}")
                actual_row_count = row_count

            # Scroll to load more data if needed
            scroll_attempts = 0
            max_scroll_attempts = 50
            no_increase_count = 0
            while row_count < actual_row_count and scroll_attempts < max_scroll_attempts:
                scroll_attempts += 1
                print(f"Scrolling to load more data... ({row_count}/{actual_row_count})")
                last_row = page.locator(f"(//tbody[@class='fixed-body']/tr)[{row_count + 1}]")

                try:
                    async with page.expect_response(
                        lambda response: "List/Get" in response.url and response.request.method == "POST",
                        timeout=5000  # Faster timeout to avoid long hangs when scrolling doesn't trigger request
                    ) as response_info:
                        await last_row.scroll_into_view_if_needed()
                        # Also trigger JavaScript scrolling inside any scrollable divs/tbodys
                        await page.evaluate('''() => {
                            window.scrollBy(0, 10000);
                            const elements = Array.from(document.querySelectorAll('div, tbody, section'));
                            for (const el of elements) {
                                if (el.scrollHeight > el.clientHeight) {
                                    el.scrollTop = el.scrollHeight;
                                }
                            }
                        }''')
                    
                    list_response = await response_info.value
                    json_data = await list_response.json()
                    records = []
                    if isinstance(json_data, dict):
                        if "data" in json_data:
                            records = json_data["data"]
                        elif "Data" in json_data:
                            records = json_data["Data"]
                    elif isinstance(json_data, list):
                        records = json_data

                    for record in records:
                        if isinstance(record, dict):
                            wo_num = str(record.get("WorkOrder") or record.get("WorkOrderNumber") or record.get("Number") or record.get("WorkOrderNo") or "")
                            disp_id = record.get("DispatchID")
                            disp_task_id = record.get("DispatchTaskID")
                            if wo_num and disp_id is not None and disp_task_id is not None:
                                if wo_num not in dispatch_mapping:
                                    dispatch_mapping[wo_num] = (disp_id, disp_task_id)
                except Exception as e:
                    print(f"⚠️ Scroll wait or parse failed: {e}")
                    # Run fallback scrolling directly
                    await last_row.scroll_into_view_if_needed()
                    await page.evaluate('''() => {
                        window.scrollBy(0, 10000);
                        const elements = Array.from(document.querySelectorAll('div, tbody, section'));
                        for (const el of elements) {
                            if (el.scrollHeight > el.clientHeight) {
                                el.scrollTop = el.scrollHeight;
                            }
                        }
                    }''')
                    await asyncio.sleep(2)

                await asyncio.sleep(2)
                all_table_rows = await page.locator("//tbody[@class='fixed-body']/tr").all()
                new_row_count = len(all_table_rows) - 1
                
                if new_row_count <= row_count:
                    no_increase_count += 1
                    print(f"Row count did not increase after scrolling ({no_increase_count}/3).")
                    if no_increase_count >= 3:
                        print("Stopping scroll.")
                        break
                else:
                    no_increase_count = 0
                row_count = new_row_count

            print(f"Total work orders captured in mapping: {len(dispatch_mapping)}")

            # Process each work order from the captured API response dispatch mapping
            for wo_number in list(dispatch_mapping.keys()):
                print(f"\n--- Processing WO {wo_number} ---")
                
                # Check if this work order was already successfully processed
                # We skip if status is "updated" or "skipped"
                previous_status = processed_wos.get(wo_number)
                if previous_status in ["updated", "skipped"]:
                    print(f"WO {wo_number} already processed with status '{previous_status}'. Skipping.")
                    continue

                # Open work order in a new page/tab
                fe_page = await context.new_page()
                actual_code = ""
                existing_code = ""
                update_status = "pending"
                try:
                    if str(wo_number) in dispatch_mapping:
                        d_id, dt_id = dispatch_mapping[str(wo_number)]
                        full_wo_url = f"https://login.fieldedge.com/#/DispatchSummary/{d_id}/{dt_id}"
                    else:
                        full_wo_url = f"https://login.fieldedge.com/#/WorkOrder/{wo_number}"
                        print(f"Fallback linking to direct WorkOrder URL: {full_wo_url}")

                    try:
                        await fe_page.goto(full_wo_url, wait_until="networkidle")
                    except Exception as e:
                        print(f"⚠️ fe_page navigation failed: {e}")

                    await fe_page.wait_for_timeout(4000)
                    await dismiss_fieldedge_popup(fe_page)

                    # Extract address1 and address2 from the work order page directly
                    address1_locator = fe_page.locator('//label[@data-automation-id="address1"]')
                    await address1_locator.wait_for(state="visible", timeout=15000)
                    address = await address1_locator.inner_text()
                    address = address.strip()

                    address2_locator = fe_page.locator('//label[@data-automation-id="address2"]')
                    await address2_locator.wait_for(state="visible", timeout=15000)
                    address2 = await address2_locator.inner_text()
                    address2 = address2.strip()
                    
                    print(f"Extracted Address1: '{address}'")
                    print(f"Extracted Address2: '{address2}'")

                    # Parse city, state, zip from Address2 (e.g. Puyallup Wa 98374 or Des Moines WA 98148)
                    addr2_parts = [p.strip() for p in address2.split(" ") if p.strip()]
                    if len(addr2_parts) >= 3:
                        zipcode = addr2_parts[-1]
                        state = addr2_parts[-2]
                        city = " ".join(addr2_parts[:-2])
                    elif len(addr2_parts) == 2:
                        zipcode = addr2_parts[-1]
                        city = addr2_parts[0]
                        state = ""
                    else:
                        zipcode = address2
                        city = ""
                        state = ""

                    print(f"Parsed City: '{city}', State: '{state}', Zipcode: '{zipcode}'")

                    # Clean address
                    address_parts = address.split(' ')
                    parsed_address = address
                    if len(address_parts) >= 3:
                        if len(address_parts[1]) <= 2:
                            parsed_address = f"{address_parts[0]} {address_parts[2]}"
                        else:
                            parsed_address = f"{address_parts[0]} {address_parts[1]}"
                    elif len(address_parts) == 2:
                        parsed_address = f"{address_parts[0]} {address_parts[1]}"

                    if is_highway_address(address):
                        cleaned = strip_highway_keywords(address)
                        print(f"Cleaned highway address: '{address}' -> '{cleaned}'")
                        address = cleaned
                        address_parts = address.split(' ')
                        parsed_address = address
                        if len(address_parts) >= 3:
                            if len(address_parts[1]) <= 2:
                                parsed_address = f"{address_parts[0]} {address_parts[2]}"
                            else:
                                parsed_address = f"{address_parts[0]} {address_parts[1]}"
                        elif len(address_parts) == 2:
                            parsed_address = f"{address_parts[0]} {address_parts[1]}"

                    # Run WA state tax rate lookup
                    print(f"Fetching location code for address: {parsed_address}, City: {city}, Zip: {zipcode}")
                    tax_page = await context.new_page()
                    location_code = None
                    try:
                        tax_url = "https://webgis.dor.wa.gov/taxratelookup/SalesTax.aspx"
                        await tax_page.goto(tax_url, wait_until="networkidle")
                        location_code = await tax_rate_lookup(tax_page, tax_url, parsed_address, city, zipcode)
                        print(f"Fetched Location Code: {location_code}")
                    except Exception as e:
                        print(f"⚠️ Failed to fetch location code from WA DOR: {e}")
                    finally:
                        await tax_page.close()

                    # Click the Invoice tab
                    invoice_tab = fe_page.locator("(//div[@data-automation-id='WorkOrderTabsEnum-Invoice-container']/div)[1]")
                    await invoice_tab.wait_for(state="visible", timeout=10000)
                    await invoice_tab.click()
                    await asyncio.sleep(2)

                    # Get existing tax code text
                    tax_codes_container = fe_page.locator('(//div[@name="Tax Codes"])[1]')
                    await tax_codes_container.wait_for(state="visible", timeout=10000)
                    existing_text = await tax_codes_container.inner_text()
                    existing_code = existing_text.strip() if existing_text else ""
                    print(f"Existing Tax Code text: '{existing_code}'")

                    if location_code:
                        actual_code = location_code
                        # Check if the location code is already anywhere in the existing text
                        if location_code in existing_code:
                            print(f"Location code '{location_code}' already exists in '{existing_code}'. Skipping update.")
                            update_status = "skipped"
                        else:
                            # Click tax code dropdown/container to edit
                            tax_dropdown = fe_page.locator("(//div[@name='Tax Codes']/div/div)[1]")
                            await tax_dropdown.wait_for(state="visible", timeout=10000)
                            await tax_dropdown.click()
                            await asyncio.sleep(1)

                            # Fill location code and press Enter
                            tax_input = fe_page.locator("((//div[@name='Tax Codes']/div/div)[1]/input)[1]")
                            await tax_input.fill(location_code)
                            await asyncio.sleep(1)
                            await tax_input.press("Enter")
                            await asyncio.sleep(2)

                            # Verify the update
                            await asyncio.sleep(2)
                            updated_text = await tax_codes_container.inner_text()
                            updated_code = updated_text.strip() if updated_text else ""
                            print(f"Updated Tax Code text: '{updated_code}'")

                            if location_code in updated_code:
                                print(f"✅ Tax code {location_code} updated and verified successfully for WO {wo_number}")
                                update_status = "updated"
                            else:
                                print(f"⚠️ Verification failed! Updated code {location_code} not found in '{updated_code}'")
                                update_status = "retry"
                    else:
                        print(f"⚠️ Location code could not be resolved from WA DOR.")
                        update_status = "retry"

                except Exception as e:
                    print(f"⚠️ Failed to process WO {wo_number}: {e}")
                    update_status = "retry"
                finally:
                    await fe_page.close()
                    # Append row to report CSV
                    try:
                        with open(csv_file, mode="a", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            writer.writerow([wo_number, actual_code, existing_code, update_status])
                    except Exception as csv_err:
                        print(f"⚠️ Failed to write row to CSV report: {csv_err}")

        finally:
            await browser.close()
            print("\nBrowser closed. Process completed.")

if __name__ == "__main__":
    asyncio.run(process_work_orders())
