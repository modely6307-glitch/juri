import os
import json
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from scraper import extract_data_with_llm, get_system_prompt

"""
排查腳本：針對特定案件進行抓取與 LLM 分析測試
"""

TARGET_URL = "https://judgment.judicial.gov.tw/FJUD/data.aspx?ty=JD&id=TNHV,113,%e9%87%8d%e5%8b%9e%e4%b8%8a,4,20241231,1"
CASE_TITLE = "臺灣高等法院 臺南分院 113 年度 重勞上 字第 4 號民事判決"

def debug_single_case():
    # 1. 初始化 Gemini
    api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyB0IXurOy5DMQcI0hW4lN-5m_Gf15iJ38s")
    genai.configure(api_key=api_key)
    
    print(f"🚀 Debugging Case: {CASE_TITLE}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        try:
            print(f"📡 Navigating to URL...")
            page.goto(TARGET_URL)
            
            # 抓取內容
            page.wait_for_selector(".text-pre", timeout=10000)
            elements = page.locator(".text-pre").all()
            
            if elements:
                candidates = [el.inner_text() for el in elements]
                raw_text = max(candidates, key=len)
                print(f"✅ Successfully grabbed text ({len(raw_text)} chars)")
            else:
                print("❌ Could not find .text-pre elements")
                return

            # 測試 LLM 提取
            print("🧠 Sending to LLM...")
            # 截取前 5000 字測試
            truncated_text = raw_text[:5000]
            ai_data = extract_data_with_llm(truncated_text)
            
            if ai_data:
                print("\n✨ Extraction Result:")
                print(json.dumps(ai_data, indent=2, ensure_ascii=False))
                
                if not isinstance(ai_data, dict):
                    print(f"⚠️ Warning: Expected dict, got {type(ai_data)}")
            else:
                print("❌ LLM returned None")

        except Exception as e:
            print(f"💥 Debug failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\nClosing browser in 5 seconds...")
            page.wait_for_timeout(5000)
            browser.close()

if __name__ == "__main__":
    debug_single_case()