import asyncio
import sqlite3
import os
import requests
import tempfile
import uuid
import csv
from datetime import datetime
from playwright.async_api import async_playwright
from tools import get_pdf_all_reports, address_search, Tacoma_report_lookup, King_report_lookup, upload_attachments_to_work_order, tax_rate_lookup

king_pierce_cities = set()
try:
    with open('king_pierce_cities_plus_unincorporated.csv', 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0].strip():
                king_pierce_cities.add(row[0].strip().lower())
except Exception as e:
    print(f"⚠️ Failed to load king pierce cities CSV: {e}")



def init_work_orders_db():
    conn = sqlite3.connect('lookup_sessions.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS work_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wo_number TEXT UNIQUE NOT NULL,
            address TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE work_orders RENAME COLUMN onlinerme_status TO attachment_status")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE work_orders ADD COLUMN error_message TEXT")
    except Exception:
        pass
    for col, default in [
        ("rme_status", "not found"),
        ("tpchd_status", "not found"),
        ("invoice_status", "not found"),
        ("king_status", "not found"),
        ("run_time", "NULL"),
        ("location_code", "not found"),
        ("tax_code_status", "not found"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE work_orders ADD COLUMN {col} TEXT DEFAULT '{default}'")
        except Exception:
            pass
    conn.commit()
    return conn



async def return_customer_invoice(page):
    await asyncio.sleep(5)
    await page.locator("(//div[@data-automation-id='CustomerTabsEnum-Invoice-container']/div)[1]").click()

    # check minimum 1 invoice is available
    try:
        await page.locator("(//tbody/tr)[1]").wait_for(state="visible", timeout=15000)
        date_of_invoice = await page.locator("((//tbody/tr)[1]/td)[7]").inner_text()
        # click on this share button and intercept the resulting API response
        async with page.expect_response(lambda response: "LayoutTemplates/CreateDispatchPdf" in response.url and response.request.method == "POST", timeout=30000) as response_info:
            await page.locator("(//tbody/tr)[1]/td/button[@class='actions-icon-button']").click()
            await asyncio.sleep(5)
        response = await response_info.value
        json_data = await response.json()
        print(json_data.get("ExportAddress"))
        return json_data.get("ExportAddress"), date_of_invoice
    except Exception as e:
        print(f"⚠️ Failed to extract invoice PDF: {e}")
        return None, None

async def init_scraper_session(playwright):
    """Launch browser and log in. Returns (browser, context, page)."""
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    context.set_default_timeout(60000)
    page = await context.new_page()
    page.set_default_timeout(60000)

    print("Navigating to login page...")
    await page.goto("https://login.fieldedge.com/#/List/0")
    await asyncio.sleep(2)
    try:
        if await page.locator("input[name='UserName']").is_visible():
            print("Logging in with taylor@sterlingsepticandplumbing.com...")
            await page.locator("input[name='UserName']").fill("taylor@sterlingsepticandplumbing.com")
            await page.locator("input[name='Password']").fill("Advertising1!")
            await page.locator("input[type='submit'][value='Sign in to your account']").click()
    except Exception:
        pass
    try:
        await page.wait_for_url("**/Dashboard/**", timeout=15000)
    except Exception:
        print("URL didn't strictly match Dashboard, continuing anyway...")
    return browser, context, page


async def _ensure_logged_in(page):
    """Check if the session is still active; re-login if not."""
    try:
        # Navigate to the app root — if session expired we'll land on the login page
        try:
            await page.goto("https://login.fieldedge.com/#/List/0", wait_until="networkidle", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(2)

        if await page.locator("input[name='UserName']").is_visible(timeout=5000):
            print("🔐 Session expired — re-logging in...")
            await page.locator("input[name='UserName']").fill("taylor@sterlingsepticandplumbing.com")
            await page.locator("input[name='Password']").fill("Advertising1!")
            await page.locator("input[type='submit'][value='Sign in to your account']").click()
            try:
                await page.wait_for_url("**/Dashboard/**", timeout=20000)
            except Exception:
                pass
            print("✅ Re-login successful.")
        else:
            print("✅ Session still active.")
    except Exception as e:
        print(f"⚠️ Login check failed: {e}")


async def run_scraper_pass(browser, context, page):
    """Run one scraper pass on an existing browser session."""
    run_time = datetime.utcnow().isoformat() + 'Z'

    # Always verify the session is alive before starting work
    await _ensure_logged_in(page)

    # reload page
    await page.reload()
    await asyncio.sleep(5)

    # Step 1: Click on workorder tab
    print("Step 1: Navigating to Work Orders...")
    await page.locator("//a[@class='work-orders']").click()
    print("Waiting for work orders table to appear...")
    await page.wait_for_selector("tbody.fixed-body", state="visible", timeout=60000)
    await asyncio.sleep(2)

    # Click on Customized view and intercept the exact API call it generates
    print("Clicking Customized View and intercepting its final API response...")
    dispatch_mapping = {}
    async with page.expect_response(lambda response: "List/Get" in response.url and response.request.method == "POST", timeout=60000) as response_info:
        await page.locator("//div[@data-automation-id='Todays-WO-filter-container']").click()

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

    # Initialize connection and ensure table exists
    db_conn = init_work_orders_db()
    db_cursor = db_conn.cursor()

    # find all the work orders id from table
    all_table_row = await page.locator("//tbody[@class='fixed-body']/tr").all()
    row_count = len(all_table_row) - 1

    # get the actual row count
    try:
        actual_row_count = await page.locator("//div[@class='group-amount group-selected']").inner_text()
        actual_row_count = actual_row_count.replace("\xa0", " ").replace("\u00A0", " ").replace("(", "").replace(")", "").strip()
        actual_row_count = int(actual_row_count)
    except Exception as e:
        print(f"⚠️ Could not parse actual row count, defaulting to {row_count}. Error: {e}")
        actual_row_count = row_count

    scroll_attempts = 0
    max_scroll_attempts = 50
    while row_count < actual_row_count and scroll_attempts < max_scroll_attempts:
        scroll_attempts += 1
        print(f"Scrolling to load more data... ({row_count}/{actual_row_count})")
        # Scroll the last row presently visible into view
        last_row = page.locator(f"(//tbody[@class='fixed-body']/tr)[{row_count + 1}]")

        try:
            # We wait for the API call that brings new data
            async with page.expect_response(lambda response: "List/Get" in response.url and response.request.method == "POST", timeout=20000) as response_info:
                await last_row.scroll_into_view_if_needed()
            
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

            new_captured = 0
            for record in records:
                if isinstance(record, dict):
                    wo_num = str(record.get("WorkOrder") or record.get("WorkOrderNumber") or record.get("Number") or record.get("WorkOrderNo") or "")
                    disp_id = record.get("DispatchID")
                    disp_task_id = record.get("DispatchTaskID")
                    if wo_num and disp_id is not None and disp_task_id is not None:
                        if wo_num not in dispatch_mapping:
                            dispatch_mapping[wo_num] = (disp_id, disp_task_id)
                            new_captured += 1
            print(f"✅ Captured {new_captured} new Dispatch IDs from scroll.")
            
        except Exception as e:
            print(f"⚠️ Scroll wait or parse failed (may just be no more data): {e}")
            # Try to just scroll and wait safely without strictly expecting response
            await last_row.scroll_into_view_if_needed()
            await asyncio.sleep(3)

        await asyncio.sleep(2)
        all_table_row = await page.locator("//tbody[@class='fixed-body']/tr").all()
        new_row_count = len(all_table_row) - 1
        
        if new_row_count <= row_count:
            print("Row count did not increase after scrolling. Stopping scroll.")
            break
        row_count = new_row_count

    print(f"Total rows to process after scrolling: {row_count}")

    restart_needed = False

    for i in range(row_count):
        if restart_needed:
            break

        wo_number = await page.locator(f"(//tbody[@class='fixed-body']/tr)[{i+2}]/td[2]").inner_text()
        address = await page.locator(f"(//tbody[@class='fixed-body']/tr)[{i+2}]/td[5]").inner_text()
        address = address.replace('\xa0', ' ').replace('\u00A0', ' ').strip()
        city = await page.locator(f"(//tbody[@class='fixed-body']/tr)[{i+2}]/td[6]").inner_text()
        city = city.replace('\xa0', ' ').replace('\u00A0', ' ').strip()

        # Extract clean search address (Street Number + Name only), ignoring directional words
        address_parts = address.split(' ')
        parsed_address = address
        if len(address_parts) >= 3:
            if len(address_parts[1]) <= 2:
                parsed_address = f"{address_parts[0]} {address_parts[2]}"
            else:
                parsed_address = f"{address_parts[0]} {address_parts[1]}"
        elif len(address_parts) == 2:
            parsed_address = f"{address_parts[0]} {address_parts[1]}"

        db_cursor.execute('SELECT id FROM work_orders WHERE wo_number = ?', (wo_number,))
        if db_cursor.fetchone():
            print(f"WO {wo_number} already in DB. Passing...")
        else:
            # get pdf from onlinerme using a separate tab to preserve FieldEdge!
            print(f"Pulling OnlineRME reports for address: {address}")
            rme_page = await context.new_page()
            rme_result = None
            # check the city if it is Prience or king
            if city.lower() in king_pierce_cities:
                county = "King"
            else:
                county = "Pierce"

            try:
                rme_url = "https://www.onlinerme.com/contractorsearchproperty.aspx"
                try:
                    await rme_page.goto(rme_url, wait_until="networkidle")
                except:
                    pass
                await address_search(page=rme_page, url=rme_url, address_line_1=parsed_address, county=county)
                rme_result = await get_pdf_all_reports(page=rme_page, url=rme_url, input_address=address)
                print(f"✅ Finished getting PDFs from OnlineRME for WO {wo_number}")
            except Exception as e:
                print(f"⚠️ Error fetching OnlineRME for {wo_number}: {e}")
            finally:
                await rme_page.close()

            print(f"Pulling TPCHD reports for address: {address}")
            tpchd_page = await context.new_page()
            tpchd_result = []
            try:
                tpchd_url = "https://edocs.tpchd.org/"
                try:
                    await tpchd_page.goto(tpchd_url, wait_until="networkidle")
                except:
                    pass
                tpchd_result = await Tacoma_report_lookup(page=tpchd_page, url=tpchd_url, address_line_1=parsed_address)
                print(f"✅ Finished getting PDFs from TPCHD for WO {wo_number} using parsed address: '{parsed_address}'")
            except Exception as e:
                print(f"⚠️ Error fetching TPCHD for {wo_number}: {e}")
            finally:
                await tpchd_page.close()

            # --- KING COUNTY REPORTS CHECK ---
            king_result = []
            if city.lower() in king_pierce_cities:
                print(f"City '{city}' matched active list. Pulling King County reports for address: {address}")
                king_page = await context.new_page()
                try:
                    king_url = "https://kingcounty.maps.arcgis.com/apps/instant/sidebar/index.html?appid=6c0bbaa4339c4ffab0c53cfe1f8d3d85"
                    try:
                        await king_page.goto(king_url, wait_until="networkidle")
                    except:
                        pass
                    k_reports, k_error = await King_report_lookup(page=king_page, url=king_url, address_line_1=address)
                    if k_reports:
                        king_result = k_reports
                        print(f"✅ Finished getting {len(k_reports)} PDFs from King County for WO {wo_number}")
                    else:
                        print(f"⚠️ King County returned no reports or error: {k_error}")
                except Exception as e:
                    print(f"⚠️ Error fetching King County for {wo_number}: {e}")
                finally:
                    await king_page.close()

            final_rme_urls = rme_result.get("pdf_urls", []) if rme_result and isinstance(rme_result, dict) else []
            report_dict = {
                "tpchd_reports": tpchd_result,
                "king_reports": king_result,
                "rme_reports": final_rme_urls
            }
            print(f"\n--- REPORT DICTIONARY FOR WO {wo_number} ---")
            print(report_dict)
            print("------------------------------------------\n")

            # --- DOWNLOAD AND ATTACH PROCESS ---
            file_paths = []
            error_details = None
            rme_status = "not found"
            tpchd_status = "not found"
            king_status = "not found"
            invoice_status = "not found"
            location_code_val = "not found"
            tax_code_status = "not found"
            tmpdir = tempfile.mkdtemp(prefix=f"wo_attach_{wo_number}_")
            try:
                session_http = requests.Session()
                session_http.headers.update({
                    'User-Agent': 'Mozilla/5.0',
                    'Accept': 'application/pdf,application/octet-stream,*/*;q=0.8'
                })

                # 1. Download RME Reports
                if final_rme_urls:
                    rme_status = "pending upload"
                for item in final_rme_urls:
                    try:
                        parts = item.split(',')
                        pdf_url = parts[0]
                        rme_type = parts[1].strip() if len(parts) > 1 else 'unknown'
                        rme_date = parts[2].strip().replace('/', '-') if len(parts) > 2 else datetime.now().strftime('%Y-%m-%d')
                        r = session_http.get(pdf_url, stream=True, timeout=15)
                        if r.status_code == 200:
                            if "TIME OF SALE" in rme_type.upper() or rme_type.upper() == "TOS":
                                base_name = "TOS"
                            else:
                                base_name = f"RME ({rme_type}) - {rme_date}"
                                
                            filepath = os.path.join(tmpdir, f"{base_name}.pdf")
                            counter = 1
                            while os.path.exists(filepath):
                                filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")
                                counter += 1
                                
                            with open(filepath, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            file_paths.append(filepath)
                        else:
                            rme_status = "error"
                    except Exception as e:
                        print(f"Failed to download RME PDF {item}: {e}")
                        rme_status = "error"

                # 2. Download TPCHD Reports (ONLY AsBuilt)
                if any(len(i.split(',')) > 1 and i.split(',')[1].strip().lower() == 'asbuilt' for i in tpchd_result):
                    tpchd_status = "pending upload"
                for item in tpchd_result:
                    try:
                        parts = item.split(',')
                        pdf_url = parts[0]
                        record_type = parts[1].strip() if len(parts) > 1 else ""
                        if record_type.lower() == 'asbuilt':
                            r = session_http.get(pdf_url, stream=True, timeout=15)
                            if r.status_code == 200:
                                base_name = "AS-BUILT"
                                filepath = os.path.join(tmpdir, f"{base_name}.pdf")
                                counter = 1
                                while os.path.exists(filepath):
                                    filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")
                                    counter += 1

                                with open(filepath, 'wb') as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                file_paths.append(filepath)
                            else:
                                tpchd_status = "error"
                    except Exception as e:
                        print(f"Failed to download TPCHD PDF {item}: {e}")
                        tpchd_status = "error"

                # 3. Download King County Reports
                if king_result:
                    king_status = "pending upload"
                for item in king_result:
                    try:
                        r = session_http.get(item, stream=True, timeout=15)
                        if r.status_code == 200:
                            base_name = "AS-BUILT"
                            filepath = os.path.join(tmpdir, f"{base_name}.pdf")
                            counter = 1
                            while os.path.exists(filepath):
                                filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")
                                counter += 1

                            with open(filepath, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            file_paths.append(filepath)
                        else:
                            king_status = "error"
                    except Exception as e:
                        print(f"Failed to download King County PDF {item}: {e}")
                        king_status = "error"

                # 4. Fetch Customer Invoice and 5. Attach ALL Collected PDFs
                print(f"Checking for Customer Invoice for WO {wo_number}...")
                fe_page = await context.new_page()
                try:
                    if str(wo_number) in dispatch_mapping:
                        d_id, dt_id = dispatch_mapping[str(wo_number)]
                        full_wo_url = f"https://login.fieldedge.com/#/DispatchSummary/{d_id}/{dt_id}"
                    else:
                        full_wo_url = f"https://login.fieldedge.com/#/WorkOrder/{wo_number}"
                        print(f"Fallback direct linking to WorkOrder: {full_wo_url}")
                    try:
                        await fe_page.goto(full_wo_url, wait_until="networkidle")
                    except:
                        pass
                    await fe_page.wait_for_timeout(4000)

                    try:

                        cust_link_loc = fe_page.locator('//a[contains(@class, "customer-label")]')
                        await cust_link_loc.wait_for(state="visible", timeout=10000)
                        href = await cust_link_loc.get_attribute("href")
                        address2 = await fe_page.locator("//label[@data-automation-id='address2']").inner_text()
                        # find zipcode from address2 (e,g Des Moines WA 98148)
                        zipcode = address2.split(" ")[-1]
                        print(f"Fetching location code for WO {wo_number}...")
                        tax_page = await context.new_page()
                        location_code = None
                        try:
                            tax_url = "https://webgis.dor.wa.gov/taxratelookup/SalesTax.aspx"
                            await tax_page.goto(tax_url, wait_until="networkidle")
                            location_code = await tax_rate_lookup(tax_page, tax_url, parsed_address, city, zipcode)
                            print(f"Fetched Location Code: {location_code} for WO {wo_number}")
                                
                        except Exception as e:
                            print(f"Failed to fetch location code for WO {wo_number}: {e}")
                        finally:
                            await tax_page.close()
                        
                            # check if location code is available
                        if location_code:
                            location_code_val = location_code
                            try:
                                await fe_page.locator("(//div[@data-automation-id='WorkOrderTabsEnum-Invoice-container']/div)[1]").click()
                                await asyncio.sleep(2)
                                await fe_page.locator("(//div[@name='Tax Codes']/div/div)[1]").click()
                                await asyncio.sleep(1)
                                await fe_page.locator("((//div[@name='Tax Codes']/div/div)[1]/input)[1]").fill(location_code)
                                await asyncio.sleep(1)
                                await fe_page.locator("((//div[@name='Tax Codes']/div/div)[1]/input)[1]").press("Enter")
                                await asyncio.sleep(2)

                                print("Tax code updated successfully")
                                tax_code_status = "done"
                            except Exception as e:
                                print(f"Failed to update tax code for WO {wo_number}: {e}")
                                tax_code_status = "error"
                                error_details = f"Tax code update failed: {e}"

                        if href:
                            cust_url = f"https://login.fieldedge.com/{href}"
                            print(f"Navigating to Customer Page: {cust_url}")
                            try:
                                await fe_page.goto(cust_url, wait_until="networkidle")
                            except:
                                pass
                            await fe_page.wait_for_timeout(3000)

                            invoice_pdf_url, date_of_invoice = await return_customer_invoice(fe_page)
                            if invoice_pdf_url:
                                print(f"Found Invoice PDF URL: {invoice_pdf_url}")
                                invoice_status = "pending upload"
                                print("Waiting 4 seconds for Invoice PDF to be fully generated on Azure...")
                                await asyncio.sleep(4)  # non-blocking — was time.sleep(4)
                                r = session_http.get(invoice_pdf_url, stream=True, timeout=15)
                                if r.status_code == 200:
                                    invoice_date = date_of_invoice.strip().replace('/', '-') if date_of_invoice else datetime.now().strftime('%Y-%m-%d')
                                    base_name = f"INVOICE {invoice_date}"
                                    filepath = os.path.join(tmpdir, f"{base_name}.pdf")
                                    counter = 1
                                    while os.path.exists(filepath):
                                        filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")
                                        counter += 1

                                    with open(filepath, 'wb') as f:
                                        for chunk in r.iter_content(chunk_size=8192):
                                            f.write(chunk)
                                    file_size = os.path.getsize(filepath)
                                    print(f"Downloaded Invoice PDF size: {file_size} bytes")
                                    if file_size > 1000:
                                        file_paths.append(filepath)
                                        print("✅ Successfully downloaded Customer Invoice.")
                                    else:
                                        print("⚠️ Invoice PDF is unusually small. Skipping.")
                                        invoice_status = "error"
                                        error_details = "Invoice blob storage returned an empty/invalid file."
                                else:
                                    invoice_status = "error"
                    except Exception as e:
                        print(f"⚠️ Failed to extract or download customer invoice: {e}")
                        invoice_status = "error"
                        error_details = f"Invoice extraction error: {str(e)}"

                    # 5. Attach ALL Collected PDFs to FieldEdge Work Order
                    if file_paths:
                        print(f"Uploading {len(file_paths)} PDF(s) to Work Order {wo_number}...")
                        try:
                            await fe_page.goto(full_wo_url, wait_until="networkidle")
                        except:
                            pass
                        await fe_page.wait_for_timeout(4000)
                        await upload_attachments_to_work_order(
                            page=fe_page,
                            url="",
                            address_line_1="",
                            file_paths=file_paths,
                            work_order_number=str(wo_number)
                        )
                        await page.wait_for_timeout(20000)
                        if rme_status == "pending upload": rme_status = "done"
                        if tpchd_status == "pending upload": tpchd_status = "done"
                        if king_status == "pending upload": king_status = "done"
                        if invoice_status == "pending upload": invoice_status = "done"
                        print(f"✅ Successfully attached PDFs to WO {wo_number}")
                    else:
                        print(f"No relevant PDFs (RME/TPCHD/King/Invoice) found for WO {wo_number} to attach.")

                except Exception as e:
                    print(f"⚠️ Failed to handle Invoice/Attachments for WO {wo_number}: {e}")
                    error_details = str(e)
                    
                    try:
                        if await fe_page.locator("input[name='UserName']").is_visible(timeout=2000):
                            print("🔐 Detected logout during WO processing! Re-logging in...")
                            await _ensure_logged_in(fe_page)
                            restart_needed = True
                    except Exception:
                        pass

                    if rme_status == "pending upload": rme_status = "error"
                    if tpchd_status == "pending upload": tpchd_status = "error"
                    if king_status == "pending upload": king_status = "error"
                    if invoice_status == "pending upload": invoice_status = "error"
                finally:
                    await fe_page.close()
            finally:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

            if restart_needed:
                break

            print(f"WO {wo_number} successfully finished! Saving to DB.")
            db_cursor.execute(
                'INSERT INTO work_orders (wo_number, address, error_message, rme_status, tpchd_status, king_status, invoice_status, run_time, location_code, tax_code_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (wo_number, address, error_details, rme_status, tpchd_status, king_status, invoice_status, run_time, location_code_val, tax_code_status)
            )
            db_conn.commit()

    db_conn.close()

    if restart_needed:
        print("🔄 Restarting scraper process due to session timeout...")
        return await run_scraper_pass(browser, context, page)


async def run_scraper():
    """Standalone run: open browser, one pass, close. Used for manual 'Run Now' and __main__."""
    async with async_playwright() as p:
        browser, context, page = await init_scraper_session(p)
        try:
            await run_scraper_pass(browser, context, page)
        finally:
            await browser.close()
            print("Scraper finished and closed browser.")

if __name__ == "__main__":
    asyncio.run(run_scraper())
