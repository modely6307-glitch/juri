import time
import sys
import os
import random
import json
import requests
import pandas as pd
from playwright.sync_api import sync_playwright
import re
import google.generativeai as genai

# ==========================================
# 🛡️ 環境檢查
# ==========================================
if sys.version_info < (3, 9):
    print("❌ Error: This script requires Python 3.9 or higher due to 'google-generativeai' requirements.")
    print(f"   Current version: {sys.version}")
    sys.exit(1)

# ==========================================
# ⚙️ 系統設定區
# ==========================================

# 1. LLM 設定
LLM_PROVIDER = "ollama"  # 可選 "ollama" 或 "gemini"

# Ollama 設定
OLLAMA_BASE_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b"

# Gemini 設定
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB0IXurOy5DMQcI0hW4lN-5m_Gf15iJ38s")
GEMINI_MODEL = "gemini-2.0-flash"

# 2. 爬蟲設定
SEARCH_KEYWORDS = '確認僱傭關係存在 月薪'
MAX_CASES_TO_SCRAPE = 1000  # 設為 None 跑全部，或整數 (如 5) 測試
TEXT_TRUNCATE_LENGTH = 5000 # 給 LLM 的字數上限

# ==========================================
# 🤖 全域模型實例 (避免重複初始化)
# ==========================================
_gemini_model_instance = None

# ==========================================
# 🧠 AI 分析邏輯 (含 JSON 清洗)
# ==========================================

def get_system_prompt():
    return """你是一個專業的台灣法律資料分析師。請仔細閱讀傳入的判決書內容，並提取原告（勞方）的職位與薪資資訊。

請嚴格遵守以下規則：
1. **職稱 (job_title)**: 找出原告受僱的職位名稱（例如：工程師、業務經理、司機）。若判決書中未提及具體職稱，請改為提取被告（雇主/公司）的名稱。
2. **月薪 (monthly_salary)**: 找出雙方「約定」或法院「認定」的每月薪資數額（請轉換為純數字，不含逗號）。若有爭議，優先採用法院認定金額。
3. **格式**: 必須只回傳一個標準的 JSON 物件。
4. **缺失處理**: 如果找不到相關資訊，該欄位請填 null。

JSON 範例格式：
{
  "job_title": "軟體工程師",
  "monthly_salary": 50000,
  "currency": "TWD"
}
"""

def clean_json_string(text):
    """
    清洗 LLM 回傳的字串，移除 Markdown 標記，只保留 JSON 部分
    """
    if not text:
        return None
    try:
        # 嘗試直接解析
        return json.loads(text)
    except:
        # 如果失敗，嘗試用 Regex 抓取 { ... }
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        return None

def extract_data_with_llm(text):
    """呼叫 LLM 進行語意分析 (效能優化版)"""
    global _gemini_model_instance
    current_model = OLLAMA_MODEL if LLM_PROVIDER == "ollama" else GEMINI_MODEL
    print(f"      [LLM] Analyzing text ({len(text)} chars) using {LLM_PROVIDER} ({current_model})...")
    
    # 如果內容太短 (例如抓錯了)，直接跳過不浪費算力
    if len(text) < 100:
        print("      ⚠️ Text too short, skipping LLM analysis.")
        return None

    try:
        if LLM_PROVIDER == "ollama":
            payload = {
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": get_system_prompt()},
                    {"role": "user", "content": text}
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "num_ctx": 6144,      
                    "num_batch": 2048,    
                    "num_predict": 512,   
                    "temperature": 0.1,   
                    "num_thread": 8       
                }
            }
            
            response = requests.post(OLLAMA_BASE_URL, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            content = result['message']['content']

        elif LLM_PROVIDER == "gemini":
            if _gemini_model_instance is None:
                if not hasattr(genai, "GenerativeModel"):
                    print(f"      ❌ Error: Your 'google-generativeai' version is too old.")
                    print(f"         Detected version: {getattr(genai, '__version__', 'unknown')}")
                    print(f"         Requirement: Version 0.3.0+ and Python 3.9+ are required.")
                    return None
                _gemini_model_instance = genai.GenerativeModel(
                    model_name=GEMINI_MODEL,
                    system_instruction=get_system_prompt()
                )
            
            try:
                response = _gemini_model_instance.generate_content(
                    text,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                if not response.candidates or not response.candidates[0].content.parts:
                    print("      ⚠️ Gemini blocked the response (Safety filters) or returned empty content.")
                    return None
                content = response.text
            except ValueError:
                print("      ⚠️ Gemini blocked the response due to safety filters.")
                return None

        else:
            print(f"      ❌ Unknown LLM Provider: {LLM_PROVIDER}")
            return None
        
        # 使用清洗函式解析 JSON
        parsed_data = clean_json_string(content)
        
        # 處理 LLM 回傳 List 的情況 (常見於某些模型的 JSON 模式)
        if isinstance(parsed_data, list) and len(parsed_data) > 0:
            parsed_data = parsed_data[0]
            
        if parsed_data is None:
            print(f"      ⚠️ Failed to parse JSON. Raw output: {content[:50]}...")
            
        return parsed_data
        
    except Exception as e:
        print(f"      [Error] LLM extraction failed: {e}")
        return None

# ==========================================
# 🕸️ 爬蟲主程式 (Scraper)
# ==========================================

def run():
    current_model = OLLAMA_MODEL if LLM_PROVIDER == "ollama" else GEMINI_MODEL
    print(f"🚀 Starting Scraper on M4 Pro | Backend: {LLM_PROVIDER.upper()}")
    print(f"   Model: {current_model}")
    
    # Initialize Gemini once if needed
    if LLM_PROVIDER == "gemini":
        if not GEMINI_API_KEY or "YOUR_KEY" in GEMINI_API_KEY:
            print("❌ Error: GEMINI_API_KEY not set. Please set it as an environment variable.")
            return
        genai.configure(api_key=GEMINI_API_KEY)
        
        print("🔍 Checking available Gemini models...")
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            print("   Available models:")
            for m_name in available_models:
                print(f"    - {m_name}")
        except Exception as e:
            print(f"   ⚠️ Could not list models: {e}")

    csv_filename = "labor_judgments_final.csv"
    results = []
    seen_urls = set()

    # 1. 讀取現有檔案以避免重複爬取
    if os.path.exists(csv_filename):
        print(f"📂 Loading existing data from {csv_filename}...")
        try:
            existing_df = pd.read_csv(csv_filename)
            results = existing_df.to_dict('records')
            seen_urls = set(existing_df['URL'].dropna().tolist())
            print(f"   ✅ Loaded {len(results)} existing records.")
        except Exception as e:
            print(f"   ⚠️ Could not load existing file: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        main_page = context.new_page()
        print("1. [Main] Navigating to Judicial Yuan...")
        main_page.goto("https://judgment.judicial.gov.tw/FJUD/default.aspx")

        print(f"2. [Main] Searching for: {SEARCH_KEYWORDS}")
        main_page.fill("#txtKW", SEARCH_KEYWORDS)
        main_page.click("#btnSimpleQry")

        print("3. [Main] Waiting for results (scanning iframes)...")
        main_page.wait_for_timeout(5000)

        # 尋找正確的 Iframe
        target_frame = None
        for frame in main_page.frames:
            try:
                if frame.locator("a[href*='data.aspx']").count() > 0:
                    print(f"   ✅ Found results in frame: '{frame.name}'")
                    target_frame = frame
                    break
            except:
                continue

        if not target_frame:
            print("   ❌ Error: Could not find any frame with judgment links. Exiting.")
            browser.close()
            return

        page_num = 1

        while True:
            if MAX_CASES_TO_SCRAPE and len(results) >= MAX_CASES_TO_SCRAPE:
                break

            print(f"\n--- 📄 Processing Page {page_num} ---")
            
            # 重新尋找 Iframe (確保翻頁後仍能抓到內容)
            target_frame = None
            for frame in main_page.frames:
                try:
                    if frame.locator("a[href*='data.aspx']").count() > 0:
                        target_frame = frame
                        break
                except:
                    continue

            if not target_frame:
                print("   ❌ Error: Could not find results frame. Ending.")
                break

            # 抓取當前頁面的案件連結
            links = target_frame.locator("a[href*='data.aspx']").all()
            page_tasks = []
            for link in links:
                href = link.get_attribute("href")
                title = link.inner_text().strip()
                if href and title:
                    if not href.startswith("http"):
                        href = "https://judgment.judicial.gov.tw/FJUD/" + href
                    if href not in seen_urls:
                        page_tasks.append({"url": href, "title": title})
                        seen_urls.add(href)

            if not links:
                print("   ⚠️ No links found on this page. Ending.")
                break

            if not page_tasks:
                print("   ⏭️ All cases on this page already processed. Skipping to next page...")

            # 處理當前頁面的案件
            for task in page_tasks:
                if MAX_CASES_TO_SCRAPE and len(results) >= MAX_CASES_TO_SCRAPE:
                    break

                print(f"\n[{len(results)+1}] Processing: {task['title']}")
                detail_page = context.new_page()
                
                try:
                    detail_page.goto(task['url'])
                    
                    # --- 🔧 關鍵修正：智慧內容抓取 ---
                    # 1. 抓取頁面上 "所有" 的 .text-pre 元素
                    try:
                        detail_page.wait_for_selector(".text-pre", timeout=8000)
                        elements = detail_page.locator(".text-pre").all()
                        
                        # 2. 找出 "字數最多" 的那一個 (這才是真正的判決書)
                        if elements:
                            candidates = [el.inner_text() for el in elements]
                            raw_text = max(candidates, key=len) # 選最長的
                            
                            # 如果最長的還是很短，可能 selector 沒抓對，嘗試抓 body
                            if len(raw_text) < 100:
                                print("      ⚠️ .text-pre content too short, falling back to body...")
                                raw_text = detail_page.locator("body").inner_text()
                        else:
                            raise Exception("No elements found")
                            
                    except Exception as wait_err:
                        print(f"      ⚠️ Text selector issue ({wait_err}), falling back to body text...")
                        raw_text = detail_page.locator("body").inner_text()

                    # 截取文字
                    truncated_text = raw_text[:TEXT_TRUNCATE_LENGTH]
                    
                    # 呼叫 LLM
                    ai_data = extract_data_with_llm(truncated_text)
                    
                    if ai_data:
                        job = ai_data.get('job_title')
                        salary = ai_data.get('monthly_salary')
                        print(f"      ✅ Extracted: {job} / ${salary}")
                        
                        results.append({
                            "Case_ID": task['title'],
                            "URL": task['url'],
                            "Job_Title": job,
                            "Monthly_Salary": salary,
                            "Raw_JSON": json.dumps(ai_data, ensure_ascii=False)
                        })
                        
                        # 每爬完一筆就存檔，避免程式中斷導致資料遺失
                        pd.DataFrame(results).to_csv(csv_filename, index=False, encoding="utf-8-sig")
                        
                    else:
                        print("      ⚠️ AI returned null data.")

                except Exception as e:
                    print(f"      ❌ Error processing case: {e}")
                
                finally:
                    detail_page.close()
                
                    sleep_time = random.uniform(2, 4)
                    time.sleep(sleep_time)

            # --- 翻頁邏輯 ---
            next_button = target_frame.locator("#hlNext")
            if next_button.count() > 0 and (not MAX_CASES_TO_SCRAPE or len(results) < MAX_CASES_TO_SCRAPE):
                print(f"\n➡️ Page {page_num} finished. Clicking 'Next Page'...")
                next_button.first.click()
                main_page.wait_for_timeout(5000) # 等待 iframe 內容更新
                page_num += 1
            else:
                print("\n🏁 No more pages or limit reached.")
                break

        browser.close()

    if results:
        df = pd.DataFrame(results)
        df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
        print(f"\n🎉 Done! Saved {len(results)} rows to {csv_filename}")
    else:
        print("\n⚠️ No data extracted.")

if __name__ == "__main__":
    run()