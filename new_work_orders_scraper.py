import asyncio
import sqlite3
import os
import requests
import tempfile
import csv
from datetime import datetime
import re
# pyrefly: ignore [missing-import]
from playwright.async_api import async_playwright
from tools import get_pdf_all_reports, address_search, Tacoma_report_lookup, King_report_lookup, upload_attachments_to_work_order, tax_rate_lookup, Accella_report_lookup, dismiss_fieldedge_popup
import shutil

king_pierce_cities = set()
try:
    with open('king_pierce_cities_plus_unincorporated.csv', 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0].strip():
                king_pierce_cities.add(row[0].strip().lower())
except Exception as e:
    print(f"⚠️ Failed to load king pierce cities CSV: {e}")


# ── Highway address detection & cleaning ──────────────────────────────────────
import re as _re

# Order matters: longer/more-specific patterns first
# The lookahead (?=\s*\d) ensures we only match when the keyword is followed
# by a route number — so named streets like "Mountain HWY" are NOT stripped.
_HIGHWAY_STRIP_PATTERN = _re.compile(
    r'\b(state\s+route|state\s+rd|highway|route|hwy|sr)(?=\s*\d)',
    flags=_re.IGNORECASE
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
    cleaned = _re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

_STREET_SUFFIXES = {
    'st', 'street', 'ave', 'avenue', 'rd', 'road', 'dr', 'drive', 
    'ln', 'lane', 'blvd', 'boulevard', 'ct', 'court', 'pl', 'place',
    'way', 'pkwy', 'parkway', 'cir', 'circle', 'hwy', 'highway', 'sr'
}

def expand_duplex_addresses(address: str) -> list:
    """
    Given an input address string (e.g. '22013/15 225th Ave E', '22013-15 225th Ave E',
    '22013 22015 225th Ave E', '101-103 Main St', or standard '22013 225th Ave E'),
    returns a list of normalized single-number addresses.
    """
    if not address or not address.strip():
        return [address]

    address_str = address.strip()
    
    # Normalize spaces around slashes and hyphens at start of address
    address_norm = _re.sub(r'^(\d+)\s*([/\-])\s*(\d+)', r'\1\2\3', address_str)
    
    # Pattern A: Building number range with / or - (Option 1 & Option 3)
    range_match = _re.match(r'^(\d+)([\/\-](?:\d+[\/\-]*)+)\s+(.*)$', address_norm)
    
    if range_match:
        first_num = range_match.group(1)
        suffix_str = range_match.group(2)
        rest_of_address = range_match.group(3)
        
        raw_parts = [p for p in _re.split(r'[\/\-]', suffix_str) if p]
        
        extracted_numbers = [first_num]
        for part in raw_parts:
            part = part.strip()
            if not part:
                continue
            if len(part) >= len(first_num):
                extracted_numbers.append(part)
            else:
                prefix_len = len(first_num) - len(part)
                if prefix_len > 0:
                    full_num = first_num[:prefix_len] + part
                    extracted_numbers.append(full_num)
                else:
                    extracted_numbers.append(part)
                    
        addresses = []
        for num in extracted_numbers:
            addresses.append(f"{num} {rest_of_address}")
        return addresses

    # Pattern B: Space-separated house numbers (Option 2: "22013 22015 225th Ave E" or "22013 15 225th Ave E")
    space_match = _re.match(r'^(\d+)\s+(\d+)\s+(.+)$', address_norm)
    if space_match:
        first_num = space_match.group(1)
        second_part = space_match.group(2)
        rest_of_address = space_match.group(3)
        
        # Check if the word immediately following second_part is a street suffix (like "123 45 Ave E")
        first_word_in_rest = rest_of_address.split()[0].lower().strip('.')
        if first_word_in_rest not in _STREET_SUFFIXES:
            # It's a duplex! e.g., "22013 22015 225th Ave E" or "22013 22015 Main St"
            if len(second_part) >= len(first_num):
                second_num = second_part
            else:
                prefix_len = len(first_num) - len(second_part)
                if prefix_len > 0:
                    second_num = first_num[:prefix_len] + second_part
                else:
                    second_num = second_part
            return [f"{first_num} {rest_of_address}", f"{second_num} {rest_of_address}"]

    return [address_str]

def parse_single_address(address: str) -> str:
    """
    Extract clean search address (Street Number + Name only), ignoring directional words.
    Also handles highway address cleaning if highway keywords are present.
    """
    cleaned_addr = address
    if is_highway_address(address):
        cleaned_addr = strip_highway_keywords(address)

    address_parts = cleaned_addr.split(' ')
    parsed_address = cleaned_addr
    if len(address_parts) >= 3:
        if len(address_parts[1]) <= 2:
            parsed_address = f"{address_parts[0]} {address_parts[2]}"
        else:
            parsed_address = f"{address_parts[0]} {address_parts[1]}"
    elif len(address_parts) == 2:
        parsed_address = f"{address_parts[0]} {address_parts[1]}"
        
    return parsed_address

async def edit_customer_and_update_tax_code(page, tax_code):
    edit_btn = page.locator("//span[normalize-space()='Edit Customer']")
    await edit_btn.wait_for(state="visible", timeout=15000)
    await edit_btn.click()
    await page.wait_for_timeout(5000)
    
    tax_code_box = page.locator("//div[@name='Tax Group']")
    # check the tax code is already set correct 
    try:
        current_tax_code = await tax_code_box.inner_text()
        if current_tax_code.lower().strip() in tax_code.lower().strip() and "inactive" not in current_tax_code.lower().strip():
            cancel_btn = page.locator("//span[normalize-space()='Cancel'] | //button[normalize-space()='Cancel']").first
            if await cancel_btn.is_visible():
                await cancel_btn.click()
                await page.wait_for_timeout(1000)
            return "already updated"
        else:
            tax_code_box.click()
            await page.wait_for_timeout(1000)
            tax_code_input = page.locator("//div[@name='Tax Group']//input")
            await tax_code_input.wait_for(state="visible", timeout=15000)
            await tax_code_input.fill(tax_code)
            await page.wait_for_timeout(1000)
            # press enter key
            await page.keyboard.press('Enter')
            await page.wait_for_timeout(1000)
            # check any inactive code in the field
            tax_code_input_check_again = page.locator("//div[@name='Tax Group']//input")
            if "inactive" in tax_code_input_check_again.lower().strip():
                # update with 2nd code
                await tax_code_input_check_again.fill(tax_code)
                await page.wait_for_timeout(1000)
                # press down arrow key
                await page.keyboard.press('ArrowDown')
                await page.wait_for_timeout(1000)
                # press enter key
                await page.keyboard.press('Enter')
                await page.wait_for_timeout(1000)
            
            # save the changes
            save_btn = page.locator("//span[normalize-space()='Save']")
            await save_btn.wait_for(state="visible", timeout=15000)
            await save_btn.click()
            await page.wait_for_timeout(1000)
            return "updated"
            
    except Exception as e:
        print(f"⚠️ Failed to get current tax code: {e}")
        try:
            cancel_btn = page.locator("//span[normalize-space()='Cancel'] | //button[normalize-space()='Cancel']").first
            if await cancel_btn.is_visible():
                await cancel_btn.click()
                await page.wait_for_timeout(1000)
        except Exception as ce:
            print(f"⚠️ Failed to close edit panel via Cancel button: {ce}")
        return "failed"





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
        ("accella_status", "not found"),
        ("invoice_status", "not found"),
        ("king_status", "not found"),
        ("run_time", "NULL"),
        ("location_code", "not found"),
        ("tax_code_status", "not found"),
        ("customer_tax_code_status", "not found"),
        ("work_order_url", "NULL"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE work_orders ADD COLUMN {col} TEXT DEFAULT '{default}'")
        except Exception:
            pass
    try:
        cursor.execute("UPDATE work_orders SET work_order_url = 'https://login.fieldedge.com/#/WorkOrder/' || wo_number WHERE work_order_url IS NULL OR work_order_url = '' OR work_order_url = 'NULL'")
    except Exception:
        pass
    conn.commit()
    return conn



async def return_customer_invoice(page):
    # Dismiss any popup before interacting with the invoice tab
    await dismiss_fieldedge_popup(page)
    await asyncio.sleep(5)

    # Click the Invoice tab
    invoice_tab = page.locator("(//div[@data-automation-id='CustomerTabsEnum-Invoice-container']/div)[1]")
    await invoice_tab.wait_for(state="visible", timeout=15000)
    await invoice_tab.click()

    # check minimum 1 invoice is available
    # Use a scoped locator tied to the invoice table, not just any tbody
    try:
        # Wait for the invoice list container to appear
        invoice_row = page.locator("//div[contains(@data-automation-id,'Invoice')]//tbody/tr[1]")
        try:
            await invoice_row.wait_for(state="visible", timeout=5000)
        except Exception:
            # Fallback to generic tbody if scoped locator fails
            invoice_row = page.locator("(//tbody/tr)[1]")
            await invoice_row.wait_for(state="visible", timeout=10000)

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
    context = await browser.new_context(accept_downloads=True)
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
            await page.locator("//button[@type='submit']").click()
    except Exception:
        pass
    try:
        await page.wait_for_url("**/Dashboard/**", timeout=15000)
    except Exception:
        print("URL didn't strictly match Dashboard, continuing anyway...")
    # Dismiss any popup that appears after initial login/load
    await dismiss_fieldedge_popup(page)
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
            await page.locator("//button[@type='submit']").click()
            try:
                await page.wait_for_url("**/Dashboard/**", timeout=20000)
            except Exception:
                pass
            print("✅ Re-login successful.")
        else:
            print("✅ Session still active.")
        # Dismiss any popup that appears after navigation/re-login
        await dismiss_fieldedge_popup(page)
    except Exception as e:
        print(f"⚠️ Login check failed: {e}")


def normalize_name(name):
    # Remove extension
    name_no_ext, _ = os.path.splitext(name)
    # Remove leading sequence prefix like "1_", "2_", "10_"
    name_clean = re.sub(r'^\d+_*', '', name_no_ext)
    return name_clean.strip().lower()


def is_matching_pattern(name, file_paths=None):
    # Match any name starting with a number followed by an underscore (e.g. "1_", "12_")
    return bool(re.match(r'^\d+_', name))


async def _process_single_work_order(page, context, wo_number, address, city, dispatch_mapping, run_time, db_conn, db_cursor, force_reprocess=False):
    """
    Process a single work order: search external sites (RME, TPCHD, King, Accella),
    fetch location code, update tax code on FieldEdge, download invoice, and attach PDFs.
    Returns (restart_needed, status_str).
    """
    # Expand address in case of duplex (e.g. '22013/15 225th Ave E' or '22013-15 225th Ave E')
    expanded_addresses = expand_duplex_addresses(address)
    if len(expanded_addresses) > 1:
        print(f"🏠 Duplex detected for WO {wo_number}! Expanded '{address}' -> {expanded_addresses}")

    if str(wo_number) in dispatch_mapping:
        d_id, dt_id = dispatch_mapping[str(wo_number)]
        work_order_url_val = f"https://login.fieldedge.com/#/DispatchSummary/{d_id}/{dt_id}"
    else:
        work_order_url_val = f"https://login.fieldedge.com/#/WorkOrder/{wo_number}"

    if not force_reprocess:
        db_cursor.execute('SELECT id FROM work_orders WHERE wo_number = ?', (wo_number,))
        if db_cursor.fetchone():
            print(f"WO {wo_number} already in DB. Passing...")
            return False, "already_in_db"

    final_rme_urls = []
    tpchd_result = []
    king_result = []
    accella_result = []
    accella_status = "not found"

    if city.lower() in king_pierce_cities:
        county = "King"
    else:
        county = "Pierce"

    for idx, single_addr in enumerate(expanded_addresses, start=1):
        parsed_single_addr = parse_single_address(single_addr)
        print(f"\n🔎 [{idx}/{len(expanded_addresses)}] Processing address variant: '{single_addr}' (parsed: '{parsed_single_addr}')")

        # 1. OnlineRME
        try:
            print(f"Pulling OnlineRME reports for address: {single_addr}")
            rme_page = await context.new_page()
            rme_url = "https://www.onlinerme.com/contractorsearchproperty.aspx"
            try:
                await rme_page.goto(rme_url, wait_until="networkidle")
            except:
                pass
            await address_search(page=rme_page, url=rme_url, address_line_1=parsed_single_addr, county=county)
            rme_res = await get_pdf_all_reports(page=rme_page, url=rme_url, input_address=single_addr)
            if rme_res and isinstance(rme_res, dict):
                urls = rme_res.get("pdf_urls", [])
                for u in urls:
                    if u not in final_rme_urls:
                        final_rme_urls.append(u)
            print(f"  ✅ OnlineRME returned {len(final_rme_urls)} total PDF URL(s) so far")
        except Exception as e:
            print(f"  ⚠️ Error fetching OnlineRME for {single_addr}: {e}")
        finally:
            await rme_page.close()

        # 2. TPCHD (Tacoma)
        try:
            print(f"Pulling TPCHD reports for address: {single_addr}")
            tpchd_page = await context.new_page()
            tpchd_url = "https://edocs.tpchd.org/"
            try:
                await tpchd_page.goto(tpchd_url, wait_until="networkidle")
            except:
                pass
            t_reports = await Tacoma_report_lookup(page=tpchd_page, url=tpchd_url, address_line_1=parsed_single_addr)
            if t_reports:
                for tr in t_reports:
                    if tr not in tpchd_result:
                        tpchd_result.append(tr)
            print(f"  ✅ TPCHD returned {len(tpchd_result)} total report(s) so far")
        except Exception as e:
            print(f"  ⚠️ Error fetching TPCHD for {single_addr}: {e}")
        finally:
            await tpchd_page.close()

        # 3. King County
        if city.lower() in king_pierce_cities:
            try:
                print(f"City '{city}' matched active list. Pulling King County reports for address: {single_addr}")
                king_page = await context.new_page()
                king_url = "https://kingcounty.maps.arcgis.com/apps/instant/sidebar/index.html?appid=6c0bbaa4339c4ffab0c53cfe1f8d3d85"
                try:
                    await king_page.goto(king_url, wait_until="networkidle")
                except:
                    pass
                k_reports, k_error = await King_report_lookup(page=king_page, url=king_url, address_line_1=single_addr)
                if k_reports:
                    for kr in k_reports:
                        if kr not in king_result:
                            king_result.append(kr)
                    print(f"  ✅ King County returned {len(king_result)} total report(s) so far")
                else:
                    print(f"  ⚠️ King County returned no reports for {single_addr}: {k_error}")
            except Exception as e:
                print(f"  ⚠️ Error fetching King County for {single_addr}: {e}")
            finally:
                await king_page.close()

        # 4. Accella
        if city.lower() not in king_pierce_cities:
            try:
                print(f"City '{city}' not in King list. Pulling Accella reports for address: {single_addr}")
                accella_page = await context.new_page()
                accella_url = "https://aca-prod.accela.com/TPCHD/Cap/CapHome.aspx?module=EnvHealth&TabName=EnvHealth"
                try:
                    await accella_page.goto(accella_url, wait_until="networkidle")
                except:
                    pass
                a_status_text, a_files = await Accella_report_lookup(page=accella_page, url=accella_url, session_id=f"wo_{wo_number}", address_line_1=parsed_single_addr)
                if a_files:
                    for af in a_files:
                        if af not in accella_result:
                            accella_result.append(af)
                    print(f"  ✅ Accella returned {len(accella_result)} total report(s) so far")
                else:
                    print(f"  ⚠️ Accella returned no reports for {single_addr}: {a_status_text}")
            except Exception as e:
                print(f"  ⚠️ Error fetching Accella for {single_addr}: {e}")
            finally:
                await accella_page.close()

    report_dict = {
        "tpchd_reports": tpchd_result,
        "king_reports": king_result,
        "accella_reports": accella_result,
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
    customer_tax_code_status = "not found"
    restart_needed = False
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

        # 2. Download TPCHD Reports (ONLY AsBuilt and Onsite and microfilm)
        if any(len(i.split(',')) > 1 and (i.split(',')[1].strip().lower() == 'asbuilt' or i.split(',')[1].strip().lower() == 'onsite' or i.split(',')[1].strip().lower() == 'microfilm') for i in tpchd_result):
            tpchd_status = "pending upload"
        for item in tpchd_result:
            try:
                parts = item.split(',')
                pdf_url = parts[0]
                record_type = parts[1].strip() if len(parts) > 1 else ""
                if record_type.lower() == 'asbuilt' or record_type.lower() == 'onsite' or record_type.lower() == 'microfilm':
                    r = session_http.get(pdf_url, stream=True, timeout=15)
                    if r.status_code == 200:
                        base_name = "AS-BUILT"
                        counter = 1
                        filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")
                        while os.path.exists(filepath):
                            counter += 1
                            filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")

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
                    counter = 1
                    filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")
                    while os.path.exists(filepath):
                        counter += 1
                        filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")

                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    file_paths.append(filepath)
                else:
                    king_status = "error"
            except Exception as e:
                print(f"Failed to download King County PDF {item}: {e}")
                king_status = "error"

        # 4. Copy Accella Reports
        if any(len(i.split(',')) > 1 and i.split(',')[1].strip().lower() == 'approved asbuilt' for i in accella_result):
            accella_status = "pending upload"
        for item in accella_result:
            parts = item.split(',')
            src_path = parts[0].strip()
            record_type = parts[1].strip() if len(parts) > 1 else "Unknown"
            
            if record_type.strip().lower() != 'approved asbuilt':
                if os.path.exists(src_path):
                    try:
                        os.remove(src_path)
                    except Exception as e:
                        print(f"Could not remove skipped Accella PDF {src_path}: {e}")
                continue
                
            upload_date = parts[2].strip().replace('/', '-') if len(parts) > 2 else ""
            
            if os.path.exists(src_path):
                formatted_type = record_type.replace(' ', '_')
                base_name = f"Accella_{formatted_type}_{upload_date}".strip('_')
                
                filepath = os.path.join(tmpdir, f"{base_name}.pdf")
                counter = 1
                while os.path.exists(filepath):
                    filepath = os.path.join(tmpdir, f"{base_name}_{counter}.pdf")
                    counter += 1
                
                try:
                    shutil.copy2(src_path, filepath)
                    file_paths.append(filepath)
                    try:
                        os.remove(src_path)
                    except Exception as e:
                        print(f"Could not remove original Accella PDF {src_path}: {e}")
                except Exception as e:
                    print(f"Failed to copy Accella PDF {src_path}: {e}")
                    accella_status = "error"
            else:
                print(f"Accella PDF missing at path {src_path}")
                accella_status = "error"

        # 5. Fetch Customer Invoice and Attach ALL Collected PDFs
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
            await dismiss_fieldedge_popup(fe_page)

            if fe_page.url and "fieldedge.com" in fe_page.url:
                work_order_url_val = fe_page.url
                print(f"Captured browser URL for WO {wo_number}: {work_order_url_val}")

            try:
                cust_link_loc = fe_page.locator('//a[contains(@class, "customer-label")]')
                await cust_link_loc.wait_for(state="visible", timeout=10000)
                href = await cust_link_loc.get_attribute("href")
                address2 = await fe_page.locator("//label[@data-automation-id='address2']").inner_text()
                zipcode = address2.split(" ")[-1]
                print(f"Fetching location code for WO {wo_number}...")
                tax_page = await context.new_page()
                location_code = None
                try:
                    tax_url = "https://webgis.dor.wa.gov/taxratelookup/SalesTax.aspx"
                    await tax_page.goto(tax_url, wait_until="networkidle")
                    for single_addr in expanded_addresses:
                        p_addr = parse_single_address(single_addr)
                        location_code = await tax_rate_lookup(tax_page, tax_url, p_addr, city, zipcode)
                        if location_code:
                            print(f"Fetched Location Code: {location_code} for WO {wo_number} using address '{p_addr}'")
                            break
                        
                except Exception as e:
                    print(f"Failed to fetch location code for WO {wo_number}: {e}")
                finally:
                    await tax_page.close()
                
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
                        await asyncio.sleep(3)

                        tax_codes_container = fe_page.locator('(//div[@name="Tax Codes"])[1]')
                        tax_dropdown = fe_page.locator("(//div[@name='Tax Codes']/div/div)[1]")
                        tax_input = fe_page.locator("((//div[@name='Tax Codes']/div/div)[1]/input)[1]")
                        tax_group_container = fe_page.locator("//div[@data-automation-id='new-section-invoice-TaxGroup-container']")
                        updated_code = ""
                        if await tax_codes_container.is_visible():
                            updated_text = await tax_codes_container.inner_text()
                            updated_code = updated_text.strip() if updated_text else ""
                        elif await tax_group_container.is_visible():
                            updated_text = await tax_group_container.inner_text()
                            updated_code = re.sub(r'Tax\s*Group', '', updated_text, flags=re.IGNORECASE).strip()
                        try:
                            if "inactive" in updated_code.lower():
                                print(f"⚠️ Updated code '{updated_code}' is inactive. Re-selecting using ArrowDown...")
                                await tax_dropdown.click()
                                await asyncio.sleep(1)
                                await tax_input.press("Meta+A")
                                await tax_input.press("Backspace")
                                await asyncio.sleep(0.5)
                                await tax_input.fill(location_code)
                                await asyncio.sleep(2)
                                await tax_input.press("ArrowDown")
                                await asyncio.sleep(1)
                                await tax_input.press("Enter")
                                await asyncio.sleep(2)

                                if await tax_codes_container.is_visible():
                                    updated_text = await tax_codes_container.inner_text()
                                    updated_code = updated_text.strip() if updated_text else ""
                                elif await tax_group_container.is_visible():
                                    updated_text = await tax_group_container.inner_text()
                                    updated_code = re.sub(r'Tax\s*Group', '', updated_text, flags=re.IGNORECASE).strip()
                                print(f"Re-selected verified code: '{updated_code}'")

                            if location_code in updated_code:
                                print("Verification succeeded!")
                            else:
                                print("Verification failed!")
                        except Exception as e:
                            print(f"Failed to verify tax code for WO {wo_number}: {e}")

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
                    await dismiss_fieldedge_popup(fe_page)

                    if location_code_val and location_code_val != "not found":
                        print(f"Updating tax code on Customer Page to: {location_code_val}")
                        try:
                            edit_res = await edit_customer_and_update_tax_code(fe_page, location_code_val)
                            print(f"Customer tax code update status: {edit_res}")
                            if edit_res == "updated":
                                customer_tax_code_status = "done"
                            elif edit_res == "already updated":
                                customer_tax_code_status = "already updated"
                            else:
                                customer_tax_code_status = "error"
                        except Exception as e:
                            print(f"⚠️ Failed to update customer tax code on Customer Page: {e}")
                            customer_tax_code_status = "error"

                    invoice_pdf_url, date_of_invoice = await return_customer_invoice(fe_page)
                    if invoice_pdf_url:
                        print(f"Found Invoice PDF URL: {invoice_pdf_url}")
                        invoice_status = "pending upload"
                        print("Waiting 4 seconds for Invoice PDF to be fully generated on Azure...")
                        await asyncio.sleep(4)
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

            if file_paths:
                seq_file_paths = []
                for idx, fp in enumerate(file_paths, start=1):
                    try:
                        dir_name = os.path.dirname(fp)
                        base_name = os.path.basename(fp)
                        new_base_name = f"{idx}_{base_name}"
                        new_fp = os.path.join(dir_name, new_base_name)
                        os.rename(fp, new_fp)
                        seq_file_paths.append(new_fp)
                        print(f"Renamed: {base_name} -> {new_base_name}")
                    except Exception as e:
                        print(f"⚠️ Failed to rename {fp} to add sequence: {e}")
                        seq_file_paths.append(fp)
                file_paths = seq_file_paths

                print(f"Uploading {len(file_paths)} PDF(s) to Work Order {wo_number}...")
                try:
                    await fe_page.goto(full_wo_url, wait_until="networkidle")
                except:
                    pass
                await fe_page.wait_for_timeout(4000)
                await dismiss_fieldedge_popup(fe_page)

                print("Checking for existing attachments to delete...")
                while True:
                    await fe_page.wait_for_timeout(1000)
                    attachment_names = await fe_page.locator('//div[@class="attachment-name"]').all_text_contents()
                    
                    match_index = -1
                    for idx, name in enumerate(attachment_names, start=1):
                        name_val = name.strip() if name else ""
                        if is_matching_pattern(name_val, file_paths):
                            match_index = idx
                            break
                            
                    if match_index == -1:
                        print("No matching attachments found to delete.")
                        break
                        
                    matched_name = attachment_names[match_index - 1].strip()
                    print(f"Deleting attachment '{matched_name}' at index {match_index}...")
                    
                    try:
                        name_loc = fe_page.locator(f'(//div[@class="attachment-name"])[{match_index}]')
                        await name_loc.hover()
                        await fe_page.wait_for_timeout(500)
                        
                        delete_loc = fe_page.locator(f'(//div[@class="fa fa-times-circle"])[{match_index}]')
                        await delete_loc.click()
                        await fe_page.wait_for_timeout(2000)
                        
                        confirm_loc = fe_page.locator(f'(//span[normalize-space()="Yes"])[2]')
                        await confirm_loc.click()
                        await fe_page.wait_for_timeout(3000)
                    except Exception as e:
                        print(f"⚠️ Error while deleting attachment at index {match_index}: {e}")
                        break

                await upload_attachments_to_work_order(
                    page=fe_page,
                    url="",
                    address_line_1="",
                    file_paths=file_paths,
                    work_order_number=str(wo_number)
                )
                await fe_page.wait_for_timeout(20000)
                if rme_status == "pending upload": rme_status = "done"
                if tpchd_status == "pending upload": tpchd_status = "done"
                if king_status == "pending upload": king_status = "done"
                if accella_status == "pending upload": accella_status = "done"
                if invoice_status == "pending upload": invoice_status = "done"
                print(f"✅ Successfully attached PDFs to WO {wo_number}")
            else:
                print(f"No relevant PDFs (RME/TPCHD/King/Accella/Invoice) found for WO {wo_number} to attach.")

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
            if accella_status == "pending upload": accella_status = "error"
            if invoice_status == "pending upload": invoice_status = "error"
        finally:
            await fe_page.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not restart_needed:
        db_cursor.execute('SELECT id FROM work_orders WHERE wo_number = ?', (wo_number,))
        row = db_cursor.fetchone()
        if row:
            print(f"WO {wo_number} already in DB. Updating record.")
            db_cursor.execute(
                '''UPDATE work_orders SET 
                    address=?, error_message=?, rme_status=?, tpchd_status=?, king_status=?, 
                    accella_status=?, invoice_status=?, run_time=?, location_code=?, 
                    tax_code_status=?, customer_tax_code_status=?, work_order_url=?
                    WHERE wo_number=?''',
                (address, error_details, rme_status, tpchd_status, king_status, accella_status, invoice_status, run_time, location_code_val, tax_code_status, customer_tax_code_status, work_order_url_val, wo_number)
            )
        else:
            print(f"WO {wo_number} successfully finished! Saving to DB.")
            db_cursor.execute(
                'INSERT INTO work_orders (wo_number, address, error_message, rme_status, tpchd_status, king_status, accella_status, invoice_status, run_time, location_code, tax_code_status, customer_tax_code_status, work_order_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (wo_number, address, error_details, rme_status, tpchd_status, king_status, accella_status, invoice_status, run_time, location_code_val, tax_code_status, customer_tax_code_status, work_order_url_val)
            )
        db_conn.commit()

    return restart_needed, "success"


async def run_scraper_pass(browser, context, page):
    """Run one scraper pass on an existing browser session."""
    run_time = datetime.utcnow().isoformat() + 'Z'

    # Always verify the session is alive before starting work
    await _ensure_logged_in(page)

    # reload page
    await page.reload()
    await asyncio.sleep(5)
    # Dismiss any popup that may appear after reload
    await dismiss_fieldedge_popup(page)

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

        restart_needed, _ = await _process_single_work_order(
            page, context, wo_number, address, city, dispatch_mapping, run_time, db_conn, db_cursor
        )

    db_conn.close()

    if restart_needed:
        print("🔄 Restarting scraper process due to session timeout...")
        return await run_scraper_pass(browser, context, page)


async def run_search_scraper_pass(browser, context, page, target_wo_numbers):
    """Run search-based scraper pass for specified work order numbers."""
    run_time = datetime.utcnow().isoformat() + 'Z'

    await _ensure_logged_in(page)
    await page.reload()
    await asyncio.sleep(5)
    await dismiss_fieldedge_popup(page)

    print("Step 1: Navigating to Work Orders...")
    await page.locator("//a[@class='work-orders']").click()
    print("Waiting for work orders table to appear...")
    await page.wait_for_selector("tbody.fixed-body", state="visible", timeout=60000)
    await asyncio.sleep(2)

    print("Clicking ALL Work Orders view filter...")
    await page.locator("//div[@data-automation-id='ALL-WO-filter-container']").click()
    await asyncio.sleep(4)
    await dismiss_fieldedge_popup(page)

    dispatch_mapping = {}
    valid_wo_list = []

    search_input = page.locator("//input[@id='search']")
    await search_input.wait_for(state="visible", timeout=30000)

    for raw_target in target_wo_numbers:
        target_wo = str(raw_target).strip()
        if not target_wo:
            continue

        print(f"\n🔍 Searching for Work Order: {target_wo}...")
        try:
            await search_input.click()
            await search_input.fill("")
            await asyncio.sleep(0.5)
            await search_input.fill(target_wo)

            try:
                async with page.expect_response(
                    lambda response: "List/Get" in response.url and response.request.method == "POST",
                    timeout=15000
                ) as response_info:
                    await search_input.press("Enter")

                list_response = await response_info.value
                json_data = await list_response.json()
                records = []
                if isinstance(json_data, dict):
                    records = json_data.get("data") or json_data.get("Data") or []
                elif isinstance(json_data, list):
                    records = json_data

                for record in records:
                    if isinstance(record, dict):
                        wo_num = str(record.get("WorkOrder") or record.get("WorkOrderNumber") or record.get("Number") or record.get("WorkOrderNo") or "")
                        disp_id = record.get("DispatchID")
                        disp_task_id = record.get("DispatchTaskID")
                        if wo_num and disp_id is not None and disp_task_id is not None:
                            dispatch_mapping[wo_num] = (disp_id, disp_task_id)
            except Exception as api_err:
                print(f"⚠️ Search API response wait failed/timed out for WO {target_wo}: {api_err}")
                await search_input.press("Enter")
                await asyncio.sleep(3)

            valid_wo_list.append(target_wo)

        except Exception as search_err:
            print(f"⚠️ Error while searching for Work Order {target_wo}: {search_err}")

    print(f"\n📋 Search capture complete. Captured Dispatch Mapping for {len(dispatch_mapping)} WO(s): {dispatch_mapping}")

    captured_wos = []
    # Visit each Work Order page directly to extract street address and city from address labels
    for target_wo in valid_wo_list:
        if str(target_wo) in dispatch_mapping:
            d_id, dt_id = dispatch_mapping[str(target_wo)]
            full_wo_url = f"https://login.fieldedge.com/#/DispatchSummary/{d_id}/{dt_id}"
        else:
            full_wo_url = f"https://login.fieldedge.com/#/WorkOrder/{target_wo}"

        print(f"\n🏠 Opening WO page to extract address for {target_wo}: {full_wo_url}")
        wo_page = await context.new_page()
        try:
            try:
                await wo_page.goto(full_wo_url, wait_until="networkidle", timeout=30000)
            except Exception:
                pass
            await wo_page.wait_for_timeout(4000)
            await dismiss_fieldedge_popup(wo_page)

            address1_loc = wo_page.locator('//label[@data-automation-id="address1"]')
            await address1_loc.wait_for(state="visible", timeout=15000)
            address = await address1_loc.inner_text()
            address = address.strip()

            address2_loc = wo_page.locator('//label[@data-automation-id="address2"]')
            await address2_loc.wait_for(state="visible", timeout=15000)
            address2 = await address2_loc.inner_text()
            address2 = address2.strip()

            addr2_parts = [p.strip() for p in address2.split(" ") if p.strip()]
            if len(addr2_parts) >= 3:
                city = " ".join(addr2_parts[:-2])
            elif len(addr2_parts) == 2:
                city = addr2_parts[0]
            else:
                city = ""

            print(f"✅ Extracted WO {target_wo} Address: '{address}', City: '{city}'")
            captured_wos.append({
                "wo_number": target_wo,
                "address": address,
                "city": city
            })
        except Exception as addr_err:
            print(f"⚠️ Could not extract address from WO page for {target_wo}: {addr_err}")
        finally:
            await wo_page.close()

    db_conn = init_work_orders_db()
    db_cursor = db_conn.cursor()
    restart_needed = False

    for item in captured_wos:
        if restart_needed:
            break
        wo_number = item["wo_number"]
        address = item["address"]
        city = item["city"]
        
        print(f"\n⚙️ Starting report & attachment automation for searched WO {wo_number}...")
        restart_needed, _ = await _process_single_work_order(
            page, context, wo_number, address, city, dispatch_mapping, run_time, db_conn, db_cursor, force_reprocess=True
        )

    db_conn.close()

    if restart_needed:
        print("🔄 Restarting search scraper process due to session timeout...")
        return await run_search_scraper_pass(browser, context, page, target_wo_numbers)



async def run_scraper():
    """Standalone run: open browser, one pass, close. Used for manual 'Run Now' and __main__."""
    async with async_playwright() as p:
        browser, context, page = await init_scraper_session(p)
        try:
            await run_scraper_pass(browser, context, page)
        finally:
            await browser.close()
            print("Scraper finished and closed browser.")


async def run_search_scraper(target_wo_numbers):
    """Standalone run: open browser, run search pass on specific WOs, close."""
    async with async_playwright() as p:
        browser, context, page = await init_scraper_session(p)
        try:
            await run_search_scraper_pass(browser, context, page, target_wo_numbers)
        finally:
            await browser.close()
            print("Search scraper finished and closed browser.")

if __name__ == "__main__":
    asyncio.run(run_scraper())

