import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from issue_data import run_issue_extraction   # <-- Your full extractor file


# ---------------------------
# CHROME PATHS
# ---------------------------
chrome_binary_path = r"C:\Program Files (x86)\chrome-win64\chrome-win64\chrome.exe"
PATH = r"C:\Program Files (x86)\chromedriver.exe"


# ----------------------------------------------------
# Collect issue keys across ALL pagination pages
# ----------------------------------------------------
def collect_all_issue_keys(project):
    service = Service(PATH)
    options = webdriver.ChromeOptions()
    options.binary_location = chrome_binary_path
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(service=service, options=options)
    

    wait = WebDriverWait(driver, 15)

    collected = []

    # Use YOUR ORIGINAL URL (as requested)
    url = f"https://issues.apache.org/jira/projects/{project}/issues/{project}?filter=allissues"
    print("\nOpening:", url)
    driver.get(url)

    # --------------------------
    # Helper: extract issue keys
    # --------------------------
    def extract_keys_on_page():
        rows = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ol.issue-list li"))
        )

        keys_here = []
        for row in rows:
            key_text = row.find_element(By.CSS_SELECTOR, "span.issue-link-key").text.strip()
            href = row.find_element(By.CSS_SELECTOR, "a.splitview-issue-link").get_attribute("href")
            keys_here.append((key_text, href))

        return keys_here

    # --------------------------
    # Extract first page
    # --------------------------
    print("\nExtracting Page 1…")
    collected.extend(extract_keys_on_page())

    # --------------------------
    # Pagination loop
    # --------------------------
    page_num = 1
    while True:
        try:
            next_icon = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "a.nav-next .aui-iconfont-chevron-right")
                )
            )

            parent_link = next_icon.find_element(By.XPATH, "./..")

            page_num += 1
            print(f"\nClicking NEXT → Page {page_num}")

            driver.execute_script("arguments[0].click();", parent_link)
            time.sleep(1)

            collected.extend(extract_keys_on_page())

        except Exception:
            print("\nReached LAST page. Stopping pagination.\n")
            break

    driver.quit()
    return collected


# ----------------------------------------------------
# SCRAPE + EXTRACT DETAILS FOR EACH ISSUE
# ----------------------------------------------------
def scrape_full_project(project):
    print(f"\n================== {project}: Starting Scrape ==================\n")

    keys = collect_all_issue_keys(project)
    print(f"Total issues discovered: {len(keys)}\n")

    all_issue_objects = []

    for i, (key, url) in enumerate(keys, start=1):
        print(f"[{i}/{len(keys)}] Extracting → {key}")

        try:
            issue_obj = run_issue_extraction(url)
            all_issue_objects.append(issue_obj)
        except Exception as e:
            print(f"❌ Error extracting {key}: {e}")

    return all_issue_objects


# ----------------------------------------------------
# SAVE JSON
# ----------------------------------------------------
def save_as_json(project_key, issue_objects):
    os.makedirs("output", exist_ok=True)
    filepath = f"output/{project_key}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(issue_objects, f, indent=2, ensure_ascii=False)

    print(f"\n✔ JSON saved → {filepath}")


# ----------------------------------------------------
# SAVE JSONL
# ----------------------------------------------------
def save_as_jsonl(project_key, issue_objects):
    os.makedirs("output", exist_ok=True)
    filepath = f"output/{project_key}.jsonl"

    with open(filepath, "w", encoding="utf-8") as f:
        for obj in issue_objects:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"✔ JSONL saved → {filepath}")


# ----------------------------------------------------
# RUNNER — scrape ANY 3 projects
# ----------------------------------------------------
if __name__ == "__main__":
    project_list = ["ABDERA", "ACCUMULO", "AIRAVATA"]   # change these 3 if needed

    for project in project_list:
        print(f"\n\n==================== SCRAPING {project} ====================\n")

        data = scrape_full_project(project)

        save_as_json(project, data)
        save_as_jsonl(project, data)

    print("\n\nAll 3 projects scraped successfully!")
