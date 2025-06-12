def main():
    print("🟢 WTNC Bot 程式啟動")

    try:
        import subprocess
        chromium_version = subprocess.check_output(["chromium", "--version"]).decode().strip()
        print("🔧 Chromium 版本：", chromium_version)
        chromedriver_version = subprocess.check_output(["chromedriver", "--version"]).decode().strip()
        print("🔧 Chromedriver 版本：", chromedriver_version)
    except Exception as e:
        print("⚠️ 無法取得版本：", e)

    CHROMIUM_PATH = shutil.which("chromium")
    CHROMEDRIVER_PATH = shutil.which("chromedriver")
    print("🔍 chromium 在哪：", CHROMIUM_PATH)
    print("🔍 chromedriver 在哪：", CHROMEDRIVER_PATH)

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
                driver.find_element(By.NAME, 'username').send_keys(ACCOUNT)
                driver.find_element(By.NAME, 'password').send_keys(PASSWORD)
                driver.find_element(By.NAME, 'captcha').send_keys(str(answer))
                driver.find_element(By.XPATH, "//button[contains(text(), '登入')]").click()
                time.sleep(3)

                # 嘗試抓錯誤訊息
                try:
                    error_box = driver.find_element(By.CLASS_NAME, "el-message__content")
                    log(f"⚠️ 登入失敗訊息：{error_box.text}")
                except:
                    log("❔ 找不到錯誤訊息")

                if "dashboard" in driver.current_url or "overview" in driver.current_url:
                    try:
                        wait.until(EC.presence_of_element_located((By.XPATH, '//span[text()="營業報表"]')))
                        log("✅ 登入成功")
                        break
                    except:
                        log("❌ 登入後找不到預期頁面元素")
                        driver.refresh()
                        continue

                driver.refresh()

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
