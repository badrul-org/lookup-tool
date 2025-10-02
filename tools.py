from playwright.async_api import async_playwright
import asyncio


class LookupTool:
    def __init__(self, file_lock=None):
        self.playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.file_lock = file_lock or asyncio.Lock()
        # self.county = "King"
    
    async def open_browser(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)  # Set headless=True to run without GUI
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
    
    async def close_browser(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    async def tax_rate_lookup(self, address_line_1: str, city: str, zip: str):
        try:
            tax_rate_url = "https://webgis.dor.wa.gov/taxratelookup/SalesTax.aspx"
            await self.page.goto(tax_rate_url)
            input_street_address = self.page.locator("//input[@id='txtAddr']")
            await input_street_address.wait_for(state="visible", timeout=10000)
            await input_street_address.fill(address_line_1)
            input_city = self.page.locator("//input[@id='txtCity']")
            await input_city.wait_for(state="visible", timeout=10000)
            await input_city.fill(city)
            input_zip = self.page.locator("//input[@id='txtZip']")
            await input_zip.wait_for(state="visible", timeout=10000)
            await input_zip.fill(zip)
            await self.page.locator("//input[@id='imgAdrSrc']").click()
            await self.page.wait_for_timeout(5000)
            table_rows = self.page.locator("//div[@id='tblSales']//tr")
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
    async def address_search(self, street_number: str, street_name: str, county: str):
        try:
            await self.page.goto("https://www.onlinerme.com/contractorsearchproperty.aspx", timeout=15000)
        except Exception as e:
            print(e)
            await self.page.goto("https://www.onlinerme.com/contractorsearchproperty.aspx", timeout=15000)
        # Wait for the county dropdown to be visible and have options populated
        county_dropdown = self.page.locator("select#drpCounty[name='drpCounty']")
        await county_dropdown.wait_for(state="visible")
        await self.page.locator("#drpCounty option").first.wait_for(state="attached")

        # Resolve the correct option value by matching visible text that starts with "Pierce"
        option_locators = await self.page.locator("#drpCounty option").all()
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
        
        await self.page.locator("//input[@id='txtStreetNumber']").fill(street_number)
        await self.page.locator("//input[@id='txtSearch']").fill(street_name)
        await self.page.locator("//input[@id='chkExactMatch']").click()
        await self.page.wait_for_timeout(1000)
        await self.page.locator("//input[@id='btnSearch']").click()
        await self.page.wait_for_timeout(10000)
        no_record = self.page.locator("//span[@id='lblMultiMatch']")
        if await no_record.is_visible():
            await self.page.locator("//input[@id='chkExactMatch']").click()
            await self.page.wait_for_timeout(1000)
            await self.page.locator("//input[@id='btnSearch']").click()
            await self.page.wait_for_timeout(10000)

    async def get_report_pdf(self):
        pdf_urls = []
        header = self.page.locator("//div[@id='HeaderContainer']")
        if await header.is_visible(timeout=5000):
            service_history = self.page.locator("//div[contains(text(),'Service History')]")
            await service_history.wait_for(state="visible")
            await service_history.click()
            await self.page.wait_for_timeout(10000)
            first_row = self.page.locator("(//tr[@valign='top'])[1]")
            if await first_row.is_visible(timeout=5000):
                # get the report 
                row = self.page.locator("(//tr[@valign='top'])")
                rows = await row.all()
                count = len(rows)
                print(f"Count: {count}")
                pdf_urls = []
                # if  :
                for i , row in enumerate(rows):
                    # collect latest 3 pdfs
                    if i < 3:
                        # row_number = row.locator("(//td)[1]").text_content()
                        image_input = row.locator("(//td//input[@type='image'])[1]")
                        # open iframe in new tab
                        # async with self.page.expect_popup() as popup_info:
                        await image_input.click()
                        # await self.page.wait_for_timeout(10000)
                        # new_tab = await popup_info.value

                        # print("New tab URL:", new_tab.url)
                        # await self.page.wait_for_timeout(10000)
                        # download the pdf from iframe 
                        try:
                            iframe = self.page.locator("//iframe")
                            await iframe.wait_for(state="visible", timeout=10000)
                            pdf_url = await self.page.locator("iframe").get_attribute("src")
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
                            pdf_urls.append(full_pdf_url)
                                
                            await self.page.go_back()
                            await self.page.wait_for_timeout(5000)
                            
                        except Exception as e:
                            print(f"Error downloading PDF: {e}")
                            # Try to go back even if there was an error
                            try:
                                await self.page.go_back()
                                await self.page.wait_for_timeout(5000)
                            except:
                                pass
                            continue
        print(f"PDF URLs: {pdf_urls}")
        return pdf_urls
    async def Tacoma_report_lookup(self, address_line_1: str):
        url = "https://edocs.tpchd.org/"
        tacoma_reports = []
        try:
            await self.page.goto(url)
        except Exception as e:
            pass
        address_input = self.page.locator("//input[@id='TextBox1']")
        await address_input.wait_for(state="visible", timeout=10000)
        await address_input.fill(address_line_1)
        await self.page.locator("//input[@id='Button1']").click()
        # await self.page.wait_for_timeout(10000)
        report_table = self.page.locator("//table[@id='GridView1']")
        try:
            await report_table.wait_for(state="visible", timeout=5000)
            if await report_table.is_visible():
                rows = await self.page.locator("//table[@id='GridView1']//tr").all()
                # start from 2nd row
                rows = rows[1:]
                for row in rows:
                    # last data have the link
                    href = await row.locator("//td").last.locator("//a").get_attribute("href")
                    if href:
                        full_url = url + href
                        tacoma_reports.append(full_url)
                        print(full_url)
        except Exception as e:
            print(e)
        
        return tacoma_reports
async def main():
    # User input
    address_line_1 = input("Enter the Address Line 1: ")
    street_number = address_line_1.split(" ")[0]
    street_name = address_line_1.split(" ")[1]
    City = input("Enter the City name: ")
    State_name = ("Enter The state/province name: ")
    Zip_code = input("Enter The zip/postal code: ")
    county = input("Enter the county: ")
    county = county.strip()
    # frist letter of county to uppercase
    county = county.capitalize()
    lookup_tool = LookupTool()
    await lookup_tool.open_browser()
    await lookup_tool.address_search(street_number, street_name, county)
    await lookup_tool.get_report_pdf()
    location_code = await lookup_tool.tax_rate_lookup(address_line_1, City, Zip_code)
    print(f"Location Code: {location_code}")
    # # if county == "Pierce":
    # if True:
    #     await lookup_tool.Tacoma_report_lookup("6124 Alameda")
    # await lookup_tool.close_browser()

if __name__ == "__main__":
    asyncio.run(main())