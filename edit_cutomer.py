import asyncio
from playwright.async_api import async_playwright

async def init_session(playwright):
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
            await page.locator("input[name='UserName']").fill("taylor@sterlingsepticandplumbing.com")
            await page.locator("input[name='Password']").fill("Advertising1!")
            await page.locator("input[type='submit'][value='Sign in to your account']").click()
    except Exception:
        pass
    try:
        await page.wait_for_url("**/Dashboard/**", timeout=15000)
    except Exception:
        pass
    return browser, context, page

async def run_edit_customer_pass(browser, context, page):
    # Go to customer list
    print("Navigating to Customer List...")
    try:
        await page.goto("https://login.fieldedge.com/#/List/1", wait_until="networkidle")
    except Exception as e:
        print(f"Error navigating to customer list: {e}")
    await asyncio.sleep(5)
    
    # Click custom view and intercept API
    print("Clicking custom view to intercept API...")
    entity_ids = set()
    try:
        async with page.expect_response(lambda response: "List/Get" in response.url and response.request.method == "POST", timeout=60000) as response_info:
            await page.locator('//div[@data-automation-id="disable-rec-filter-container"]').click()
            
        list_response = await response_info.value
        json_data = await list_response.json()
        
        records = []
        if isinstance(json_data, dict):
            if "data" in json_data: records = json_data["data"]
            elif "Data" in json_data: records = json_data["Data"]
        elif isinstance(json_data, list):
            records = json_data
            
        for record in records:
            if isinstance(record, dict) and record.get("EntityID"):
                entity_ids.add(str(record.get("EntityID")))
        print(f"Captured {len(entity_ids)} Entity IDs from first load.")
    except Exception as e:
        print(f"Error intercepting List/Get: {e}")
        return

    # Check row count
    try:
        actual_row_count_text = await page.locator("//div[@class='group-amount group-selected']").inner_text(timeout=5000)
        actual_row_count = int(actual_row_count_text.replace("(", "").replace(")", "").strip())
    except Exception as e:
        print(f"Could not get actual row count: {e}")
        actual_row_count = len(entity_ids)
        
    current_count = len(entity_ids)
    scroll_attempts = 0
    while current_count < actual_row_count and scroll_attempts < 50:
        scroll_attempts += 1
        print(f"Scrolling... ({current_count}/{actual_row_count})")
        
        rows = await page.locator("//tbody[@class='fixed-body']/tr").all()
        if not rows:
            break
        last_row = page.locator(f"(//tbody[@class='fixed-body']/tr)[{len(rows)}]")
        
        try:
            async with page.expect_response(lambda response: "List/Get" in response.url and response.request.method == "POST", timeout=20000) as response_info:
                await last_row.scroll_into_view_if_needed()
                
            list_response = await response_info.value
            json_data = await list_response.json()
            
            records = []
            if isinstance(json_data, dict):
                if "data" in json_data: records = json_data["data"]
                elif "Data" in json_data: records = json_data["Data"]
            elif isinstance(json_data, list):
                records = json_data
                
            for record in records:
                if isinstance(record, dict) and record.get("EntityID"):
                    entity_ids.add(str(record.get("EntityID")))
        except Exception as e:
            print("Scroll wait failed:", e)
            await last_row.scroll_into_view_if_needed()
            await asyncio.sleep(3)
            
        await asyncio.sleep(2)
        new_count = len(entity_ids)
        if new_count <= current_count:
            print("No new data after scrolling. Stopping.")
            break
        current_count = new_count
        
    print(f"Total Entity IDs captured: {len(entity_ids)}")
    
    for entity_id in entity_ids:
        print(f"Processing Customer {entity_id}...")
        cust_page = await context.new_page()
        try:
            try:
                await cust_page.goto(f"https://login.fieldedge.com/#/Customer/{entity_id}", wait_until="networkidle")
                await cust_page.wait_for_timeout(5000)
            except Exception as e:
                print(f"Error navigating to customer page: {e}")
            
            edit_btn = cust_page.locator("//span[normalize-space()='Edit Customer']")
            await edit_btn.wait_for(state="visible", timeout=15000)
            await edit_btn.click()
            await cust_page.wait_for_timeout(5000)
            
            call_rec_div = cust_page.locator('//div[@class="customer-contact-call-recording"]')
            await call_rec_div.wait_for(state="visible", timeout=15000)
            await call_rec_div.click()
            await cust_page.wait_for_timeout(1000)
            
            save_btn = cust_page.locator("//span[normalize-space()='Save']")
            await save_btn.click()
            await cust_page.wait_for_timeout(5000)
            
            print(f"✅ Customer {entity_id} edited successfully.")
            
        except Exception as e:
            print(f"⚠️ Failed to edit Customer {entity_id}: {e}")
        finally:
            await cust_page.close()
            
    print("Finished editing customers.")

async def run_edit_customer():
    async with async_playwright() as p:
        browser, context, page = await init_session(p)
        try:
            await run_edit_customer_pass(browser, context, page)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_edit_customer())
