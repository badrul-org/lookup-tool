# from playwright.async_api import async_playwright
# import asyncio
import re
import unicodedata
import json


# class LookupTool:
#     def __init__(self, page, url):
#         page = page
#         url = url
#         print(f"LookupTool initialized with URL: {url}")
#         print(f"Page URL: {page.url}")
    
async def close_browser(page, url):
    """Navigate back to the base URL"""
    if page:
        await page.goto(url)

async def tax_rate_lookup(page, url, address_line_1: str, city: str, zip: str):
    try:
        # Debug: Check current URL
        current_url = page.url
        print(f"Tax rate lookup - Current URL: {current_url}")
        
        # Debug: Check if page is loaded
        await page.wait_for_load_state("networkidle")
        print("Page loaded successfully")

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
        # await page.wait_for_timeout(5000)
        table_rows = page.locator("(//div[@id='tblSales']//tr)[3]")
        await table_rows.wait_for(state="visible", timeout=10000)
        rows = await table_rows.all()
        for row in rows:
            if "Location code" in await row.text_content():
                location_code = await row.text_content()
                location_code = location_code.replace("  ", "")
                location_code = location_code.split(")")[1]
                print(f"Location Code: {location_code}")
        return location_code

    except Exception as e:
        print(e)
        return None
async def address_search(page, url, address_line_1: str, county: str):
    try:
        # if there any SE, SW, NE, NW remove them
        address_line_1 = address_line_1.replace("SE", "")
        address_line_1 = address_line_1.replace("SW", "")
        address_line_1 = address_line_1.replace("NE", "")
        address_line_1 = address_line_1.replace("NW", "")
        # Parse address_line_1 into street number and name
        parts = address_line_1.split(' ')
        if len(parts) < 2:
            print(f"Invalid address format: {address_line_1}")
            return
        street_number = parts[0].strip()
        street_name = parts[1].strip()

        # Debug: Check current URL
        current_url = page.url
        print(f"Address search - Current URL: {current_url}")
        
        # Debug: Check if page is loaded
        await page.wait_for_load_state("networkidle")
        print("Property page loaded successfully")
        
    except Exception as e:
        print(f"Error in address_search: {e}")
        return
    
    # Wait for the county dropdown to be visible and have options populated
    county_dropdown = page.locator("select#drpCounty[name='drpCounty']")
    await county_dropdown.wait_for(state="visible")
    await page.locator("#drpCounty option").first.wait_for(state="attached")

    # Resolve the correct option value by matching visible text that starts with "Pierce"
    option_locators = await page.locator("#drpCounty option").all()
    selected_value = None
    for option in option_locators:
        text = await option.text_content()
        if (text or "").strip().startswith(county):
            selected_value = await option.get_attribute("value")
            break

    if not selected_value:
        # Fallback: try selecting by exact label without trailing spaces, in case it's present
        try:
            await county_dropdown.select_option(label=county)
            return
        except Exception:
            raise RuntimeError(f"Could not find a county option starting with '{county}'.")

    await county_dropdown.select_option(value=selected_value)
    
    await page.locator("//input[@id='txtStreetNumber']").fill(street_number)
    await page.locator("//input[@id='txtSearch']").fill(street_name)
    await page.locator("//input[@id='chkExactMatch']").click()
    # await page.wait_for_timeout(1000)
    await page.locator("//input[@id='btnSearch']").click()
    # await page.wait_for_timeout(5000)
    no_record = page.locator("//span[@id='lblMultiMatch']")
    if await no_record.is_visible():
        await page.locator("//input[@id='chkExactMatch']").click()
        # await page.wait_for_timeout(1000)
        await page.locator("//input[@id='btnSearch']").click()
async def get_pdf_all_reports(page, url, input_address: str = "", county: str = ""):
    """
    Get PDF reports and handle multimatch scenarios.
    If multimatch is detected, validates and selects only the 100% matching address.
    Returns a dictionary with multimatch data and PDF URLs.
    """
    multimatch_data = []
    pdf_urls = []
    is_multimatch = False
    
    # Helper function to normalize addresses for comparison
    def normalize_address(addr):
        """Normalize address for comparison: lowercase, remove extra spaces, remove common suffixes"""
        if not addr:
            return ""
        normalized = addr.lower().strip()
        # Remove common address suffixes that might differ
        suffixes = [' st', ' street', ' ave', ' avenue', ' rd', ' road', ' dr', ' drive', 
                   ' ln', ' lane', ' blvd', ' boulevard', ' ct', ' court', ' pl', ' place',
                   ' way', ' pkwy', ' parkway', ' cir', ' circle']
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
        # Remove extra spaces
        normalized = ' '.join(normalized.split())
        return normalized
    
    # Helper function to check if addresses match (100% match)
    def addresses_match(input_addr, site_addr):
        """Check if input address matches site address (100% match)"""
        if not input_addr or not site_addr:
            return False
        
        # Normalize both addresses
        input_norm = normalize_address(input_addr)
        site_norm = normalize_address(site_addr)
        
        # Exact match after normalization
        if input_norm == site_norm:
            return True
        
        # Also check if input address is contained in site address (for cases with apt/unit numbers)
        if input_norm in site_norm:
            return True
        
        # Check if site address is contained in input address
        if site_norm in input_norm:
            return True
        
        # Check word-by-word match (all words from input must be in site address)
        input_words = set(input_norm.split())
        site_words = set(site_norm.split())
        if input_words and input_words.issubset(site_words):
            return True
        
        return False
    
    try:
        error_message = None
        # Check if multimatch exists
        multimatch_element = page.locator("//legend[normalize-space()='Multi-Match Site Select']")
        await multimatch_element.wait_for(state="visible", timeout=1000)
        
        if await multimatch_element.is_visible():
            print("Multimatch detected, processing multiple records...")
            
            # Get all table rows - try multiple selectors to find the table
            table_rows = None
            try:
                # Try the actual table structure from the HTML
                table_rows = page.locator("//table//tbody//tr")
                await table_rows.first.wait_for(state="visible", timeout=3000)
            except:
                try:
                    # Fallback to BlackStandard class
                    table_rows = page.locator("//table[@class='BlackStandard']//tr")
                    await table_rows.first.wait_for(state="visible", timeout=3000)
                except:
                    # Try any table with tbody
                    table_rows = page.locator("//tbody//tr")
            
            rows = await table_rows.all()
            print(f"Found {len(rows)} total rows in multimatch table")
            
            # Skip header row (first row), process data rows
            if len(rows) > 1:
                exact_match_found = False
                exact_match_row = None
                exact_match_index = None
                exact_match_address = None
                
                # First pass: Check ALL rows to find the exact match (don't click yet)
                # Skip header row (index 0), process data rows starting from index 1
                print(f"Checking all {len(rows)-1} data rows for address match with input: '{input_address}'")
                for i, row in enumerate(rows[1:], 1):  # Skip header row
                    try:
                        # Get all td elements in this row
                        cells = await row.locator("td").all()
                        if len(cells) < 4:
                            print(f"Row {i} has insufficient cells ({len(cells)}), skipping")
                            continue
                        
                        # Column indices based on actual table structure:
                        # 0: magnify icon/link
                        # 1: Tax ID
                        # 2: Site Name
                        # 3: Site Address
                        site_address = await cells[3].text_content()
                        site_address = site_address.strip() if site_address else ''
                        
                        print(f"Row {i} - Site Address: '{site_address}'")
                        
                        # Check if this address matches the input address
                        if input_address:
                            match_result = addresses_match(input_address, site_address)
                            print(f"  Match check: {match_result}")
                            if match_result:
                                exact_match_found = True
                                exact_match_row = row
                                exact_match_index = i
                                exact_match_address = site_address
                                print(f"✓ Found exact match at row {i}: '{site_address}' matches input '{input_address}'")
                                # Don't break - continue checking all rows to see if there are multiple matches
                                # But we'll use the first match found
                        else:
                            print(f"  No input address provided for matching")
                    except Exception as e:
                        print(f"Error checking address match for row {i}: {e}")
                        continue
                
                # If we found an exact match, use only that row
                if exact_match_found and exact_match_row:
                    print(f"\n=== Processing exact match: Row {exact_match_index} - Address: '{exact_match_address}' ===")
                
                # If exact match found, process only that row
                if exact_match_found and exact_match_row:
                    try:
                        # Get all td elements in the exact match row
                        cells = await exact_match_row.locator("td").all()
                        if len(cells) < 10:
                            print(f"Exact match row has insufficient cells ({len(cells)})")
                            raise Exception("Insufficient cells in exact match row")
                        
                        # Extract table data using correct column indices
                        # 0: magnify icon/link (clickable)
                        # 1: Tax ID
                        # 2: Site Name
                        # 3: Site Address
                        # 4: Last Name
                        # 5: First Name
                        # 6: Company Name
                        # 7: JurisdictionID
                        # 8: City
                        # 9: County
                        tax_id = await cells[1].text_content()
                        site_name = await cells[2].text_content()
                        site_address = await cells[3].text_content()
                        last_name = await cells[4].text_content()
                        first_name = await cells[5].text_content()
                        company_name = await cells[6].text_content()
                        jurisdiction = await cells[7].text_content()
                        city = await cells[8].text_content()
                        county = await cells[9].text_content()
                        
                        # Create structured data for the exact match entry
                        multimatch_entry = {
                            'row_number': exact_match_index,
                            'tax_id': tax_id.strip() if tax_id else '',
                            'site_name': site_name.strip() if site_name else '',
                            'site_address': site_address.strip() if site_address else '',
                            'last_name': last_name.strip() if last_name else '',
                            'first_name': first_name.strip() if first_name else '',
                            'company_name': company_name.strip() if company_name else '',
                            'jurisdiction': jurisdiction.strip() if jurisdiction else '',
                            'city': city.strip() if city else '',
                            'county': county.strip() if county else '',
                            'pdf_urls': []
                        }
                        
                        # Click on the magnify icon/link for THIS SPECIFIC ROW (the exact match)
                        print(f"Clicking magnify icon for exact match row {exact_match_index}...")
                        try:
                            # Get the cells again to ensure we have the right row
                            match_cells = await exact_match_row.locator("td").all()
                            if len(match_cells) > 0:
                                # Try clicking the anchor with the magnify image in the first cell
                                clickable = match_cells[0].locator("a").first
                                if await clickable.count() > 0:
                                    await clickable.click()
                                    print(f"Successfully clicked magnify icon for row {exact_match_index}")
                                else:
                                    # Fallback: click the first cell directly
                                    await match_cells[0].click()
                                    print(f"Clicked first cell directly for row {exact_match_index}")
                            else:
                                raise Exception("No cells found in exact match row")
                        except Exception as click_error:
                            print(f"Error clicking row {exact_match_index}: {click_error}")
                            # Try alternative: click the row itself
                            try:
                                await exact_match_row.click()
                                print(f"Clicked row {exact_match_index} directly as fallback")
                            except:
                                raise Exception(f"Failed to click exact match row {exact_match_index}")
                        
                        await page.wait_for_timeout(2000)
                        
                        # Get PDF URLs for this specific row
                        row_pdf_urls, error_message = await get_report_pdf(page, url)
                        multimatch_entry['pdf_urls'] = row_pdf_urls or []
                        
                        # Set as single match (not multimatch) since we found exact match
                        pdf_urls = row_pdf_urls or []
                        is_multimatch = False
                        
                        print(f"✓ Processed exact match row {exact_match_index}: '{multimatch_entry['site_address']}' - Found {len(row_pdf_urls)} PDFs")
                        
                        # Get Application History reports for the exact match
                        # IMPORTANT: After RME reports, we're still on the property page (Service History page)
                        # We need to go back ONCE to get to the property page where Application History button is visible
                        # Then click Application History directly without re-searching
                        application_history_urls = []
                        application_history_error = None
                        try:
                            matched_address = multimatch_entry['site_address']
                            matched_county = county.strip() if county else ''
                            
                            # Only get Application History for King County
                            if matched_county and matched_county.lower() == 'king':
                                print(f"Getting Application History for exact match address: '{matched_address}' (County: {matched_county})")
                                
                                # After get_report_pdf, we're on Service History page
                                # Go back ONCE to get to property page (where Application History button is)
                                print("Going back to property page to access Application History...")
                                try:
                                    await page.go_back()
                                    await page.wait_for_timeout(2000)
                                    print("Back on property page")
                                except Exception as back_err:
                                    print(f"Error going back: {back_err}")
                                    # If go_back fails, try to navigate to property page
                                    await page.goto(url, wait_until="networkidle")
                                    await page.wait_for_timeout(2000)
                                
                                # Now we should be on property page, check if Application History button is visible
                                # try:
                                #     application_history_probe = page.locator("//div[contains(text(),'Application History')]")
                                #     await application_history_probe.wait_for(state="visible", timeout=5000)
                                #     application_history_visible = await application_history_probe.is_visible()
                                #     if application_history_visible:
                                #         print("✓ Application History button is visible, proceeding to extract...")
                                #         # Click Application History directly - no need to re-search!
                                #         application_history_urls, application_history_error = await get_application_history_reports(page, url, matched_address, matched_county, skip_check=True)
                                #     else:
                                #         raise Exception("Application History button not visible after going back")
                                # except Exception as verify_err:
                                #     print(f"Application History button not accessible: {verify_err}")
                                #     application_history_urls = []
                                #     application_history_error = f"Application History button not accessible: {verify_err}"
                                application_history_urls = []
                                application_history_error = "Disabled"
                            else:
                                application_history_urls = []
                                application_history_error = None
                                print(f"Skipping Application History (not King County: {matched_county})")
                            print(f"Application History reports for exact match: {application_history_urls}")
                        except Exception as e:
                            print(f"Error fetching Application History for exact match: {e}")
                            import traceback
                            print(traceback.format_exc())
                            application_history_error = str(e)
                        
                    except Exception as e:
                        print(f"Error processing exact match row {exact_match_index}: {e}")
                        error_message = f"Error processing exact match: {str(e)}"
                else:
                    # No exact match found - process all rows as before (preserve existing functionality)
                    print(f"\n⚠ No exact match found for input address '{input_address}'")
                    print(f"Processing all {len(rows)-1} multimatch entries (preserving existing functionality)...")
                    for i, row in enumerate(rows[1:], 1):  # Skip header row
                        try:
                            # Get all td elements in this row
                            cells = await row.locator("td").all()
                            if len(cells) < 10:
                                print(f"Row {i} has insufficient cells ({len(cells)}), skipping")
                                continue
                            
                            # Extract table data using correct column indices
                            tax_id = await cells[1].text_content()
                            site_name = await cells[2].text_content()
                            site_address = await cells[3].text_content()
                            last_name = await cells[4].text_content()
                            first_name = await cells[5].text_content()
                            company_name = await cells[6].text_content()
                            jurisdiction = await cells[7].text_content()
                            city = await cells[8].text_content()
                            county = await cells[9].text_content()
                            
                            # Create structured data for this multimatch entry
                            multimatch_entry = {
                                'row_number': i,
                                'tax_id': tax_id.strip() if tax_id else '',
                                'site_name': site_name.strip() if site_name else '',
                                'site_address': site_address.strip() if site_address else '',
                                'last_name': last_name.strip() if last_name else '',
                                'first_name': first_name.strip() if first_name else '',
                                'company_name': company_name.strip() if company_name else '',
                                'jurisdiction': jurisdiction.strip() if jurisdiction else '',
                                'city': city.strip() if city else '',
                                'county': county.strip() if county else '',
                                'pdf_urls': []
                            }
                            
                            # Click on the magnify icon/link (first td, first anchor or image)
                            try:
                                # Try clicking the anchor with the magnify image
                                clickable = cells[0].locator("a").first
                                await clickable.click()
                            except:
                                # Fallback: click the first cell
                                await cells[0].click()
                            
                            await page.wait_for_timeout(2000)
                            
                            # Get PDF URLs for this specific row
                            row_pdf_urls, error_message = await get_report_pdf(page, url)
                            multimatch_entry['pdf_urls'] = row_pdf_urls or []
                            
                            # Add to multimatch data
                            multimatch_data.append(multimatch_entry)
                            
                            print(f"Processed multimatch row {i}: {multimatch_entry['site_name']} - {len(row_pdf_urls)} PDFs")
                            
                            # Go back to multimatch table
                            await page.go_back()
                            await page.wait_for_timeout(1000)
                            await page.go_back()
                            await page.wait_for_timeout(1000)
                            
                        except Exception as e:
                            print(f"Error processing multimatch row {i}: {e}")
                            continue
                    
                    print(f"Completed multimatch processing: {len(multimatch_data)} entries")
                    is_multimatch = len(multimatch_data) > 0
            else:
                pdf_urls = []
                error_message = f"{len(rows)} matching addresses found. Please Check your address."
                is_multimatch = False
                # Do not return early; fall through to unified return structure
                
        else:
             print("No multimatch, processing single record...")
             # No multimatch, get PDFs for single record
             pdf_urls, error_message = await get_report_pdf(page, url)
             is_multimatch = False

    except Exception as e:
        print(f"Error in get_pdf_all_reports: {e}")
        # Fallback: try to get PDFs anyway
        try:
            pdf_urls, error_message = await get_report_pdf(page, url)
        except Exception as fallback_error:
            print(f"Fallback PDF retrieval also failed: {fallback_error}")
    
    # Return structured data (include Application History if extracted)
    result = {
        'multimatch_data': multimatch_data,
        'pdf_urls': pdf_urls,
        'is_multimatch': is_multimatch,
        'error_message': error_message
    }
    
    # Add Application History if it was extracted (for exact match in multimatch)
    if 'application_history_urls' in locals():
        result['application_history_reports'] = application_history_urls
        if application_history_error:
            result['application_history_error'] = application_history_error
    
    return result

async def get_report_pdf(page, url):
    pdf_urls = []
    error_message = None
    try:
        header = page.locator("//div[@id='HeaderContainer']")
        await header.wait_for(state="visible", timeout=10000)
        visible = True
    except Exception as e:
        visible = False

    if visible:
        service_history = page.locator("//div[contains(text(),'Service History')]")
        await service_history.wait_for(state="visible")
        await service_history.click()
        # await page.wait_for_timeout(5000)
        # try:
        first_row = page.locator("(//tr[@valign='top'])[1]")
        try:
            await first_row.wait_for(state="visible", timeout=10000)
            #     print(f"First row: {first_row}")
            #     await first_row.wait_for(state="visible", timeout=10000)
            #     First_row_visible = True
            #     print(f"First row visible: {First_row_visible}")
            # except Exception as e:
            #     First_row_visible = False
            #     print(f"First row visible: {First_row_visible}")
            if await first_row.is_visible():                # get the report 
                row = page.locator("(//tr[@valign='top'])")
                rows = await row.all()
                count = len(rows)
                print(f"Count: {count}")
                pdf_urls = []
                # if  :
                for i , row in enumerate(rows):
                    # collect latest 3 pdfs
                    if i < 3:
                        # row_number = row.locator("(//td)[1]").text_content()
                        image_input = page.locator(f"((//tr[@valign='top'])[{i+1}]//input[@type='image'])[1]")
                        # open iframe in new tab
                        type = page.locator(f"((//tr[@valign='top'])[{i+1}]//td)[3]")
                        date_cell = page.locator(f"((//tr[@valign='top'])[{i+1}]//td)[1]")
                        type = await type.text_content()
                        type = type.strip()
                        # Extract and normalize the displayed date text
                        try:
                            raw_date_text = await date_cell.text_content()
                            date_text = (raw_date_text or '').strip()
                        except Exception:
                            date_text = ''
                        if type == "PUMP":
                            type = "PUMPING"
                        # print(f"Type: {type}")
                        # async with page.expect_popup() as popup_info:
                        await image_input.click()
                        # await page.wait_for_timeout(10000)
                        # new_tab = await popup_info.value

                        # print("New tab URL:", new_tab.url)
                        # await page.wait_for_timeout(10000)
                        # download the pdf from iframe 
                        try:
                            iframe = page.locator("//iframe")
                            await iframe.wait_for(state="visible", timeout=10000)
                            pdf_url = await page.locator("iframe").get_attribute("src")
                            print(f"Original PDF URL: {pdf_url}")
                                                    
                            if not pdf_url:
                                print("No PDF URL found in iframe")
                                continue
                            
                            # Construct the full URL
                            if pdf_url.startswith("http"):
                                full_pdf_url = pdf_url
                            elif pdf_url.startswith("/"):
                                full_pdf_url = f"https://www.onlinerme.com{pdf_url}"
                            else:
                                full_pdf_url = f"https://www.onlinerme.com/{pdf_url}"
                            pdf_urls.append(f"{full_pdf_url},{type},{date_text}")
                                
                            await page.go_back()
                            await page.wait_for_timeout(1000)
                            
                        except Exception as e:
                            print(f"Error downloading PDF: {e}")
                            # Try to go back even if there was an error
                            try:
                                await page.go_back()
                                await page.wait_for_timeout(5000)
                            except:
                                pass
                            continue
                # collect the TIME OF SALE OSS INSPECTION REPORT from application history
                await page.locator("//div[contains(text(),'Application History')]").click()
                await page.wait_for_timeout(3000)
                
                rows_locator = page.locator('//tbody/tr[td[contains(text(), "TIME OF SALE OSS INSPECTION REPORT")]]')
                rows_count = await rows_locator.count()
                print(f"Rows count: {rows_count}")
                for i in range(rows_count):
                    row = rows_locator.nth(i)
                    link = row.locator("a").first
                    href = await link.get_attribute("href")
                    print(f"Href: {href}")
                    if href:
                        date_text = await row.locator("td").nth(2).text_content()
                        date_text = date_text.strip() if date_text else ""
                        
                        # Handle relative vs absolute URL
                        if not href.startswith("http"):
                            href = href.lstrip("/")
                            full_url = f"https://www.onlinerme.com/{href}"
                        else:
                            full_url = href
                        print(f"Full URL: {full_url}")
                        # open new page not popup and get the pdf url
                        new_page = await page.context.new_page()
                        try:
                            # Setting a reasonable timeout so we don't hang if it doesn't load
                            await new_page.goto(full_url, wait_until="networkidle", timeout=15000)
                            await new_page.wait_for_timeout(2000)
                            
                            pdf_url = new_page.url
                            pdf_urls.append(f"{pdf_url},TIME OF SALE OSS INSPECTION REPORT,{date_text}")
                        except Exception as e:
                            print(f"Failed to follow OnlineRME link redirect for OSS report: {e}")
                        finally:
                            await new_page.close()
            else:
                pdf_urls = []
                error_message = "No PDF URLs found"
                return pdf_urls, error_message
        except Exception as e:
            print(f"!!! FATAL ERROR in get_pdf_all_reports: {e} !!!")
            pdf_urls = []
            error_message = "No PDF URLs found"
            return pdf_urls, error_message
    if not pdf_urls and error_message is None:
        error_message = "No PDF URLs found"
    print(f"PDF URLs: {pdf_urls}")
    return pdf_urls, error_message

async def get_application_history_reports(page, url, address_line_1: str = "", county: str = "", skip_check: bool = False):
    """
    Get Application History (Time of Sale) reports from RME.
    - Clicks Application History button
    - Reads the application grid (#ctl02_grdApplications)
    - Captures completed date and the View link
    - If available, also captures the final PDF link from the View page
    Returns list of strings: "pdf_or_view_url,TIME OF SALE REPORT,completed_date"
    
    skip_check: If True, skip the initial Application History button check (already done in caller)
    """
    application_history_urls = []
    error_message = None
    base = "https://www.onlinerme.com"

    try:
        # When skip_check=True, caller has already ensured we're on property page with button visible
        # Just click Application History directly - NO navigation, NO address search
        if skip_check:
            print("skip_check=True: Application History button should already be visible, clicking directly...")
            # Just wait for button and click - no checks, no navigation
            application_history = page.locator("//div[contains(text(),'Application History')]")
            await application_history.wait_for(state="visible", timeout=10000)
            await application_history.click()
        else:
            # For single match (non-multimatch), check if Application History button is visible
            # If not visible, re-run address search to reselect the property
            try:
                # Ensure we are on the property page; if not, navigate back
                try:
                    if "onlinerme.com/contractorsearchproperty" not in (page.url or ""):
                        await page.goto(url, wait_until="networkidle")
                except Exception:
                    pass
                
                application_history_probe = page.locator("//div[contains(text(),'Application History')]")
                try:
                    await application_history_probe.wait_for(state="visible", timeout=3000)
                    application_history_visible = await application_history_probe.is_visible()
                    if application_history_visible:
                        print("Application History button is visible, proceeding...")
                    else:
                        application_history_visible = False
                        print("Application History button not visible initially")
                except:
                    application_history_visible = False
                    print("Application History button not visible initially")
                
                if not application_history_visible:
                    print("Application History button not visible, re-running address search...")
                    if address_line_1 and county:
                        try:
                            await address_search(page, url, address_line_1, county)
                            await page.wait_for_timeout(2000)
                            # Check again after search
                            application_history_probe = page.locator("//div[contains(text(),'Application History')]")
                            await application_history_probe.wait_for(state="visible", timeout=5000)
                            print("Application History button visible after address search")
                        except Exception as e:
                            print(f"Re-run address search failed for Application History: {e}")
                            # Don't raise - continue to try anyway
            except Exception as e:
                print(f"Error checking Application History button visibility: {e}")
                # If button still not visible, try to re-search anyway (for single match scenarios)
                if address_line_1 and county:
                    try:
                        print("Attempting address search as fallback...")
                        await address_search(page, url, address_line_1, county)
                        await page.wait_for_timeout(2000)
                    except Exception as search_error:
                        print(f"Fallback address search also failed: {search_error}")
                        # Don't raise - let it continue and see if button appears

            # Open Application History
            application_history = page.locator("//div[contains(text(),'Application History')]")
            await application_history.wait_for(state="visible", timeout=10000)
            await application_history.click()

        # Wait for the applications table
        table = page.locator("//table[@id='ctl02_grdApplications']")
        await table.wait_for(state="visible", timeout=10000)

        # Data rows (skip header) using CSS locator to avoid XPath token errors
        all_rows = await table.locator("tr").all()
        rows_list = all_rows[1:] if len(all_rows) > 1 else []
        print(f"Application History rows: {len(rows_list)}")

        for idx, row in enumerate(rows_list, 1):
            try:
                # Columns: Application, Submitted, Completed, View (explicit td positions)
                cells = await row.locator("td").all()
                if len(cells) < 4:
                    continue
                application_text = (await cells[0].text_content() or "").strip()
                completed = (await cells[2].text_content() or "").strip()  # td[3] 0-based idx=2

                # Only keep Time of Sale rows
                if "TIME OF SALE" not in application_text.upper():
                    continue

                view_href = ""
                view_link = None
                try:
                    # Prefer known id pattern; fallback to first anchor in last cell
                    view_link = row.locator("a[id*='hypViewReport']").first
                    if await view_link.count() == 0:
                        view_link = row.locator("td:last-child a").first
                    view_href = await view_link.get_attribute("href") or ""
                except Exception:
                    view_href = ""

                # Normalize view URL
                if view_href:
                    if view_href.startswith("http"):
                        view_url = view_href
                    elif view_href.startswith("/"):
                        view_url = f"{base}{view_href}"
                    else:
                        view_url = f"{base}/{view_href}"
                else:
                    view_url = ""

                if not view_url:
                    # Nothing to open; skip row
                    continue

                final_url = view_url

                # Try to open the View link and capture a PDF link if present
                # Get URL instantly and close tab immediately
                view_page = None
                try:
                    view_page = await page.context.new_page()
                    # Use "domcontentloaded" instead of "networkidle" for faster loading
                    await view_page.goto(view_url, wait_until="domcontentloaded", timeout=5000)

                    pdf_candidate = None
                    # Try explicit final report link first - with short timeout
                    try:
                        pdf_candidate = await view_page.locator("a[href*='tempFiles'][href$='.pdf']").first.get_attribute("href", timeout=2000)
                    except Exception:
                        pdf_candidate = None
                    # Fallback: any pdf link - with short timeout
                    if not pdf_candidate:
                        try:
                            pdf_candidate = await view_page.locator("a[href*='.pdf']").first.get_attribute("href", timeout=2000)
                        except Exception:
                            pdf_candidate = None
                    # Fallback: iframe src - with short timeout
                    if not pdf_candidate:
                        try:
                            pdf_candidate = await view_page.locator("iframe").first.get_attribute("src", timeout=2000)
                        except Exception:
                            pdf_candidate = None

                    # Extract final URL immediately
                    if pdf_candidate:
                        if pdf_candidate.startswith("http"):
                            final_url = pdf_candidate
                        elif pdf_candidate.startswith("/"):
                            final_url = f"{base}{pdf_candidate}"
                        else:
                            final_url = f"{base}/{pdf_candidate}"
                    else:
                        final_url = view_url or ""
                    
                    # Close the tab IMMEDIATELY after getting the URL (no delay)
                    try:
                        await view_page.close()
                        print(f"✓ Closed Application History view tab for row {idx} immediately after getting URL")
                        view_page = None  # Mark as closed
                    except Exception as close_err:
                        print(f"Error closing view tab for row {idx}: {close_err}")
                        
                except Exception as e:
                    print(f"Could not open or parse view link for row {idx}: {e}")
                    final_url = view_url or ""
                    # Make sure to close tab even if there was an error
                    if view_page:
                        try:
                            await view_page.close()
                            print(f"✓ Closed Application History view tab for row {idx} after error")
                        except Exception as close_err:
                            print(f"Error closing view tab for row {idx} after error: {close_err}")

                application_history_urls.append(f"{final_url or view_url},TIME OF SALE REPORT,{completed}")
            except Exception as e:
                print(f"Error processing Application History row {idx}: {e}")
                continue

    except Exception as e:
        print(f"Error accessing Application History: {e}")
        error_message = "Could not access Application History"

    if not application_history_urls and error_message is None:
        error_message = "No Time of Sale Reports found"

    print(f"Application History URLs: {application_history_urls}")
    return application_history_urls, error_message

async def Tacoma_report_lookup(page, url, address_line_1: str):
    # url = "https://edocs.tpchd.org/"
    tacoma_reports = []
    # try:
    #     await page.goto(url)
    # except Exception as e:
    #     pass
    address_input = page.locator("//input[@id='TextBox1']")
    await address_input.wait_for(state="visible", timeout=10000)
    await address_input.fill(address_line_1)
    await page.locator("//input[@id='Button1']").click()
    # await page.wait_for_timeout(10000)
    report_table = page.locator("//table[@id='GridView1']")
    try:
        await report_table.wait_for(state="visible", timeout=5000)
        if await report_table.is_visible():
            rows = await page.locator("//table[@id='GridView1']//tr").all()
            # start from 2nd row
            rows = rows[1:]
            for row in rows:
                # last data have the link
                href = await row.locator("//td").last.locator("//a").get_attribute("href")
                recordType = await row.locator("//td").nth(0).text_content()
                owner = await row.locator("//td").nth(1).text_content()
                address = await row.locator("//td").nth(2).text_content()
                additional = await row.locator("//td").nth(3).text_content()
                city = await row.locator("//td").nth(4).text_content()
                state = await row.locator("//td").nth(5).text_content()
                zipCode = await row.locator("//td").nth(6).text_content()
                parcel = await row.locator("//td").nth(7).text_content()

                if href:
                    # Replace backslashes with forward slashes for proper URL formatting
                    href = href.replace('\\', '/')
                    full_url = url + href
                    tacoma_reports.append(f"{full_url},{recordType},{owner},{address},{additional},{city},{state},{zipCode},{parcel}")
                    print(full_url)
    except Exception as e:
        print(e)
    return tacoma_reports
async def King_report_lookup(page, url, address_line_1: str):
    error_message = None
    # url = "https://kingcounty.maps.arcgis.com/apps/instant/sidebar/index.html?appid=6c0bbaa4339c4ffab0c53cfe1f8d3d85"
    king_reports = []
    
    # Use full address as-is for the first search (do not strip directional or suffix)
    address_parts = address_line_1.strip().split()
    search_address = address_line_1.strip()
    # Fallback: remove single-letter words (e.g. directional "S", "N") from the address
    fallback_address = ' '.join(w for w in address_parts if len(w) > 2)
    if fallback_address == search_address:
        fallback_address = search_address  # nothing to strip, no fallback needed
    should_try_full_address = False  # already using full address first; fallback is shorter form
    print(f"King County: First search with full address: {search_address}")

    address_input = page.get_by_role("searchbox", name="Search")
    await address_input.wait_for(state="visible", timeout=10000)

    # First attempt: search with full address as-is
    await address_input.clear()
    await address_input.type(f"{search_address}\n")
    await page.wait_for_timeout(3000)
    
    # Check if no results found message appears
    no_results_found = False
    try:
        no_found = page.locator(f"//div[normalize-space()='There were no results found for \"{search_address}\".']")
        await no_found.wait_for(state="visible", timeout=5000)
        if await no_found.is_visible():
            no_results_found = True
            print(f"King County: No results message found for {search_address}")
    except Exception as e:
        # No "no results" message means we might have results, continue to check for reports
        pass
    
    # If no "no results" message, try to extract reports to see if any were found
    if not no_results_found:
        await page.wait_for_timeout(15000)
        # click in the center of the map exclude the sidebar (assuming 1280x720 viewport, sidebar ~350px)
        # Center X = 350 + (1280-350)/2 = 815, Center Y = 360
        await page.mouse.click(800, 360)
        try:
            link = page.locator("(//strong[normalize-space()='King County septic permitting records'])[1]")
            await link.wait_for(state="visible", timeout=20000)
            links = page.locator("//div[@class='esri-feature-content']")
            print(f"Links: {links}")
            all_links = await links.all()
            # remove email links
            for link in all_links:
                text = await link.inner_html()
                if "@" in text:
                    continue
                if "King County septic permitting records" in text:
                    count = await link.locator("a").count()
                    print(f"Found {count} links")
                    for i in range(count):
                        href = await link.locator("a").nth(i).get_attribute("href")
                        king_reports.append(href)
                    break
        except Exception as e:
            print(f"King County: Error extracting reports for {search_address}: {e}")
            # If extraction failed, treat as no results
            no_results_found = True
    
    # If no results found OR no reports extracted, retry with fallback (first 2 words)
    if (no_results_found or len(king_reports) == 0) and fallback_address != search_address:
        print(f"King County: No results for '{search_address}', retrying with fallback: {fallback_address}")
        king_reports = []
        await address_input.clear()
        await address_input.type(f"{fallback_address}\n")
        await page.wait_for_timeout(3000)

        no_results_found_full = False
        try:
            no_found_full = page.locator(f"//div[normalize-space()='There were no results found for \"{fallback_address}\".']")
            await no_found_full.wait_for(state="visible", timeout=5000)
            if await no_found_full.is_visible():
                no_results_found_full = True
                error_message = f"There is no King County result found for {address_line_1}"
                king_reports = []
                print(error_message)
                return king_reports, error_message
        except Exception:
            pass

        if not no_results_found_full:
            await page.wait_for_timeout(15000)
            await page.mouse.click(800, 360)
            try:
                link = page.locator("(//strong[normalize-space()='King County septic permitting records'])[1]")
                await link.wait_for(state="visible", timeout=20000)
                links = page.locator("//div[@class='esri-feature-content']")
                print(f"Links: {links}")
                all_links = await links.all()
                for link in all_links:
                    text = await link.inner_html()
                    if "@" in text:
                        continue
                    if "King County septic permitting records" in text:
                        count = await link.locator("a").count()
                        print(f"Found {count} links")
                        for i in range(count):
                            href = await link.locator("a").nth(i).get_attribute("href")
                            king_reports.append(href)
                        break
            except Exception as e:
                print(f"King County: Error extracting reports for fallback {fallback_address}: {e}")
                if len(king_reports) == 0:
                    error_message = f"There is no King County result found for {address_line_1}"
                    return king_reports, error_message
    elif no_results_found or len(king_reports) == 0:
        error_message = f"There is no King County result found for {search_address}"
        king_reports = []
        print(error_message)
        return king_reports, error_message
    
    return king_reports, error_message

async def Create_Customer(page, url, customer_data: dict):
    try:
        # Quick check if it is logout or not
        login_email = page.locator("//input[@id='LoginEmail']")
        try:
            await login_email.wait_for(state="visible", timeout=1000)
            # login if it is logout
            with open("credentials.json", "r") as f:
                credentials = json.load(f)
            email = credentials.get("email")
            password = credentials.get("password")
            await page.locator("//input[@id='LoginEmail']").fill(email)
            await page.locator("//input[@id='LoginPassword']").fill(password)
            await page.locator("//input[@id='LoginButton']").click()
            await page.wait_for_timeout(5000)
            page.goto("https://login.fieldedge.com/#/List/1")
            await page.wait_for_timeout(5000)
        except Exception as e:
            pass
    except Exception as e:
        pass
    """Minimal create customer flow placeholder.
    Expects an authenticated FieldEdge session already present on 'page'.
    Currently, this function navigates to the dashboard and returns successfully.
    """
    try:
        create_customer_button = page.locator("//div[@id='add-item-button-container']")
        await create_customer_button.wait_for(state="visible", timeout=10000)
        await create_customer_button.click(force=True)
        display_name = customer_data.get('displayName')
        print(display_name)
        # await page.wait_for_timeout(10000)
        Tax_code_field = page.locator("(//div[@name='Tax Group']//div)[3]")
        # scroll to the Tax_code_field
        await Tax_code_field.scroll_into_view_if_needed()
        await Tax_code_field.wait_for(state="visible", timeout=10000)
        await page.wait_for_timeout(5000)
        await Tax_code_field.click()
        await page.wait_for_timeout(1000)
        await page.locator("(//div[@name='Tax Group']//div)[2]").get_by_role("searchbox").fill(customer_data.get('taxCode') or '')
        await page.locator("(//div[@name='Tax Group']//div)[2]").get_by_role("searchbox").press("Enter")
        frist_name_field = page.locator("//input[@name='First Name']")
        # scroll up to the frist_name_field
        await frist_name_field.scroll_into_view_if_needed()
        await frist_name_field.wait_for(state="visible", timeout=10000)
        await page.wait_for_timeout(1000)
        await page.fill("//input[@name='First Name']", (customer_data.get('firstName') or ''))
        await page.fill("//input[@name='Last Name']", (customer_data.get('lastName') or ''))
        await page.fill("//input[@name='Company Name']", (customer_data.get('companyName') or ''))
        # await page.locator('(//span[@title="Select"])[1]').click()
        # await page.locator('(//span[@title="Select"])[1]').fill(customer_data.get('customerType') or '')
        # await page.locator('(//span[@title="Select"])[1]').press("Enter")
        await page.fill("//textarea[contains(@class, 'customer-pinned-note')]", (customer_data.get('note') or ''))
        
        
        await page.fill("//input[@name='Address 1']", (customer_data.get('address1') or ''))
        await page.fill("//input[@name='Address 2']", (customer_data.get('address2') or ''))
        await page.fill("//input[@name='City']", (customer_data.get('city') or ''))
        await page.fill("//input[@name='State']", (customer_data.get('state') or ''))
        await page.fill("//input[@name='Zip']", (customer_data.get('zip') or ''))

        await page.fill("//input[@name='Full Name']", (customer_data.get('contactName') or ''))
        if customer_data.get('phone_checkbox') or customer_data.get('sms_checkbox'):
            await page.locator("//div[@class='checkboxes']//input[@type='checkbox']").nth(0).click()
            await page.locator("//div[@class='checkboxes']//input[@type='checkbox']").nth(2).click()
            await page.fill("//input[@name='Phone Number']", (customer_data.get('phoneNumber') or ''))
        if customer_data.get('email_checkbox'):
            await page.locator("//div[@class='checkboxes']//input[@type='checkbox']").nth(1).click()
            await page.fill("//input[@name='Email']", (customer_data.get('email') or ''))
 

        try:
            Terms_field = page.locator("//div[@name='Terms']")
            await Terms_field.wait_for(state="visible", timeout=10000)
            await Terms_field.click()
            await Terms_field.fill({customer_data.get('terms')})
            await Terms_field.press("Enter")
        except Exception as e:
            pass
        # try:
        #     await page.wait_for_timeout(10000)
        #     Tax_code_field = page.locator("(//div[@name='Tax Group']//div)[3]")
        #     await Tax_code_field.wait_for(state="visible", timeout=10000)
        #     await page.wait_for_timeout(10000)
        #     await Tax_code_field.click()
        #     await page.wait_for_timeout(20000)
        #     await Tax_code_field.get_by_role("searchbox").click()
        #     await page.wait_for_timeout(10000)
        #     print(f"Tax code: {customer_data.get('taxCode')}")
        #     # await page.wait_for_timeout(10000)
            # tax_code = customer_data.get('taxCode')
            # print(f"Tax code: {tax_code}")
            # await Tax_code_field.get_by_role("searchbox").fill(tax_code)
            # await page.wait_for_timeout(10000)
            # await Tax_code_field.get_by_role("searchbox").press("Enter")
            # await page.wait_for_timeout(10000)
            
        # except Exception as e:
        #     print(f"Error in tax code input: {e}")
        #     return "Creation Failed"


        submit_button = page.locator("//button[normalize-space()='Create']")
        await submit_button.wait_for(state="visible", timeout=10000)
        await submit_button.click()
        customer_already_exists = page.locator("(//div[normalize-space()='Record Already Exists'])[1]")
        try:
            Customer_created = page.locator("//div[@class='header-customer-title trim-text']")
            await Customer_created.wait_for(state="visible", timeout=10000)
            if await Customer_created.is_visible():
                return "Created Successfully" , [display_name]
            
        except Exception as e:
            try:
                await customer_already_exists.wait_for(state="visible", timeout=10000)
                if await customer_already_exists.is_visible():
                    return "Already Exists" , [display_name]
            # except Exception:
            #     pass
            except Exception as e:
                # return "Creation Failed"
                Yes_button = page.locator("(//span[normalize-space()='Yes'])[2]")
                try:
                    await Yes_button.wait_for(state="visible", timeout=5000)
                    await Yes_button.click()
                except Exception as e:
                    pass

                customer_already_exists = page.locator("(//div[normalize-space()='Record Already Exists'])[1]")
                try:
                    await customer_already_exists.wait_for(state="visible", timeout=10000)
                    if await customer_already_exists.is_visible():
                        return "Already Exists" , [display_name]
                except Exception as e:
                    try:
                        Customer_created = page.locator("//div[@class='header-customer-title trim-text']")
                        await Customer_created.wait_for(state="visible", timeout=10000)
                        if await Customer_created.is_visible():
                            return "Created Successfully" , [display_name]
                    except Exception as e:
                        print(f"Error in Create_Customer: {e}")
                        return "Creation Failed" , []
        
    except Exception as e:
        print(f"Error in Create_Customer: {e}")
        # Return a generic error status instead of surfacing raw errors
        return "Creation Failed" , []


async def Check_Existing_Customer(page, url, address_line_1: str):
    try:
        # Quick check if it is logout or not
        login_email = page.locator("//input[@id='LoginEmail']")
        try:
            await login_email.wait_for(state="visible", timeout=1000)
            # login if it is logout
            with open("credentials.json", "r") as f:
                credentials = json.load(f)
            email = credentials.get("email")
            password = credentials.get("password")
            await page.locator("//input[@id='LoginEmail']").fill(email)
            await page.locator("//input[@id='LoginPassword']").fill(password)
            await page.locator("//input[@id='LoginButton']").click()
            await page.wait_for_timeout(5000)
            page.goto("https://login.fieldedge.com/#/List/1")
            await page.wait_for_timeout(5000)
        except Exception as e:
            pass
    except Exception as e:
        pass
    try:
        Display_name_list = []
        search_input = page.locator("//input[@id='search']")
        await search_input.wait_for(state="visible", timeout=10000)
        await search_input.fill(address_line_1)
        await search_input.press("Enter")
        no_record = page.locator("//div[normalize-space()='There are no active items entered']")
        try:
            await no_record.wait_for(state="visible", timeout=10000)
            if await no_record.is_visible():
                return "NO CUSTOMER EXISTS" , []
        except Exception:
            table_rows = page.locator("//table//tr")
            rows = await table_rows.all()
            if len(rows) > 1:
                for i in range(len(rows)-1):
                        display_name = await page.locator(f"(//table//tr)[{i+2}]//td").nth(0).text_content()
                        display_name = display_name.strip()
                        print(f"Display name: {display_name}")
                        Display_name_list.append(display_name)
            print(f"Display name list: {Display_name_list}")
            return "Already Exists" , Display_name_list
    except Exception as e:
        return "Error" , []
    

async def Upload_Attachments(page, address_line_1: str, file_paths):
    try:
        # Quick check if it is logout or not
        login_email = page.locator("//input[@id='LoginEmail']")
        try:
            await login_email.wait_for(state="visible", timeout=1000)
            # login if it is logout
            with open("credentials.json", "r") as f:
                credentials = json.load(f)
            email = credentials.get("email")
            password = credentials.get("password")
            await page.locator("//input[@id='LoginEmail']").fill(email)
            await page.locator("//input[@id='LoginPassword']").fill(password)
            await page.locator("//input[@id='LoginButton']").click()
            await page.wait_for_timeout(5000)
            page.goto("https://login.fieldedge.com/#/List/1")
            await page.wait_for_timeout(5000)
        except Exception as e:
            pass
    except Exception as e:
        pass
    """Upload one or more files to the first matching customer by address.
    Assumes page is an authenticated FieldEdge customers list page.
    Returns tuple (num_uploaded, num_failed).
    """
    # Search by address and get result rows
    search_input = page.locator("//input[@id='search']")
    await search_input.wait_for(state="visible", timeout=15000)
    await search_input.fill(address_line_1)
    await search_input.press("Enter")

    # Wait for at least one result row
    list_first_row = page.locator("(//table//tr)[2]")

    await list_first_row.wait_for(state="visible", timeout=15000)

    # Determine latest row by activity date if multiple rows are present
    latest_row_index = 2
    try:
        rows = await page.locator("//table//tr").all()
        total_rows = len(rows)
        if total_rows > 2:
            from datetime import datetime
            def parse_activity_date(txt: str):
                txt = (txt or '').strip()
                for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
                    try:
                        return datetime.strptime(txt, fmt)
                    except Exception:
                        continue
                return None

            latest_dt = None
            for i in range(2, total_rows + 1):
                row_sel = f"(//table//tr)[{i}]"
                try:
                    r = page.locator(row_sel)
                    await r.wait_for(state="visible", timeout=10000)
                    await r.click()
                    # Wait for activity/timeline area and get most recent date
                    date_el = page.locator('(//div[@class="timeline-date-value"])[1]')
                    await date_el.wait_for(state="visible", timeout=10000)
                    date_text = await date_el.text_content()
                    dt = parse_activity_date(date_text)
                    # Track latest
                    if dt is not None and (latest_dt is None or dt > latest_dt):
                        latest_dt = dt
                        latest_row_index = i
                except Exception:
                    # Skip rows we cannot open/parse
                    pass
                finally:
                    # Go back to list for next iteration
                    try:
                        await page.go_back()
                        await page.wait_for_timeout(300)
                        await list_first_row.wait_for(state="visible", timeout=10000)
                    except Exception:
                        # If go_back fails, try to navigate back to list URL
                        try:
                            await page.goto('https://login.fieldedge.com/#/List/1')
                            await list_first_row.wait_for(state="visible", timeout=15000)
                        except Exception:
                            pass
    except Exception:
        # If any error during selection, fall back to first row
        latest_row_index = 2

    # Open the chosen (latest) row
    chosen_row = page.locator(f"(//table//tr)[{latest_row_index}]")
    await chosen_row.wait_for(state="visible", timeout=15000)
    await chosen_row.click()

    add_attachment = page.locator("(//a[contains(@class, 'base-link')]//div[normalize-space()='Add Attachment'])[1]")

    uploaded = 0
    failed = 0

    for path in file_paths:
        try:
            await add_attachment.wait_for(state="visible", timeout=15000)
            # Try the canonical file chooser path first
            try:
                async with page.expect_file_chooser(timeout=3000) as chooser_info:
                    await add_attachment.click()
                chooser = await chooser_info.value
                await chooser.set_files(path)
                uploaded += 1
                await page.wait_for_timeout(500)
                continue
            except Exception:
                # Fallback: click then try to find a file input and set files directly
                try:
                    await add_attachment.click()
                except Exception:
                    pass
                selectors = [
                    "input[type='file'][accept*='pdf']",
                    "input[type='file']",
                    "//input[@type='file']",
                ]
                input_found = False
                for sel in selectors:
                    try:
                        file_input = page.locator(sel).first
                        await file_input.wait_for(state="attached", timeout=3000)
                        await file_input.set_input_files(path)
                        uploaded += 1
                        input_found = True
                        await page.wait_for_timeout(500)
                        break
                    except Exception:
                        continue
                if not input_found:
                    failed += 1
                    print(f"Upload fallback failed for {path}: no file input found")
        except Exception as e:
            print(f"Upload failed for {path}: {e}")
            failed += 1
            continue

    return uploaded, failed

async def create_work_order(page, url, address_line_1: str, order_form_data: dict, combined: bool):
    try:
        # Quick check if it is logout or not
        login_email = page.locator("//input[@id='LoginEmail']")
        try:
            await login_email.wait_for(state="visible", timeout=1000)
            # login if it is logout
            with open("credentials.json", "r") as f:
                credentials = json.load(f)
            email = credentials.get("email")
            password = credentials.get("password")
            await page.locator("//input[@id='LoginEmail']").fill(email)
            await page.locator("//input[@id='LoginPassword']").fill(password)
            await page.locator("//input[@id='LoginButton']").click()
            await page.wait_for_timeout(5000)
            page.goto("https://login.fieldedge.com/#/List/1")
            await page.wait_for_timeout(5000)
        except Exception as e:
            pass
    except Exception as e:
        pass
    try:
    # search by address and get the result rows
        if not combined:
            search_input = page.locator("//input[@id='search']")
            await search_input.wait_for(state="visible", timeout=15000)
            await search_input.fill(address_line_1)
            await search_input.press("Enter")
            list_first_row = page.locator("(//table//tr)[2]")
            await list_first_row.wait_for(state="visible", timeout=15000)
            await list_first_row.click()
        add_work_order = page.locator("(//div[contains(@data-automation-id, 'WorkOrders')]//div)[1]")
        await add_work_order.wait_for(state="visible", timeout=15000)
        await add_work_order.click()
        add_work_order_button = page.locator("//div[contains(@class,'base-icon add')]")
        await add_work_order_button.wait_for(state="visible", timeout=15000)
        await add_work_order_button.click()
        select_task = page.locator("//div[@name='Task']")
        await select_task.wait_for(state="visible", timeout=15000)
        await select_task.click()
        await page.locator("//div[@name='Task']//input").fill(order_form_data.get('task') or '')
        await page.locator("//div[@name='Task']//input").press("Enter")
        select_lead_source = page.locator("//div[@name='Lead Source']")
        await select_lead_source.wait_for(state="visible", timeout=15000)
        await select_lead_source.click()
        await page.locator("//div[@name='Lead Source']//input").fill(order_form_data.get('lead_source') or '')
        await page.locator("//div[@name='Lead Source']//input").press("Enter")
        await page.wait_for_timeout(1000)
        await page.locator("(//div[@class='create-workorder-form-priority']//div)[6]").click()
        await page.locator("//div[@class='create-workorder-form-priority']//input").fill(order_form_data.get('priority') or '')
        await page.wait_for_timeout(1000)
        await page.locator("//div[@class='create-workorder-form-priority']//input").press("Enter")
        await page.wait_for_timeout(1000)
        await page.locator("(//textarea)[2]").fill(order_form_data.get('description') or '')
        await page.wait_for_timeout(1000)
        save_button = page.locator("//button[contains(@class,'confirm')]//span[normalize-space()='Save']")
        await save_button.wait_for(state="visible", timeout=15000)
        await save_button.click()
        try: 
            work_order_number = page.locator("(//div[@class='title-container']//span)[1]")
            await work_order_number.wait_for(state="visible", timeout=15000)
            work_order_number_text = await work_order_number.text_content()
            work_order_number = work_order_number_text.strip()
            work_order_number = work_order_number.split(":")[1].strip()

            return "Created Successfully" , work_order_number
        except Exception as e:
            print(f"Error in creating work order: {e}")
            return "Creation Failed" , None
    except Exception as e:
        print(f"Error in creating work order: {e}")
        return "Error" , None



async def upload_attachments_to_work_order(page, url, address_line_1: str, file_paths, work_order_number: str, combined: bool = False):
    try:
        # Quick check if it is logout or not
        login_email = page.locator("//input[@id='LoginEmail']")
        try:
            await login_email.wait_for(state="visible", timeout=1000)
            # login if it is logout
            with open("credentials.json", "r") as f:
                credentials = json.load(f)
            email = credentials.get("email")
            password = credentials.get("password")
            await page.locator("//input[@id='LoginEmail']").fill(email)
            await page.locator("//input[@id='LoginPassword']").fill(password)
            await page.locator("//input[@id='LoginButton']").click()
            await page.wait_for_timeout(5000)
            page.goto("https://login.fieldedge.com/#/List/1")
            await page.wait_for_timeout(5000)
        except Exception as e:
            pass
    except Exception as e:
        pass
    try:
        if not work_order_number:
            # search by address and get the result rows
            search_input = page.locator("//input[@id='search']")
            await search_input.wait_for(state="visible", timeout=15000)
            await search_input.fill(address_line_1)
            await search_input.press("Enter")
            list_first_row = page.locator("(//table//tr)[2]")
            await list_first_row.wait_for(state="visible", timeout=15000)
            await list_first_row.click()

            add_work_order = page.locator("(//div[contains(@data-automation-id, 'WorkOrders')]//div)[1]")
            await add_work_order.wait_for(state="visible", timeout=15000)
            await add_work_order.click()
            try:
                table = page.locator("//tbody[@data-automation-id='table-body']")
                await table.wait_for(state="visible", timeout=15000)
                print(f"Table is visible")
                work_order_list = page.locator("//tbody[@data-automation-id='table-body']//a")
                # await work_order_list.wait_for(state="visible", timeout=15000)
                work_order_list = await work_order_list.all()
                print(f"Found {len(work_order_list)} work orders in the list")
                # print(f"Looking for work order number: '{work_order_number}'")
                
                for work_order in work_order_list:
                    work_order_number_text = await work_order.text_content()
                    work_order_number_text = work_order_number_text.strip()
                    print(f"Checking work order: '{work_order_number_text}'")
                    if int(work_order_number_text) > 1:
                        print(f"Match found! Clicking work order: {work_order_number_text}")
                        # print(f"Match found! Clicking work order: {work_order_number}")
                        await work_order.click()
                        break
                else:
                    print(f"Work Order Not Found: '{work_order_number}'")
                    return "Work Order Not Found" , None
            except Exception as e:
                print(f"Work Order Not Found: '{work_order_number}'")
                return "Work Order Not Found" , None
                # print(f"Error in searching work order: {e}")
                # return "Error" , None
        add_attachment = page.locator("(//a[contains(@class, 'base-link')]//div[normalize-space()='Add Attachment'])[1]")
        uploaded = 0
        failed = 0

        for path in file_paths:
            try:
                await add_attachment.wait_for(state="visible", timeout=15000)
                # Try the canonical file chooser path first
                try:
                    async with page.expect_file_chooser(timeout=3000) as chooser_info:
                        await add_attachment.click()
                    chooser = await chooser_info.value
                    await chooser.set_files(path)
                    uploaded += 1
                    await page.wait_for_timeout(5000)
                    continue
                except Exception:
                    # Fallback: click then try to find a file input and set files directly
                    try:
                        await add_attachment.click()
                    except Exception:
                        pass
                    selectors = [
                        "input[type='file'][accept*='pdf']",
                        "input[type='file']",
                        "//input[@type='file']",
                    ]
                    input_found = False
                    for sel in selectors:
                        try:
                            file_input = page.locator(sel).first
                            await file_input.wait_for(state="attached", timeout=3000)
                            await file_input.set_input_files(path)
                            uploaded += 1
                            input_found = True
                            await page.wait_for_timeout(5000)
                            break
                        except Exception:
                            continue
                    if not input_found:
                        failed += 1
                        print(f"Upload fallback failed for {path}: no file input found")
            except Exception as e:
                print(f"Upload failed for {path}: {e}")
                failed += 1
                continue

        return "Uploaded Successfully" , uploaded
    except Exception as e:
        print(f"Error in uploading attachments to work order: {e}")
        return "Error" , None


async def Accella_report_lookup(page, url, session_id, address_line_1: str):
    try:
        root_page = page
        street_number = address_line_1.split(" ")[0]
        street_name = address_line_1.split(" ")[1]
        search_input_from = page.locator("//input[@title='Street No. From	']")
        await search_input_from.wait_for(state="visible", timeout=15000)
        await search_input_from.fill(street_number)
        search_input_to = page.locator("//input[@title='Street No. To	']")
        await search_input_to.wait_for(state="visible", timeout=15000)
        await search_input_to.fill(street_number)
        await page.locator("//input[contains(@name, 'txtGSStreetName')]").fill(street_name)
        await page.wait_for_timeout(1000)
        await page.locator("//a[contains(@id, 'Main_btnNewSearch')]").click()
        await page.wait_for_timeout(2000)
        try:
            first_row = page.locator("(//div[@class='ACA_Grid_OverFlow']//tr[contains(@class, 'TabRow')])[2]")
            await first_row.wait_for(state="visible", timeout=15000)
            rows = await page.locator("(//div[@class='ACA_Grid_OverFlow']//tr[contains(@class, 'TabRow')])").all()
            length = len(rows)
            
            # start from 2nd row
            for i in range(1, length + 1):
                # the first row is the header row, so we start from 2nd row
                row = page.locator(f"(//div[@class='ACA_Grid_OverFlow']//tr[contains(@class, 'TabRow')])[{i}]")
                row_text = await row.text_content()
                row_text = row_text.strip()
                
                if "Asbuilt Approved" in row_text or "Installation Permit Released" in row_text or "Closed - Asbuilt Approved" in row_text:
                    await page.locator(f"(//div[@class='ACA_Grid_OverFlow']//tr[contains(@class, 'TabRow')])[{i}]//a").click()
                    try:
                        await page.wait_for_timeout(5000)
                        record_info = page.locator("//a[@title='Record Info menu, press tab to expand']")
                        await record_info.wait_for(state="visible", timeout=15000)
                        await record_info.click()
                        #click attachments
                        click_attachments = page.locator("//a[@data-control='tab-attachments']")
                        await click_attachments.click()
                        await page.wait_for_timeout(5000)
                        try:
                            # First, try if attachments table is rendered inline on the current page
                            tbl_frame = None
                            try:
                                inline_rows = page.locator("(//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])")
                                await inline_rows.nth(1).wait_for(state="visible", timeout=2000)
                                tbl_frame = page
                            except Exception:
                                tbl_frame = None

                            # If not inline, search all frames for the attachments table
                            if tbl_frame is None:
                                for f in root_page.frames:
                                    try:
                                        probe = f.locator("(//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])")
                                        await probe.nth(1).wait_for(state="visible", timeout=2000)
                                        tbl_frame = f
                                        break
                                    except Exception:
                                        continue

                            if tbl_frame is None:
                                print("Attachments table not visible in page or frames")
                                return "No record found 1" , None

                            rows = await tbl_frame.locator("(//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])").all()
                            length = len(rows)
                            
                            files = []
                            for i in range(1, length):
                                row = tbl_frame.locator(f"(//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]")
                                try:
                                    row_text = await row.text_content(timeout=5000)
                                    row_text = row_text.strip()
                                except Exception as e:
                                    print(f"Could not access row {i+1}, stopping iteration: {e}")
                                    break
                                
                                # this is "Approved Asbuilt" pdf file to download
                                if "Approved Asbuilt" in row_text:
                                    # find the date of the record, it is in TabRow class and 1st column, it has span element with id contians "lblUploadDate"
                                    upload_date = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//span[contains(@id, 'lblUploadDate')])")
                                    await upload_date.wait_for(state="visible", timeout=2000)
                                    upload_date = await upload_date.text_content()
                                    upload_date = upload_date.strip()
                                    
                                    # download the pdf from the link in the same row
                                    async with root_page.expect_download() as download_info:
                                        download_path = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//a)[1]")
                                        await download_path.click()
                                    download = await download_info.value
                                    file_name = download.suggested_filename
                                    files.append(f"Accella_Reports/{session_id}_{file_name},Approved Asbuilt,{upload_date}")
                                    await download.save_as(f"Accella_Reports/{session_id}_{file_name}")
                                    print(f"Downloaded {file_name}")
                                    
                                # this is "Approved Record Drawing" pdf file to download
                                if "Approved Record Drawing" in row_text:
                                    # find the date of the record, it is in TabRow class and 1st column, it has span element with id contians "lblUploadDate"
                                    upload_date = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//span[contains(@id, 'lblUploadDate')])")
                                    await upload_date.wait_for(state="visible", timeout=2000)
                                    upload_date = await upload_date.text_content()
                                    upload_date = upload_date.strip()

                                    # download the pdf from the link in the same row
                                    async with root_page.expect_download() as download_info:
                                        download_path = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//a)[1]")
                                        await download_path.click()
                                    download = await download_info.value
                                    file_name = download.suggested_filename
                                    files.append(f"Accella_Reports/{session_id}_{file_name},Approved Record Drawing,{upload_date}")
                                    await download.save_as(f"Accella_Reports/{session_id}_{file_name}")
                                    print(f"Downloaded {file_name}")

                                # this is "Design or Basic Site Plan" pdf file to download
                                if "Design or Basic Site Plan" in row_text:
                                    # find the date of the record, it is in TabRow class and 1st column, it has span element with id contians "lblUploadDate"
                                    upload_date = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//span[contains(@id, 'lblUploadDate')])")
                                    await upload_date.wait_for(state="visible", timeout=2000)
                                    upload_date = await upload_date.text_content()
                                    upload_date = upload_date.strip()
                                    # download the pdf from the link in the same row
                                    async with root_page.expect_download() as download_info:
                                        download_path = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//a)[1]")
                                        await download_path.click()
                                    download = await download_info.value
                                    file_name = download.suggested_filename
                                    files.append(f"Accella_Reports/{session_id}_{file_name},Design or Basic Site Plan,{upload_date}")
                                    await download.save_as(f"Accella_Reports/{session_id}_{file_name}")
                                    print(f"Downloaded {file_name}")

                                # this is "Approved Design" pdf file to download
                                if "Approved Design" in row_text:
                                    # find the date of the record, it is in TabRow class and 1st column, it has span element with id contians "lblUploadDate"
                                    upload_date = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//span[contains(@id, 'lblUploadDate')])")
                                    await upload_date.wait_for(state="visible", timeout=2000)
                                    upload_date = await upload_date.text_content()
                                    upload_date = upload_date.strip()

                                    # download the pdf from the link in the same row
                                    async with root_page.expect_download() as download_info:
                                        download_path = tbl_frame.locator(f"((//table[contains(@id,'attachmentList')]//tr[contains(@class, 'TabRow')])[{i+1}]//a)[1]")
                                        await download_path.click()
                                    download = await download_info.value
                                    file_name = download.suggested_filename
                                    files.append(f"Accella_Reports/{session_id}_{file_name},Approved Design,{upload_date}")
                                    await download.save_as(f"Accella_Reports/{session_id}_{file_name}")
                                    print(f"Downloaded {file_name}")
                                    
                            # when the loops end return the files list
                            return "Record found, Downloaded successfully" , files
                                    
                        except Exception as e:
                            print(f"Error in downloading necessary files: {e}")
                            return "No record found 2" , None
                    except Exception as e:
                        print(f"Error in clicking attachments: {e}")
                        return "No record found 3" , None
            # If loop completes without finding a match, return a fallback
            return "No record found 4" , None
        except Exception as e:
            print(f"Error in Accella report lookup: {e}")
            return "Error" , None
    except Exception as e:
        print(f"Error in Accella report lookup: {e}")
        return "Error" , None