"""
google_maps_scraper.py
----------------------
Selenium-based scraper to find competitor businesses on Google Maps.
Searches for keyword in a given city/radius, extracts name/address/rating/URL.
Returns ~100 places for user approval before SWOT analysis.
"""

import time
import random
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import List, Dict

logger = logging.getLogger(__name__)


def init_driver():
    """Initialize headless Chrome driver with anti-bot detection measures."""
    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/chromium"
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--lang=en-US")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    
    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Hide webdriver flags
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )
    return driver


def search_google_maps_competitors(
    keyword: str,
    city: str,
    radius_km: float = 5,
    limit: int = 100,
    progress_callback=None
) -> List[Dict]:
    """
    Search Google Maps for competitors matching keyword in city + radius.
    
    Returns list of dicts:
    {
        "name": "Cafe Name",
        "address": "Street, City",
        "rating": 4.5,
        "reviews": 123,
        "url": "https://maps.google.com/...",
        "selected": True
    }
    
    progress_callback: function(current, total, status_text) — for progress updates
    """
    driver = None
    results = []
    
    try:
        driver = init_driver()
        
        # Build Google Maps search URL
        search_url = f"https://www.google.com/maps/search/{keyword}+in+{city}/@0,0,11z"
        logger.info(f"[SCRAPER] Searching: {search_url}")
        driver.get(search_url)
        
        # Wait for search results to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.XPATH, '//a[@data-item-id]'))
        )
        
        time.sleep(3)
        
        # Find the results list container
        try:
            results_container = driver.find_element(By.XPATH, '//div[@role="feed"]')
        except:
            results_container = driver.find_element(By.XPATH, '//*[@id="QA0Szd"]/div/div/div[1]/div[2]/div')
        
        extracted_places = set()
        stale_scroll_count = 0
        max_stale_attempts = 20
        
        while len(results) < limit and stale_scroll_count < max_stale_attempts:
            current_count = len(results)
            
            # Scroll down to load more results
            driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", results_container)
            time.sleep(random.uniform(1.5, 2.5))
            
            # Extract all visible place cards
            place_elements = driver.find_elements(By.XPATH, '//a[@data-item-id]')
            
            for elem in place_elements:
                if len(results) >= limit:
                    break
                
                try:
                    # Get place URL
                    place_url = elem.get_attribute("href") or ""
                    
                    # Create unique key
                    place_id = elem.get_attribute("data-item-id")
                    if place_id in extracted_places:
                        continue
                    extracted_places.add(place_id)
                    
                    # Extract place info from the element
                    place_card = elem.find_element(By.XPATH, './/div[contains(@class, "lI9Gke")]')
                    
                    # Name
                    try:
                        name = place_card.find_element(By.XPATH, './/div[@class="qBF1Pd"]').text
                    except:
                        name = "Unknown"
                    
                    # Address
                    try:
                        address = place_card.find_element(By.XPATH, './/div[@class="W4Efje"]').text
                    except:
                        address = "Address not available"
                    
                    # Rating
                    try:
                        rating_text = place_card.find_element(By.XPATH, './/span[@class="MW4etd"]').text
                        rating = float(rating_text.split()[0])
                    except:
                        rating = None
                    
                    # Number of reviews
                    try:
                        reviews_text = place_card.find_element(By.XPATH, './/span[@class="UY7F9"]').text
                        reviews_count = int(''.join(filter(str.isdigit, reviews_text)))
                    except:
                        reviews_count = 0
                    
                    place_data = {
                        "name": name,
                        "address": address,
                        "rating": rating,
                        "reviews": reviews_count,
                        "url": place_url,
                        "selected": True  # Default to selected, user can deselect
                    }
                    
                    results.append(place_data)
                    
                    if progress_callback:
                        progress_callback(len(results), limit, f"Found {len(results)} places...")
                    
                except Exception as e:
                    logger.warning(f"[SCRAPER] Error extracting place info: {e}")
                    continue
            
            if len(results) == current_count:
                stale_scroll_count += 1
            else:
                stale_scroll_count = 0
        
        logger.info(f"[SCRAPER] Finished. Found {len(results)} places")
        return results
        
    except Exception as e:
        logger.error(f"[SCRAPER] Fatal error: {e}")
        return results
        
    finally:
        if driver:
            driver.quit()