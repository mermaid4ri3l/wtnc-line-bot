import os
import time
import traceback
import requests
import cv2
import numpy as np
import re
import easyocr
import shutil
from datetime import datetime as dt
from tempfile import mkdtemp
from dotenv import load_dotenv
import subprocess

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# 載入 .env
load_dotenv()

def log(msg):
    timestamp = dt.now().strftime("[%Y-%m-%d %H:%M:%S]")
    message = f"{timestamp} {msg}"
    print(message)
    with open("WTNC_log.txt", "a", encoding="utf-8") as f:
        f.write(message + "\n")

def send_line_message(user_id, message):
    token = os.getenv("LINE_CHANNEL_TOKEN")
    if not token:
        log("❌ LINE_CHANNEL_TOKEN 不存在")
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    body = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}]
    }
    response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body)
    if response.status_code == 200:
        log("✅ 成功推播 LINE 訊息")
    else:
        log(f"❌ 發送失敗：{response.status_code} - {response.text}")

def solve_captcha_with_easyocr(captcha_path, debug=False):
    img = cv2.imread(captcha_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.bilateralFilter(gray, 11, 17, 17)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    if debug:
        cv2.imwrite(captcha_path.replace(".png", "_processed.png"), processed)

    reader = easyocr.Reader(['en'], gpu=False)
    result = reader.readtext(processed)
    log(f"🔍 OCR 所有結果：{result}")

    for _, text, _ in result:
        text_clean = text.replace(" ", "").replace("=", "").replace(",", "").strip()
        replacements = {'O': '0', 'o': '0', 'I': '1', 'l': '1', 'Z': '2', 'S': '5', 'B': '8', 'T': '7'}
        for wrong, right in replacements.items():
            text_clean = text_clean.replace(wrong, right)
        match = re.findall(r'\d+', text_clean)
        if len(match) == 2:
            fixed = f"{match[0]}+{match[1]}"
            log(f"✅ 強化後成功辨識並修正：{fixed}")
            return fixed
    return ""

def main():
    print("🟢 WTNC Bot 程式啟動")

    try:
        chromium_version = subprocess.check_output(["chromium", "--version"]).decode().strip()
        chromedriver_version = subprocess.check_output(["chromedriver", "--version"]).decode().strip()
        print("🔧 Chromium 版本：", chromium_version)
        print("🔧 Chromedriver 版本：", chromedriver_version)
    except Exception as e:
        print("⚠️ 無法取得版本：", e)

    CHROMIUM_PATH = shutil.which("chromium")
    CHROMEDRIVER_PATH = shutil.which("chromedriver")

    try:
        LOGIN_URL = 'https://admin.idelivery.com.tw/admin/auth/login'
        ACCOUNT = os.getenv("DM_ACCOUNT")
        PASSWORD = os.getenv("DM_PASSWORD")
        DEBUG = False
        DOWNLOAD_DIR = mkdtemp()

        options = Options()
        options.binary_location = CHROMIUM_PATH
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        prefs = {
            "download.default_directory": DOWNLOAD_DIR,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        options.add_experimental_option("prefs", prefs)

        driver = webdriver.Chrome(service=Service(), options=options)
        wait = WebDriverWait(driver, 20)
        driver.get(LOGIN_URL)

        for attempt in range(1, 16):
            log(f"\n🔄 第 {attempt} 次登入嘗試")
            try:
                captcha_element = wait.until(EC.presence_of_element_located((By.XPATH, '//img[contains(@class, "captcha")]')))
                captcha_path = os.path.join(DOWNLOAD_DIR, 'captcha.png')
                captcha_element.screenshot(captcha_path)
                captcha_text = solve_captcha_with_easyocr(captcha_path, DEBUG)
                if not captcha_text:
                    driver.refresh()
                    continue

                match = re.match(r"(\d+)\+(\d+)", captcha_text)
                if not match:
                    driver.refresh()
                    continue

                answer = int(match.group(1)) + int(match.group(2))

                username_input = driver.find_element(By.NAME, 'username')
                username_input.clear()
                username_input.send_keys(ACCOUNT)
                driver.find_element(By.NAME, 'password').send_keys(PASSWORD)
                driver.find_element(By.NAME, 'captcha').send_keys(str(answer))

                time.sleep(1)
                driver.find_element(By.XPATH, "//button[contains(text(), '登入')]").click()
                time.sleep(2)

                try:
                    wait.until(EC.presence_of_element_located((By.XPATH, '//span[text()="營業報表"]')))
                    log("✅ 登入成功")
                    break
                except:
                    try:
                        # 嘗試抓錯誤提示（常見 class）
                        error_element = driver.find_element(By.CLASS_NAME, "el-form-item__error")
                        log(f"❌ 登入錯誤提示：{error_element.text}")
                    except:
                        log("❔ 登入失敗，但抓不到錯誤提示")
                        html_preview = driver.page_source[:300].replace("\n", "")
                        log("📄 頁面快照（前300字）：\n" + html_preview)
                    driver.refresh()
                    continue

            except Exception as e:
                log(f"❌ 登入錯誤：{str(e)}")
                traceback.print_exc()
                driver.quit()
                return

        else:
            log("⛔ 所有登入失敗，結束")
            driver.quit()
            return

        # 登入成功後進入報表區
        wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='店家報表']"))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='營業報表']"))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='營業銷售報表']"))).click()
        time.sleep(2)

        net_element = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'priceArea') and contains(text(), '$')]")))
        net_value = net_element.text.strip().replace("$", "").replace(",", "")
        log(f"📊 銷售淨額：{net_value}")

        user_id = os.getenv("LINE_USER_ID")
        message = f"📢 {dt.now().strftime('%H:%M')} 業績回報: ${net_value}"
        send_line_message(user_id, message)

        driver.quit()
        log("🎉 完成任務")

    except Exception as e:
        log(f"❌ 發生錯誤：{str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
