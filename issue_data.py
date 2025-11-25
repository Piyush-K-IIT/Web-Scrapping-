from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

chrome_binary_path = r"C:\Program Files (x86)\chrome-win64\chrome-win64\chrome.exe"
PATH = r"C:\Program Files (x86)\chromedriver.exe"


# --------------------------------------------------
# Helper: safe extraction
# --------------------------------------------------
def safe_text(driver, selector):
    try:
        return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
    except:
        return None


# --------------------------------------------------
# Extract: metadata block
# --------------------------------------------------
def extract_metadata(driver):
    return {
        "type": safe_text(driver, "#type-val"),
        "status": safe_text(driver, "#status-val"),
        "priority": safe_text(driver, "#priority-val"),
        "resolution": safe_text(driver, "#resolution-val"),
        "affects_versions": safe_text(driver, "#versions-val"),
        "fix_versions": safe_text(driver, "#fixfor-val"),
        "labels": safe_text(driver, "div#wrap-labels .labels"),
        "environment": safe_text(driver, "#environment-val"),
    }


# --------------------------------------------------
# Extract: reporter, assignee, votes, watchers
# --------------------------------------------------
def extract_people(driver):
    return {
        "assignee": safe_text(driver, "#assignee-val"),
        "reporter": safe_text(driver, "#reporter-val"),
        "votes": safe_text(driver, "#vote-data"),
        "watchers": safe_text(driver, "#watcher-data"),
    }


def extract_dates(driver):
    def safe_text(selector):
        try:
            return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
        except:
            return None

    def safe_attr(selector, attr):
        try:
            return driver.find_element(By.CSS_SELECTOR, selector).get_attribute(attr)
        except:
            return None

    return {
        "created_display": safe_text("#created-val time"),
        "created_iso": safe_attr("#created-val time", "datetime"),
        "updated_display": safe_text("#updated-val time"),
        "updated_iso": safe_attr("#updated-val time", "datetime"),
    }


def extract_description(driver):
    wait = WebDriverWait(driver, 10)

    try:
        # Wait for the description block
        desc_blocks = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "div#descriptionmodule div.user-content-block")
            )
        )
    except:
        return None

    # Combine text from all description paragraphs
    description_text = []

    for block in desc_blocks:
        description_text.append(block.text.strip())

    # Join paragraphs with line breaks
    return "\n\n".join(description_text)

def extract_issue_links(driver):
    wait = WebDriverWait(driver, 10)

    try:
        links_container = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.links-container")
            )
        )
    except:
        return []   # No links module present

    link_data = []

    # Each <dl> contains one category like "Blocked", "Relates", etc.
    link_groups = links_container.find_elements(By.CSS_SELECTOR, "dl.links-list")

    for group in link_groups:
        try:
            relationship_type = group.find_element(By.CSS_SELECTOR, "dt").text.strip()
        except:
            relationship_type = None

        # Each <dd> holds one linked issue
        dd_items = group.find_elements(By.CSS_SELECTOR, "dd")

        for dd in dd_items:
            try:
                issue_key_el = dd.find_element(By.CSS_SELECTOR, "a.issue-link")
                issue_key = issue_key_el.text.strip()
                issue_url = issue_key_el.get_attribute("href")
            except:
                issue_key = None
                issue_url = None

            # Summary
            try:
                summary = dd.find_element(By.CSS_SELECTOR, "span.link-summary").text.strip()
            except:
                summary = None

            # Priority icon alt/title
            try:
                priority_img = dd.find_element(By.CSS_SELECTOR, "ul.link-snapshot li.priority img")
                priority = priority_img.get_attribute("title")
            except:
                priority = None

            # Status text
            try:
                status = dd.find_element(By.CSS_SELECTOR, "ul.link-snapshot li.status span").text.strip()
            except:
                status = None

            link_data.append({
                "type": relationship_type,
                "key": issue_key,
                "url": issue_url,
                "summary": summary,
                "priority": priority,
                "status": status,
            })

    return link_data

def extract_comments(driver):
    wait = WebDriverWait(driver, 10)

    # ----------------------------
    # STEP 1 — Click "Comments" tab
    # ----------------------------
    try:
        comments_tab = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "li#comment-tabpanel a")
            )
        )
        driver.execute_script("arguments[0].click();", comments_tab)
    except:
        return []   # No comments tab or cannot click

    # Wait for comments panel to load
    wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#issue_actions_container")
        )
    )

    container = driver.find_element(By.CSS_SELECTOR, "#issue_actions_container")

    # If no comments
    if "There are no comments" in container.text:
        return []

    # ----------------------------
    # STEP 2 — Extract comment items
    # ----------------------------
    comment_items = container.find_elements(
        By.CSS_SELECTOR, "div.activity-item.activity-comment"
    )

    comments = []

    for item in comment_items:
        # Author
        try:
            author = item.find_element(By.CSS_SELECTOR, ".action-details .user-hover").text.strip()
        except:
            author = None

        # Timestamp
        try:
            time_tag = item.find_element(By.CSS_SELECTOR, ".action-details time")
            display_time = time_tag.text.strip()
            iso_time = time_tag.get_attribute("datetime")
        except:
            display_time = None
            iso_time = None

        # Comment body text
        try:
            comment_text = item.find_element(By.CSS_SELECTOR, ".comment-body").text.strip()
        except:
            comment_text = None

        comments.append({
            "author": author,
            "display_time": display_time,
            "iso_time": iso_time,
            "text": comment_text
        })

    return comments

def extract_summary(driver):
    def safe_text(selector):
        try:
            return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
        except:
            return None

    # Issue key (ABDERA-695)
    issue_key = safe_text("#key-val")

    # Issue title/summary
    summary = safe_text("#summary-val")

    return {
        "issue_key": issue_key,
        "issue_summary": summary
    }


# --------------------------------------------------
# MAIN EXTRACTION METHOD
# --------------------------------------------------
def run_issue_extraction(issue_url):
    service = Service(PATH)
    options = webdriver.ChromeOptions()
    options.binary_location = chrome_binary_path
    options.add_argument("--headless")

    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 15)

    print("Opening issue:", issue_url)
    driver.get(issue_url)

    # Wait for metadata to load
    wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "ul#issuedetails.property-list")
    ))

    # Run extraction functions
    summary = extract_summary(driver)
    metadata = extract_metadata(driver)
    people = extract_people(driver)
    dates = extract_dates(driver)
    description = extract_description(driver)
    issue_links = extract_issue_links(driver)
    comments = extract_comments(driver)


    # Close browser
    driver.quit()

    # Return a combined dict
    return {
        "summary": summary,
        "metadata": metadata,
        "people": people,
        "dates": dates,
        "description": description,
        "issue_links": issue_links,
        "comments": comments
    }


