import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import time

class WebCrawlerTester:
    def __init__(self, base_url, max_pages=100, delay=1.0):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.max_pages = max_pages
        self.delay = delay
        self.visited_urls = set()
        self.site_map_data = {}

    def is_valid_url(self, url):
        """Ensure the URL stays within the target domain and is a web page."""
        parsed = urlparse(url)
        if parsed.netloc != self.domain or parsed.scheme not in ['http', 'https']:
            return False
        if any(parsed.path.endswith(ext) for ext in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.mp4', '.css', '.js']):
            return False
        return True

    def extract_forms(self, soup, url):
        """Extract all forms, input fields, constraints, and attributes for automation testing."""
        forms_data = []
        forms = soup.find_all('form')
        
        for idx, form in enumerate(forms):
            form_info = {
                "form_index": idx,
                "action": urljoin(url, form.get('action', '')),
                "method": form.get('method', 'get').lower(),
                "inputs": []
            }
            
            for field in form.find_all(['input', 'textarea', 'select']):
                field_type = field.get('type', 'text') if field.name == 'input' else field.name
                
                input_meta = {
                    "name": field.get('name', ''),
                    "type": field_type,
                    "id": field.get('id', ''),
                    "required": field.has_attr('required'),
                    "maxlength": field.get('maxlength', None),
                    "minlength": field.get('minlength', None),
                    "max": field.get('max', None),
                    "min": field.get('min', None),
                    "placeholder": field.get('placeholder', '')
                }
                
                if field.name == 'select':
                    input_meta["options"] = [opt.get('value', opt.text.strip()) for opt in field.find_all('option')]
                
                form_info["inputs"].append(input_meta)
                
            forms_data.append(form_info)
        return forms_data

    def crawl(self, current_url=None):
        """Recursively crawl the site up to max_pages."""
        if current_url is None:
            current_url = self.base_url

        if len(self.visited_urls) >= self.max_pages:
            return

        current_url = urlparse(current_url)._replace(fragment="").geturl()
        
        if current_url in self.visited_urls:
            return

        print(f"[{len(self.visited_urls) + 1}] Crawling: {current_url}")
        self.visited_urls.add(current_url)
        time.sleep(self.delay)

        try:
            response = requests.get(current_url, timeout=10, headers={"User-Agent": "AutomationTestCrawler/1.0"})
            if response.status_code != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
                return
            
            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = soup.title.string.strip() if soup.title else "No Title"
            forms = self.extract_forms(soup, current_url)
            
            self.site_map_data[current_url] = {
                "title": page_title,
                "forms_found": len(forms),
                "forms": forms,
                "discovered_links": []
            }

            for a_tag in soup.find_all('a', href=True):
                absolute_link = urljoin(current_url, a_tag['href'])
                if self.is_valid_url(absolute_link):
                    self.site_map_data[current_url]["discovered_links"].append(absolute_link)
                    self.crawl(absolute_link)

        except Exception as e:
            print(f"Error crawling {current_url}: {e}")

    def save_results(self, filename="sitemap_automation_spec.json"):
        """Save the extracted blueprint structure into a JSON file."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.site_map_data, f, indent=4, ensure_ascii=False)
        print(f"\n[✔] Done! Map saved to {filename}")

if __name__ == "__main__":
    # Change this URL to your application's target link
    TARGET_URL = "https://sports.punjab.gov.in/" 
    
    crawler = WebCrawlerTester(TARGET_URL, max_pages=20, delay=1.0)
    crawler.crawl()
    crawler.save_results()
