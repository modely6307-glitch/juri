import time
import random
import json
import pandas as pd
from playwright.sync_api import sync_playwright

def extract_data_with_llm(text):
    """
    Mock LLM extraction function.

    System Prompt:
    "You are a data extractor. Analyze this legal text. Identify the Plaintiff's (Worker) 'Job Title' (職稱) and 'Monthly Salary' (月薪). Return ONLY a JSON object: {'job_title': '...', 'monthly_salary': '...', 'currency': 'TWD'}. If not found, return null."
    """
    # In a real implementation, you would call an LLM API here.
    # For now, return a dummy object as requested.
    return {'job_title': 'PENDING_API_KEY', 'monthly_salary': 0, 'currency': 'TWD'}

def run():
    with sync_playwright() as p:
        # Launch Chromium with headless=False so the user can monitor it.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to target URL...")
        page.goto("https://judgment.judicial.gov.tw/FJUD/default.aspx")

        # Input keywords
        print("Inputting keywords...")
        page.fill("#txtKW", '"確認僱傭關係存在" "月薪"')

        # Click search button
        print("Clicking search...")
        page.click("#btnSimpleQry")

        # Wait for results table to load
        try:
            print("Waiting for results...")
            page.wait_for_selector("a[href*='data.aspx']", timeout=10000)
        except Exception as e:
            print(f"Error waiting for results: {e}")

        # Strategy: "Harvest then Visit"
        print("Extracting URLs...")
        links = page.locator("a[href*='data.aspx']").all()

        cases = []
        seen_urls = set()
        for link in links:
            href = link.get_attribute("href")
            text = link.inner_text().strip()

            if href:
                # Handle relative URLs
                if not href.startswith("http"):
                    href = "https://judgment.judicial.gov.tw/FJUD/" + href.lstrip('/')

                # Avoid duplicates
                if href not in seen_urls:
                    cases.append({"url": href, "case_id": text})
                    seen_urls.add(href)

        print(f"Found {len(cases)} judgments.")

        results = []

        # Extraction Loop
        for i, case in enumerate(cases):
            url = case["url"]
            case_id = case["case_id"]

            print(f"Processing {i+1}/{len(cases)}: {case_id}")
            try:
                page.goto(url)

                # Wait for content to load
                page.wait_for_selector("body", timeout=5000)

                content = ""
                # Selector Hint: .text-pre, div.col-td
                if page.locator(".text-pre").count() > 0:
                    content = page.locator(".text-pre").first.inner_text()
                elif page.locator("div.col-td").count() > 0:
                    content = page.locator("div.col-td").first.inner_text()
                else:
                    content = page.locator("form").first.inner_text()

                # Optimization: Truncate to first 4,000 characters
                truncated_text = content[:4000]

                # Mock LLM Extraction
                llm_data = extract_data_with_llm(truncated_text)

                # Metadata extraction (Date) - Simplified
                # Date is often in the text or separate column we missed during harvest.
                # For now, we leave it as Unknown or try to parse if easy.
                date_str = "Unknown"

                result = {
                    "Case_ID": case_id,
                    "Date": date_str,
                    "URL": url,
                    "Job_Title": llm_data.get('job_title'),
                    "Monthly_Salary": llm_data.get('monthly_salary')
                }
                results.append(result)

                # Rate Limiting
                sleep_time = random.uniform(2, 5)
                print(f"Sleeping for {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)

            except Exception as e:
                print(f"Error processing {url}: {e}")
                continue

        # Output to CSV
        print("Saving results to CSV...")
        if results:
            df = pd.DataFrame(results)
        else:
            df = pd.DataFrame(columns=["Case_ID", "Date", "URL", "Job_Title", "Monthly_Salary"])

        df.to_csv("labor_judgments.csv", index=False)
        print("Done.")

        browser.close()

if __name__ == "__main__":
    run()
