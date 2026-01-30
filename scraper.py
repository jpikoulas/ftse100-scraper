#!/usr/bin/env python3
"""
FTSE 100 Stock Scraper
Fetches FTSE 100 constituents data and stores it in ClickHouse
"""

import os
import time
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import clickhouse_connect

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', '10.10.1.205')
CLICKHOUSE_PORT = int(os.getenv('CLICKHOUSE_PORT', '8123'))
CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER', 'default')
CLICKHOUSE_PASSWORD = os.getenv('CLICKHOUSE_PASSWORD', 'B---5')
CLICKHOUSE_DATABASE = os.getenv('CLICKHOUSE_DATABASE', 'default')

# LSE uses page parameter in URL
LSE_BASE_URL = "https://www.londonstockexchange.com/indices/ftse-100/constituents/table"


def create_driver():
    """Create a headless Chrome driver"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def parse_number(value):
    """Parse a number string, handling commas and percentages"""
    if not value or value == '-' or value == 'N/A' or value.strip() == '':
        return None
    value = value.replace(',', '').replace('%', '').strip()
    # Handle negative numbers in parentheses
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]
    try:
        return float(value)
    except ValueError:
        return None


def wait_for_table_update(driver, wait, previous_first_code=None):
    """Wait for the table to update with new data"""
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
            time.sleep(1)

            rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            if rows:
                cells = rows[0].find_elements(By.TAG_NAME, "td")
                if cells:
                    current_first_code = cells[0].text.strip()
                    if previous_first_code is None or current_first_code != previous_first_code:
                        return current_first_code

            time.sleep(0.5)
        except StaleElementReferenceException:
            time.sleep(0.5)
            continue

    return None


def scrape_current_page(driver):
    """Scrape the current page of stocks"""
    stocks = []

    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")

        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 5:
                    code = cells[0].text.strip()
                    name = cells[1].text.strip()

                    # Skip if no code or name
                    if not code or not name:
                        continue

                    stock = {
                        'code': code,
                        'name': name,
                        'currency': cells[2].text.strip() if len(cells) > 2 else 'GBX',
                        'market_cap': parse_number(cells[3].text) if len(cells) > 3 else None,
                        'price': parse_number(cells[4].text) if len(cells) > 4 else None,
                        'change': parse_number(cells[5].text) if len(cells) > 5 else None,
                        'change_pct': parse_number(cells[6].text) if len(cells) > 6 else None,
                        'scraped_at': datetime.utcnow()
                    }
                    stocks.append(stock)
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.debug(f"Error parsing row: {e}")
                continue

    except Exception as e:
        logger.warning(f"Error scraping page: {e}")

    return stocks


def click_next_page(driver, wait, current_page):
    """Click to go to the next page using various methods"""
    next_page = current_page + 1

    # Method 1: Try clicking the page number directly
    try:
        # Look for pagination buttons/links
        pagination_container = driver.find_elements(By.CSS_SELECTOR,
            "nav[aria-label*='pagination'], .pagination, [class*='paginator'], [class*='paging']")

        for container in pagination_container:
            # Try to find the next page number
            page_buttons = container.find_elements(By.XPATH,
                f".//*[contains(text(), '{next_page}') and (self::button or self::a or self::span)]")

            for btn in page_buttons:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", btn)
                    return True
    except Exception as e:
        logger.debug(f"Method 1 failed: {e}")

    # Method 2: Try finding next/forward button
    try:
        next_selectors = [
            "button[aria-label*='next' i]",
            "button[aria-label*='Next' i]",
            "a[aria-label*='next' i]",
            "[class*='next']",
            "[class*='forward']",
            "button:has(mat-icon:contains('chevron_right'))",
            "button:has(mat-icon:contains('arrow_forward'))",
        ]

        for selector in next_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    if elem.is_displayed() and elem.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", elem)
                        return True
            except:
                continue
    except Exception as e:
        logger.debug(f"Method 2 failed: {e}")

    # Method 3: Try using keyboard navigation or Angular-specific navigation
    try:
        # Find any clickable element that might be a next button using XPath
        next_elements = driver.find_elements(By.XPATH,
            "//*[contains(@class, 'next') or contains(@aria-label, 'next') or contains(@aria-label, 'Next')]")

        for elem in next_elements:
            if elem.is_displayed():
                driver.execute_script("arguments[0].click();", elem)
                return True
    except Exception as e:
        logger.debug(f"Method 3 failed: {e}")

    # Method 4: Try to find mat-paginator (Angular Material)
    try:
        paginator = driver.find_element(By.CSS_SELECTOR, "mat-paginator, [class*='mat-paginator']")
        next_btn = paginator.find_element(By.CSS_SELECTOR,
            "button[aria-label*='Next'], button.mat-paginator-navigation-next")
        if next_btn.is_enabled():
            driver.execute_script("arguments[0].click();", next_btn)
            return True
    except Exception as e:
        logger.debug(f"Method 4 failed: {e}")

    return False


def scrape_ftse100():
    """Scrape all FTSE 100 data from London Stock Exchange"""
    driver = create_driver()
    all_stocks = []
    seen_codes = set()
    wait = WebDriverWait(driver, 30)

    try:
        logger.info(f"Navigating to {LSE_BASE_URL}")
        driver.get(LSE_BASE_URL)

        # Accept cookies if present
        try:
            cookie_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "ccc-notify-accept")))
            cookie_btn.click()
            time.sleep(1)
        except:
            pass

        # Wait for initial table load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
        time.sleep(3)

        # Scrape pages
        max_pages = 6  # Safety limit
        current_page = 1
        previous_first_code = None
        consecutive_failures = 0

        while current_page <= max_pages and consecutive_failures < 3:
            logger.info(f"Scraping page {current_page}")

            # Wait for table to be ready
            first_code = wait_for_table_update(driver, wait, previous_first_code if current_page > 1 else None)

            if current_page > 1 and first_code == previous_first_code:
                logger.warning(f"Page didn't change, same first code: {first_code}")
                consecutive_failures += 1
                time.sleep(1)
                continue

            consecutive_failures = 0

            # Scrape current page
            page_stocks = scrape_current_page(driver)

            # Filter out duplicates
            new_stocks = []
            for stock in page_stocks:
                if stock['code'] not in seen_codes:
                    seen_codes.add(stock['code'])
                    new_stocks.append(stock)

            if new_stocks:
                all_stocks.extend(new_stocks)
                logger.info(f"Got {len(new_stocks)} new stocks from page {current_page} (total: {len(all_stocks)})")
            else:
                logger.warning(f"No new stocks found on page {current_page}")

            previous_first_code = first_code

            # Check if we have enough stocks (FTSE 100 = ~100 stocks)
            if len(all_stocks) >= 100:
                logger.info("Reached 100 stocks, stopping")
                break

            # Try to go to next page
            if current_page < max_pages:
                if click_next_page(driver, wait, current_page):
                    time.sleep(2)  # Wait for page transition
                else:
                    logger.warning(f"Could not navigate to page {current_page + 1}")
                    break

            current_page += 1

        logger.info(f"Successfully scraped {len(all_stocks)} stocks total")

    except TimeoutException:
        logger.error("Timeout waiting for page to load")
    except Exception as e:
        logger.error(f"Error scraping: {e}", exc_info=True)
    finally:
        driver.quit()

    return all_stocks


def init_clickhouse():
    """Initialize ClickHouse connection and create table if needed"""
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database=CLICKHOUSE_DATABASE
    )

    # Create table if not exists
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS ftse100_indexes (
        code String,
        name String,
        currency String,
        market_cap Nullable(Float64),
        price Nullable(Float64),
        change Nullable(Float64),
        change_pct Nullable(Float64),
        scraped_at DateTime
    ) ENGINE = MergeTree()
    ORDER BY (scraped_at, code)
    """

    client.command(create_table_sql)
    logger.info("ClickHouse table initialized")

    return client


def save_to_clickhouse(client, stocks):
    """Save stock data to ClickHouse"""
    if not stocks:
        logger.warning("No stocks to save")
        return

    # Prepare data for insertion
    data = [
        (
            s['code'],
            s['name'],
            s['currency'],
            s['market_cap'],
            s['price'],
            s['change'],
            s['change_pct'],
            s['scraped_at']
        )
        for s in stocks
    ]

    client.insert(
        'ftse100_indexes',
        data,
        column_names=['code', 'name', 'currency', 'market_cap', 'price', 'change', 'change_pct', 'scraped_at']
    )

    logger.info(f"Saved {len(stocks)} stocks to ClickHouse")


def main():
    """Main entry point"""
    logger.info("Starting FTSE 100 scraper")

    # Initialize ClickHouse
    client = init_clickhouse()

    # Scrape data
    stocks = scrape_ftse100()

    # Save to ClickHouse
    if stocks:
        save_to_clickhouse(client, stocks)
    else:
        logger.warning("No data scraped")

    logger.info("Scraper finished")


if __name__ == "__main__":
    main()
