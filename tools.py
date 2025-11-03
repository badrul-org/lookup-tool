# from playwright.async_api import async_playwright
# import asyncio
import re
import unicodedata


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
async def address_search(page, url, street_number: str, street_name: str, county: str):
    try:
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
async def get_pdf_all_reports(page, url):
    """
    Get PDF reports and handle multimatch scenarios.
    Returns a dictionary with multimatch data and PDF URLs.
    """
    multimatch_data = []
    pdf_urls = []
    
    try:
        error_message = None
        # Check if multimatch exists
        multimatch_element = page.locator("//legend[normalize-space()='Multi-Match Site Select']")
        await multimatch_element.wait_for(state="visible", timeout=1000)
        
        if await multimatch_element.is_visible():
            print("Multimatch detected, processing multiple records...")
            
            # Get all table rows (skip header row)
            table_rows = page.locator("//table[@class='BlackStandard']//tr")
            rows = await table_rows.all()
            if len(rows) < 4:
            # Process each row in the multimatch table
                for i, row in enumerate(rows[1:], 1):  # Skip header row
                    try:
                        # Extract table data for this row
                        tax_id = await row.locator("//td").nth(1).text_content()
                        site_name = await row.locator("//td").nth(2).text_content()
                        site_address = await row.locator("//td").nth(3).text_content()
                        last_name = await row.locator("//td").nth(4).text_content()
                        first_name = await row.locator("//td").nth(5).text_content()
                        company_name = await row.locator("//td").nth(6).text_content()
                        jurisdiction = await row.locator("//td").nth(7).text_content()
                        city = await row.locator("//td").nth(8).text_content()
                        county = await row.locator("//td").nth(9).text_content()
                        
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
                        
                        # Click on this row to get its PDFs
                        row_clickable = row.locator("//td").nth(0)
                        await row_clickable.click()
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
            else:
                pdf_urls = []
                error_message = f"{len(rows)} matching addresses found. Please Check your address."
                # Do not return early; fall through to unified return structure
                
        else:
             print("No multimatch, processing single record...")
             # No multimatch, get PDFs for single record
             pdf_urls, error_message = await get_report_pdf(page, url)

    except Exception as e:
        print(f"Error in get_pdf_all_reports: {e}")
        # Fallback: try to get PDFs anyway
        try:
            pdf_urls, error_message = await get_report_pdf(page, url)
        except Exception as fallback_error:
            print(f"Fallback PDF retrieval also failed: {fallback_error}")
    
    # Return structured data
    return {
        'multimatch_data': multimatch_data,
        'pdf_urls': pdf_urls,
        'is_multimatch': len(multimatch_data) > 0,
        'error_message': error_message
    }

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
            else:
                pdf_urls = []
                error_message = "No PDF URLs found"
                return pdf_urls, error_message
        except Exception as e:
            pdf_urls = []
            error_message = "No PDF URLs found"
            return pdf_urls, error_message
    if not pdf_urls and error_message is None:
        error_message = "No PDF URLs found"
    print(f"PDF URLs: {pdf_urls}")
    return pdf_urls, error_message
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
                type = await row.locator("//td").nth(0).text_content()
                if href:
                    full_url = url + href
                    tacoma_reports.append(f"{full_url},{type}")
                    print(full_url)
    except Exception as e:
        print(e)
    return tacoma_reports
async def King_report_lookup(page, url, address_line_1: str):
    error_message = None
    # url = "https://kingcounty.maps.arcgis.com/apps/instant/sidebar/index.html?appid=6c0bbaa4339c4ffab0c53cfe1f8d3d85"
    king_reports = []
    # try:
    #     await page.goto(url)
    # except Exception as e:
    #     pass
    address_input = page.get_by_role("searchbox", name="Search")
    await address_input.wait_for(state="visible", timeout=10000)
    # await page.wait_for_timeout(3000)
    await address_input.type(f"{address_line_1}\n")
    try:
        no_found = page.locator(f"//div[normalize-space()='There were no results found for \"{address_line_1}\".']")
        await no_found.wait_for(state="visible", timeout=5000)
        if await no_found.is_visible():
            error_message = f"There is no King County result found for {address_line_1}"
            king_reports = []
            print(error_message)
            return king_reports, error_message
    except Exception as e:
        pass
        # await page.wait_for_timeout(15000)
    link = page.locator("(//strong[normalize-space()='King County septic permitting records'])[1]")
    await link.wait_for(state="visible", timeout=20000)
    links = page.locator("//div[@class='esri-feature-content']")
    print(f"Links: {links}")
    # await links.wait_for(state="visible", timeout=15000)
    all_links = await links.all()
    for link in all_links:
        text = await link.inner_html()
        if "King County septic permitting records" in text:
            count = await link.locator("a").count()
            print(f"Found {count} links")
            for i in range(count):
                href = await link.locator("a").nth(i).get_attribute("href")
                king_reports.append(href)
            break
    return king_reports, error_message

async def Create_Customer(page, url, customer_data: dict):
    """Minimal create customer flow placeholder.
    Expects an authenticated FieldEdge session already present on 'page'.
    Currently, this function navigates to the dashboard and returns successfully.
    """
    try:
        
        # check it is login or logout , if logout then login
        def check_login(page):
        # full_address = f"{customer_data.get('address1') or ''} {customer_data.get('address2') or ''} {customer_data.get('city') or ''} {customer_data.get('state') or ''} {customer_data.get('zip') or ''}"
        # display_name = customer_data.get('displayName')
        # seach_input = page.locator("//input[@id='search']")
        # await seach_input.wait_for(state="visible", timeout=10000)
        # await seach_input.fill(full_address)
        # await seach_input.press("Enter")
        # try:
        #     no_record = page.locator("//div[normalize-space()='There are no active items entered']")
        #     try:
        #         await no_record.wait_for(state="visible", timeout=5000)
                
        #     except Exception:
        #         table_rows = page.locator("//table//tr")
        #         rows = await table_rows.all()
        #         print(f"Rows: {len(rows)}")
        #         if len(rows) > 1:
        #             for i in range(len(rows)-1):
                        
        #                 full_address_find = await page.locator(f"(//table//tr)[{i+2}]//td").nth(2).text_content()
        #                 print(f"Full address find: {full_address_find}")
        #                 # Normalize whitespace (including non-breaking), remove punctuation consistently for both strings
        #                 def normalize_address(s: str) -> str:
        #                     if not s:
        #                         return ''
        #                     # Unicode normalize to split combined characters and fix NBSP
        #                     s = unicodedata.normalize('NFKC', s)
        #                     # Replace all whitespace (space, tabs, NBSP, newlines) with single space, then remove spaces
        #                     s = re.sub(r"\s+", " ", s).strip()
        #                     s = s.replace('\xa0', ' ').replace('\u00A0', ' ').replace(' ', '')
        #                     # Remove common punctuation separators
        #                     s = re.sub(r"[-.,;]", "", s)
        #                     return s

        #                 full_address_find = normalize_address(full_address_find)
        #                 full_address = normalize_address(full_address)
        #                 print(full_address + "----" + full_address_find)
        #                 if full_address.lower() == full_address_find.lower():
        #                     display_name_find = await page.locator(f"(//table//tr)[{i+2}]//td").nth(0).text_content()
        #                     display_name_find = display_name_find.strip()
        #                     #if display_name_find is not None and display_name_find != "" and display_name_find == display_name.strip():
        #                     return "Already Exists", display_name_find
                            
        #                 else:
        #                     pass
        # except Exception:
        #     pass
        # # try:
        # #     customer_button = page.locator("//a//span[normalize-space()='Customers']")
        # #     await customer_button.wait_for(state="visible", timeout=10000)
        # #     await customer_button.click()
        # # except Exception:
        # #     customer_button = page.locator("//a[@class='customers']")
        # #     await customer_button.wait_for(state="visible", timeout=10000)
        # #     await customer_button.click()
        create_customer_button = page.locator("//div[@id='add-item-button-container']")
        await create_customer_button.wait_for(state="visible", timeout=10000)
        await create_customer_button.click()
        display_name = customer_data.get('displayName')
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
        except Exception:
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
            
        except Exception:
            try:
                await customer_already_exists.wait_for(state="visible", timeout=10000)
                if await customer_already_exists.is_visible():
                    return "Already Exists" , [display_name]
            except Exception:
                pass
            except Exception:
                # return "Creation Failed"
                Yes_button = page.locator("(//span[normalize-space()='Yes'])[2]")
                try:
                    await Yes_button.wait_for(state="visible", timeout=5000)
                    await Yes_button.click()
                except Exception:
                    pass

                customer_already_exists = page.locator("(//div[normalize-space()='Record Already Exists'])[1]")
                try:
                    await customer_already_exists.wait_for(state="visible", timeout=10000)
                    if await customer_already_exists.is_visible():
                        return "Already Exists" , [display_name]
                except Exception:
                    try:
                        Customer_created = page.locator("//div[@class='header-customer-title trim-text']")
                        await Customer_created.wait_for(state="visible", timeout=10000)
                        if await Customer_created.is_visible():
                            return "Created Successfully" , [display_name]
                    except Exception:

                        return "Creation Failed" , []
        return "Creation Failed" , []

        
    except Exception as e:
        # Surface the error back to caller
        raise e


async def Check_Existing_Customer(page, url, address_line_1: str):
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

# async def upload_files(page, url, file_links):
#     try:
#         for file_link in file_links:
#         # download the file from the file_link
