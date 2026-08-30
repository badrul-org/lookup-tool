from asyncio import timeouts
import asyncio
import os
import json
import re
import csv
from playwright.async_api import async_playwright
from tools import dismiss_fieldedge_popup

# ── Highway address detection & cleaning ──────────────────────────────────────
_HIGHWAY_STRIP_PATTERN = re.compile(
    r'\b(state\s+route|state\s+rd|highway|route|hwy|sr)(?=\s*\d)',
    flags=re.IGNORECASE
)

def is_highway_address(address: str) -> bool:
    """Return True if the address contains a highway/route keyword."""
    return bool(_HIGHWAY_STRIP_PATTERN.search(address))

def strip_highway_keywords(address: str) -> str:
    """Remove highway designation words from an address and collapse extra spaces."""
    cleaned = _HIGHWAY_STRIP_PATTERN.sub('', address)
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

async def tax_rate_lookup_local(page, url, address_line_1: str, city: str, zip: str):
    """Local modified version of tax_rate_lookup to return (location_code, tax_rate)."""
    try:
        current_url = page.url
        print(f"Tax rate lookup - Current URL: {current_url}")
        await page.wait_for_load_state("networkidle")

        input_street_address = page.locator("//input[@id='txtAddr']")
        await input_street_address.wait_for(state="visible", timeout=10000)
        await input_street_address.fill(address_line_1)
        input_city = page.locator("//input[@id='txtCity']")
        await input_city.wait_for(state="visible", timeout=10000)
        await input_city.fill(city)
        input_zip = page.locator("//input[@id='txtZip']")
        await input_zip.wait_for(state="visible", timeout=10000)
        await input_zip.fill(zip)
        await page.locator("//input[@id='imgAdrSrc']").click()
        try:
            location_code_table_row = page.locator("//div[@id='tblSales']//label[@id='outLocationCode']")
            location_code = await location_code_table_row.text_content()
            location_code = location_code.replace("  ", "").strip()
            print(f"Location Code: {location_code}")

            tax_rate_str_table_row = page.locator("//div[@id='tblSales']//label[@id='outTotalTaxRate']")
            tax_rate_str = await tax_rate_str_table_row.text_content()
            tax_rate_str = tax_rate_str.replace("  ", "").strip()
            print(f"Tax Rate: {tax_rate_str}")
        except Exception as e:
            print(f"⚠️ Failed to get tax rate: {e}")
            location_code = None
            tax_rate_str = None
        
        # await table_rows.wait_for(state="visible", timeout=10000)
        # rows = await table_rows.all()
        # location_code = None
        # for row in rows:
        #     if "Location code" in await row.text_content():
        #         location_code = await row.text_content()
        #         location_code = location_code.replace("  ", "")
        #         location_code = location_code.split(")")[1]
        #         print(f"Location Code: {location_code}")

        # tax_rate_str = None
        # try:
        #     target_cell = page.get_by_role("cell", name="Total tax rate").locator("xpath=following-sibling::td")
        #     tax_rate = await target_cell.text_content(timeout=5000)
        #     if tax_rate:
        #         tax_rate_str = tax_rate.strip()
        #         print(f"Tax Rate: {tax_rate_str}")
        # except Exception as e:
        #     print(f"⚠️ Failed to get tax rate: {e}")

        return location_code, tax_rate_str

    except Exception as e:
        print(f"⚠️ Local tax lookup failed: {e}")
        return None, None

def extract_existing_rate(text: str) -> float:
    """Extract percentage (e.g. 10.1 from '10.1%') from existing code text."""
    if not text:
        return 0.0
    match = re.search(r'(\d+(?:\.\d+)?)\s*\.?\s*%', text)
    if match:
        return float(match.group(1))
    return 0.0

def parse_lookup_rate(rate_str: str) -> float:
    """Parse lookup rate string (e.g. 0.101 or .095) into a percentage float (10.1 or 9.5)."""
    if not rate_str:
        return 0.0
    cleaned = rate_str.strip()
    match = re.search(r'(\d+(?:\.\d+)?|\.\d+)', cleaned)
    if match:
        val = float(match.group(1))
        # Multiply by 100 if it's in decimal format (e.g., 0.101)
        if val < 1.0:
            val = val * 100.0
        return round(val, 4)
    return 0.0

async def get_invoice_amount(fe_page) -> str:
    """Retrieve the invoice due amount from the specified summary-value locator."""
    try:
        await asyncio.sleep(3)
        summary_val_loc = fe_page.locator("//div[@data-automation-id='WorkOrderTabsEnum-Invoice-container']//div[@class='summary-value']")
        await summary_val_loc.first.wait_for(state="attached", timeout=10000)
        
        count = await summary_val_loc.count()
        values = []
        for i in range(count):
            txt = await summary_val_loc.nth(i).text_content()
            if txt:
                values.append(txt.strip())
        
        print(f"Retrieved summary values: {values}")
        if values:
            return values[-1] # Return the last summary-value (usually Total or Balance Due)
        return ""
    except Exception as e:
        print(f"⚠️ Failed to retrieve invoice amount: {e}")
        return ""

async def main():
    input_csv = "tax_code_update_report.csv"
    output_csv = "tax_rate_difference_report.csv"
    
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} does not exist.")
        return

    # Load all input rows
    all_rows = []
    with open(input_csv, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_rows.append(row)
    
    print(f"Loaded {len(all_rows)} total rows from {input_csv}.")
    
    # Load previously processed rows to allow resumption
    processed_rows = {}
    if os.path.exists(output_csv):
        try:
            with open(output_csv, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    wo = row["workorder num"].strip()
                    processed_rows[wo] = row
            print(f"Loaded {len(processed_rows)} previously processed rows from {output_csv}.")
        except Exception as e:
            print(f"⚠️ Failed to parse existing {output_csv}: {e}")

    # Open target file for writing (both copying and writing updates)
    fieldnames = [
        "workorder num",
        "workorder url",
        "actual code",
        "exsisting code",
        "after update code",
        "update status",
        "tax rate difference",
        "due amount"
    ]
    
    # Let's perform Playwright startup only if we have pending items to process
    def is_row_pending(row):
        wo = row["workorder num"].strip()
        if wo in processed_rows:
            p_row = processed_rows[wo]
            if p_row.get("update status", "").strip() == "retry":
                return True
            exist_code = p_row.get("exsisting code") or ""
            after_code = p_row.get("after update code") or ""
            if "inactive" in exist_code.lower() or "inactive" in after_code.lower():
                return True
            return False
        return True

    has_items_to_process = any(is_row_pending(row) for row in all_rows)

    dispatch_mapping = {}

    if has_items_to_process:
        async with async_playwright() as p:
            browser, context, page = await init_scraper_session(p)
            try:
                # Capture dispatch mappings from Today's WO filter to speed up navigations
                print("Step 1: Navigating to Work Orders to capture dispatch links...")
                await page.locator("//a[@class='work-orders']").click()
                print("Waiting for work orders table to appear...")
                await page.wait_for_selector("tbody.fixed-body", state="visible", timeout=60000)
                await asyncio.sleep(2)

                print("Clicking Today's WO filter and intercepting list API response...")
                async with page.expect_response(
                    lambda r: "List/Get" in r.url and r.request.method == "POST",
                    timeout=60000
                ) as response_info:
                    # Click on Today's WO / Total Work Orders filter
                    await page.locator("//div[@data-automation-id='TOTAL-WORKORDERS-HOMESALE-&-PUMPING-filter-container']").click()

                list_response = await response_info.value
                try:
                    json_data = await list_response.json()
                    records = json_data.get("data") or json_data.get("Data") or json_data or []
                    for record in records:
                        if isinstance(record, dict):
                            wo_num = str(record.get("WorkOrder") or record.get("WorkOrderNumber") or record.get("Number") or record.get("WorkOrderNo") or "")
                            disp_id = record.get("DispatchID")
                            disp_task_id = record.get("DispatchTaskID")
                            if wo_num and disp_id is not None and disp_task_id is not None:
                                dispatch_mapping[wo_num] = (disp_id, disp_task_id)
                    print(f"✅ Successfully captured initial {len(dispatch_mapping)} Dispatch IDs from the list API!")
                except Exception as e:
                    print(f"⚠️ Failed to parse initial API response: {e}")

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
                        records = json_data.get("data") or json_data.get("Data") or json_data or []
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

                # Process each row
                final_results = []
                for idx, row in enumerate(all_rows):
                    wo_num = row["workorder num"].strip()
                    status = row["update status"].strip()
                    
                    # If already processed in a previous run, use it
                    if wo_num in processed_rows and not is_row_pending(row):
                        p_row = processed_rows[wo_num]
                        url_val = p_row.get("workorder url") or ""
                        if "WorkOrder/" in url_val:
                            url_val = ""
                        final_results.append({
                            "workorder num": wo_num,
                            "workorder url": url_val,
                            "actual code": p_row.get("actual code") or "",
                            "exsisting code": p_row.get("exsisting code") or "",
                            "after update code": p_row.get("after update code") or p_row.get("exsisting code") or "",
                            "update status": p_row.get("update status") or "",
                            "tax rate difference": p_row.get("tax rate difference") or "",
                            "due amount": p_row.get("due amount") or ""
                        })
                        continue
                    

                    
                    print(f"\n--- Processing WO {wo_num} ({idx+1}/{len(all_rows)}) ---")
                    
                    fe_page = await context.new_page()
                    actual_code = row["actual code"]
                    existing_code = row["exsisting code"]
                    update_status = status
                    tax_diff_str = ""
                    due_amount_str = ""
                    full_wo_url = ""

                    try:
                        # Navigate to the work order summary or search-and-click
                        if wo_num in dispatch_mapping:
                            try:
                                d_id, dt_id = dispatch_mapping[wo_num]
                                full_wo_url = f"https://login.fieldedge.com/#/DispatchSummary/{d_id}/{dt_id}"
                                await fe_page.goto(full_wo_url, wait_until="networkidle")
                                await fe_page.wait_for_timeout(4000)
                                await dismiss_fieldedge_popup(fe_page)
                            except Exception as e:
                                pass
                        else:
                            print(f"Fallback searching for WorkOrder: {wo_num} on List/0...")
                            await fe_page.goto("https://login.fieldedge.com/#/List/0", wait_until="networkidle")
                            await fe_page.wait_for_timeout(4000)
                            await dismiss_fieldedge_popup(fe_page)
                            
                            # Filter first
                            try:
                                await fe_page.locator("//div[@data-automation-id='TOTAL-WORKORDERS-HOMESALE-&-PUMPING-filter-container']").click()
                                await asyncio.sleep(2)
                            except Exception:
                                pass
                            
                            search_input = fe_page.locator("//input[@id='search']")
                            await search_input.wait_for(state="visible", timeout=15000)
                            await search_input.fill(wo_num)
                            await search_input.press("Enter")
                            await asyncio.sleep(3)
                            
                            # Row 2 is the first actual data row
                            first_row = fe_page.locator("(//tbody[@class='fixed-body']/tr)[2]")
                            await first_row.wait_for(state="visible", timeout=15000)
                            await first_row.click()
                            await fe_page.wait_for_timeout(4000)
                            await dismiss_fieldedge_popup(fe_page)

                        # Extract address1 and address2 from the page
                        address1_locator = fe_page.locator('//label[@data-automation-id="address1"]')
                        await address1_locator.wait_for(state="visible", timeout=15000)
                        address = await address1_locator.inner_text()
                        address = address.strip()

                        address2_locator = fe_page.locator('//label[@data-automation-id="address2"]')
                        await address2_locator.wait_for(state="visible", timeout=15000)
                        address2 = await address2_locator.inner_text()
                        address2 = address2.strip()
                        
                        print(f"Extracted Address: {address}, {address2}")

                        # Parse city, state, zip
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

                        # Clean address for DOR lookup
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
                            address_parts = cleaned.split(' ')
                            parsed_address = cleaned
                            if len(address_parts) >= 3:
                                if len(address_parts[1]) <= 2:
                                    parsed_address = f"{address_parts[0]} {address_parts[2]}"
                                else:
                                    parsed_address = f"{address_parts[0]} {address_parts[1]}"
                            elif len(address_parts) == 2:
                                parsed_address = f"{address_parts[0]} {address_parts[1]}"

                        # Run WA DOR tax lookup locally
                        print(f"WA DOR lookup for: Address: {parsed_address}, City: {city}, Zip: {zipcode}")
                        tax_page = await context.new_page()
                        location_code = None
                        lookup_rate_str = None
                        try:
                            tax_url = "https://webgis.dor.wa.gov/taxratelookup/SalesTax.aspx"
                            await tax_page.goto(tax_url, wait_until="networkidle")
                            location_code, lookup_rate_str = await tax_rate_lookup_local(tax_page, tax_url, parsed_address, city, zipcode)
                        except Exception as e:
                            print(f"⚠️ Failed to look up WA DOR rates: {e}")
                        finally:
                            await tax_page.close()

                        # Click Invoice Tab
                        invoice_tab = fe_page.locator("(//div[@data-automation-id='WorkOrderTabsEnum-Invoice-container']/div)[1]")
                        await invoice_tab.wait_for(state="visible", timeout=10000)
                        await invoice_tab.click()
                        await asyncio.sleep(2)

                        # Dynamic wait for tab contents to load: try waiting for either Tax Codes dropdown or Tax Group container to show up
                        tax_group_container = fe_page.locator("//div[@data-automation-id='new-section-invoice-TaxGroup-container']")
                        tax_codes_container = fe_page.locator('(//div[@name="Tax Codes"])[1]')
                        
                        # Set actual code in results
                        if location_code:
                            actual_code = location_code

                        # Try Flow
                        existing_code = ""
                        update_status = status
                        is_updated = False
                        
                        try:
                            # 1. Wait for Tax Codes dropdown to be visible
                            await tax_codes_container.wait_for(state="visible", timeout=5000)
                            
                            # Read existing code
                            existing_text_on_page = await tax_codes_container.inner_text()
                            existing_code = existing_text_on_page.strip() if existing_text_on_page else ""
                            print(f"Existing Tax Code text: '{existing_code}'")

                            existing_rate = extract_existing_rate(existing_code)
                            lookup_rate = parse_lookup_rate(lookup_rate_str)
                            tax_diff = lookup_rate - existing_rate
                            tax_diff_str = f"{tax_diff:+.2f}%" if tax_diff != 0 else "0.00%"
                            print(f"Existing rate: {existing_rate}%, Lookup rate: {lookup_rate}%. Tax Difference: {tax_diff_str}")

                            # If status is Check Manually, updated, Correct, or the code is inactive, try to update it
                            should_update = (status in ["Check Manually", "updated", "Correct"]) or ("inactive" in existing_code.lower())
                            if should_update and location_code:
                                if location_code in existing_code and "inactive" not in existing_code.lower():
                                    print(f"Tax code '{location_code}' already exists and is active. Skipping update.")
                                    update_status = "skipped" if status == "Check Manually" else status
                                else:
                                    print(f"Updating tax code to {location_code}...")
                                    tax_dropdown = fe_page.locator("(//div[@name='Tax Codes']/div/div)[1]")
                                    await tax_dropdown.wait_for(state="visible", timeout=5000)
                                    await tax_dropdown.click()
                                    await asyncio.sleep(1)

                                    tax_input = fe_page.locator("((//div[@name='Tax Codes']/div/div)[1]/input)[1]")
                                    await tax_input.fill(location_code)
                                    await asyncio.sleep(1)
                                    await tax_input.press("Enter")
                                    await asyncio.sleep(2)

                                    

                                    # Verify selection: first check dropdown, then fallback to tax group container
                                    updated_code = ""
                                    if await tax_codes_container.is_visible():
                                        updated_text = await tax_codes_container.inner_text()
                                        updated_code = updated_text.strip() if updated_text else ""
                                        print(f"Updated Tax Code from dropdown: '{updated_code}'")
                                    elif await tax_group_container.is_visible():
                                        updated_text = await tax_group_container.inner_text()
                                        updated_code = re.sub(r'Tax\s*Group', '', updated_text, flags=re.IGNORECASE).strip()
                                        print(f"Updated Tax Code from Tax Group container: '{updated_code}'")
                                    else:
                                        print("⚠️ Both verification locators not found after update!")
                                        update_status = "error"
                                        raise Exception("Verification locators not found after update")

                                    # Handle inactive code fallback by checking dropdown or tax group container
                                    if "inactive" in updated_code.lower():
                                        print(f"⚠️ Updated code '{updated_code}' is inactive. Re-selecting using ArrowDown...")
                                        await tax_dropdown.click()
                                        await asyncio.sleep(1)
                                        await tax_input.press("Meta+A")
                                        await tax_input.press("Backspace")
                                        await asyncio.sleep(0.5)
                                        await tax_input.fill(location_code)
                                        await asyncio.sleep(2) # wait 3 sec
                                        await tax_input.press("ArrowDown")
                                        await asyncio.sleep(1)
                                        await tax_input.press("Enter")
                                        await asyncio.sleep(2)

                                        # Read verified code again
                                        if await tax_codes_container.is_visible():
                                            updated_text = await tax_codes_container.inner_text()
                                            updated_code = updated_text.strip() if updated_text else ""
                                        elif await tax_group_container.is_visible():
                                            updated_text = await tax_group_container.inner_text()
                                            updated_code = re.sub(r'Tax\s*Group', '', updated_text, flags=re.IGNORECASE).strip()
                                        print(f"Re-selected verified code: '{updated_code}'")

                                    if location_code in updated_code:
                                        print("✅ Verification succeeded!")
                                        update_status = "new update"
                                        is_updated = True
                                    else:
                                        print("⚠️ Verification failed!")
                                        update_status = "retry"
                            else:
                                # For status 'updated', keep update_status as the status
                                update_status = status

                        except Exception as try_err:
                            print(f"Editable try flow failed/timed out: {try_err}. Checking fallback tax group container...")
                            if await tax_group_container.is_visible():
                                print("Tax Group container is visible (Not Editable).")
                                raw_text = await tax_group_container.inner_text()
                                cleaned_existing_code = re.sub(r'Tax\s*Group', '', raw_text, flags=re.IGNORECASE).strip()
                                existing_code = cleaned_existing_code
                                print(f"Cleaned Tax Group code: '{existing_code}'")
                                
                                existing_rate = extract_existing_rate(existing_code)
                                lookup_rate = parse_lookup_rate(lookup_rate_str)
                                tax_diff = lookup_rate - existing_rate
                                tax_diff_str = f"{tax_diff:+.2f}%" if tax_diff != 0 else "0.00%"
                                print(f"Existing rate: {existing_rate}%, Lookup rate: {lookup_rate}%. Tax Difference: {tax_diff_str}")
                                
                                update_status = "not edidtable"
                            else:
                                print("⚠️ Dropdown update failed and tax group container is not visible either.")
                                update_status = "error"

                        # Retrieve due amount
                        if update_status != "error":
                            if is_updated or update_status == "new update":
                                print("Waiting 5 seconds for page/tax recalculation after update...")
                                await asyncio.sleep(3)
                            print("Retrieving invoice amount...")
                            due_amount_str = await get_invoice_amount(fe_page)
                            print(f"Retrieved Amount: '{due_amount_str}'")

                    except Exception as e:
                        print(f"⚠️ Error processing WO {wo_num}: {e}")
                        update_status = "retry"
                    finally:
                        await fe_page.close()
                        
                        # Compile new row data and write immediately
                        new_row = {
                            "workorder num": wo_num,
                            "workorder url": full_wo_url,
                            "actual code": actual_code,
                            "exsisting code": existing_code,
                            "after update code": updated_code if update_status == "new update" else existing_code,
                            "update status": update_status,
                            "tax rate difference": tax_diff_str,
                            "due amount": due_amount_str
                        }
                        final_results.append(new_row)
                        
                        # Incrementally update/write output CSV file
                        try:
                            with open(output_csv, mode="w", newline="", encoding="utf-8") as f_out:
                                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                                writer.writeheader()
                                # Convert remaining unprocessed rows to match headers
                                remaining_rows = []
                                for r in all_rows[len(final_results):]:
                                    wo = r["workorder num"].strip()
                                    remaining_rows.append({
                                        "workorder num": wo,
                                        "workorder url": f"https://login.fieldedge.com/#/WorkOrder/{wo}",
                                        "actual code": r.get("actual code") or "",
                                        "exsisting code": r.get("exsisting code") or "",
                                        "after update code": r.get("exsisting code") or "",
                                        "update status": r.get("update status") or "",
                                        "tax rate difference": "",
                                        "due amount": ""
                                    })
                                writer.writerows(final_results + remaining_rows)
                        except Exception as w_err:
                            print(f"⚠️ Failed to write incremental update to CSV: {w_err}")

            finally:
                await browser.close()
                print("Browser session closed.")
    else:
        print("No pending updated or Check Manually work orders found to process.")
        # Simply duplicate the csv adding the empty columns if output doesn't exist
        if not os.path.exists(output_csv):
            final_results = []
            for row in all_rows:
                wo = row["workorder num"].strip()
                final_results.append({
                    "workorder num": wo,
                    "workorder url": f"https://login.fieldedge.com/#/WorkOrder/{wo}",
                    "actual code": row.get("actual code") or "",
                    "exsisting code": row.get("exsisting code") or "",
                    "after update code": row.get("exsisting code") or "",
                    "update status": row.get("update status") or "",
                    "tax rate difference": "",
                    "due amount": ""
                })
            with open(output_csv, mode="w", newline="", encoding="utf-8") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(final_results)
            print(f"Copied all rows to {output_csv} with blank columns and URLs.")

    print("\nProcess fully finished.")

if __name__ == "__main__":
    asyncio.run(main())
