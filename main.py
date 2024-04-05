import os
import concurrent.futures
import re
import time
from urllib.parse import urljoin
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from email_validator import validate_email
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

class MyBoxLayout(BoxLayout):
    def __init__(self, **kwargs):
        super(MyBoxLayout, self).__init__(**kwargs)

        # Add UI elements
        self.orientation = 'vertical'
        self.padding = [10, 10]
        self.spacing = 10

        self.intro_label = Label(text='Enter keywords to search (separated by commas):', size_hint_y=None, height=30)
        self.add_widget(self.intro_label)

        self.keyword_input = TextInput(multiline=False, size_hint_y=None, height=40)
        self.add_widget(self.keyword_input)

        self.search_button = Button(text='Search', size_hint_y=None, height=40)
        self.search_button.bind(on_press=self.search_keywords)
        self.add_widget(self.search_button)

        self.result_label = Label(text='', size_hint_y=None, height=30)
        self.add_widget(self.result_label)

    def search_keywords(self, instance):
        keywords = self.keyword_input.text.split(',')
        all_urls = set()
        for keyword in keywords:
            urls = google_search(keyword.strip())
            all_urls.update(urls)

        if all_urls:
            self.result_label.text = f"Top {len(all_urls)} relevant websites (domain name + TLD only) related to the keywords:"
            formatted_urls = '\n'.join([f"'https://{url}'," for url in all_urls])
            self.result_label.text += '\n' + formatted_urls
        else:
            self.result_label.text = "No relevant websites found."

        progress_bar = tqdm(total=len(all_urls), desc="Scraping Progress")
        scraped_links = set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(scrape_url, url): url for url in all_urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    link = future.result()
                    if link and link not in scraped_links:
                        scraped_links.add(link)
                except Exception as e:
                    print(f"Error scraping {url}: {e}")
                progress_bar.update(1)

        progress_bar.close()

        self.result_label.text += f"\nScraped {len(scraped_links)} unique 'Impressum' URLs:"
        formatted_impressum_urls = '\n'.join([f'"{url}",' for url in scraped_links])
        self.result_label.text += '\n' + formatted_impressum_urls

        valid_emails = []
        invalid_emails = []
        for url in scraped_links:
            valid, invalid = scrape_emails(url)
            valid_emails.extend(valid)
            invalid_emails.extend(invalid)

        self.result_label.text += "\nValid Emails:\n" + ",".join([f'"{email}"' for email in valid_emails])
        self.result_label.text += "\nInvalid Emails:\n" + ",".join([f'"{email}"' for email in invalid_emails])

        output_folder = input("Enter the path to the output folder: ")
        output_vcf_file = os.path.join(output_folder, "contacts.vcf")
        create_vcf(valid_emails, output_vcf_file)
        self.result_label.text += f"\nVCF file '{output_vcf_file}' has been created successfully."

def is_valid_url(url):
    domain_pattern = r"https?://([^/]+)/?$"
    match = re.match(domain_pattern, url)
    if match:
        return match.group(1)
    else:
        return None

def google_search(keyword, num_results=10):
    urls = set()
    try:
        driver = webdriver.Chrome()
        driver.get("https://www.google.com/search?q=" + keyword)

        for _ in range(30):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            try:
                load_more_button = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="botstuff"]/div/div[3]/div[4]/a[1]/h3/div/span[2]')))
                load_more_button.click()
                time.sleep(1)
            except:
                pass

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        for link in soup.find_all('div', class_='tF2Cxc'):
            url = link.find('a')['href']
            domain = is_valid_url(url)
            if domain:
                urls.add(domain)
                if len(urls) >= num_results:
                    break

        driver.quit()
        return urls
    except Exception as e:
        print("An error occurred during the search:", e)
        return set()

def scrape_url(url):
    scraped_link = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        if not url.startswith("https://"):
            url = "https://" + url

        with webdriver.Chrome(options=options) as driver:
            driver.get(url)
            driver.implicitly_wait(3)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            anchor_tags = soup.find_all('a')

            for tag in anchor_tags:
                if 'impressum' in tag.text.lower() or 'impressum' in tag.get('href', '').lower():
                    href = tag.get('href', '')
                    if href:
                        scraped_link = urljoin(url, href)
                        break
    except Exception as e:
        print(f"Error scraping {url}: {e}")

    return scraped_link

def scrape_emails(url):
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        # Initialize WebDriver for each URL
        with webdriver.Chrome(options=options) as driver:
            # Load the page
            driver.get(url)
            driver.implicitly_wait(2)  # Set implicit wait time for 2 seconds

            # Parse the HTML content
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Find all text nodes
            text_nodes = soup.find_all(string=True)

            # Initialize variables to store email
            found_email = None

            # Iterate through text nodes to find email
            for node in text_nodes:
                # Check if an email address is found
                email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', str(node))
                if email_match:
                    found_email = email_match.group()
                    break  # Stop searching after finding the first email

            # Return the found email (if any)
            if found_email:
                return [found_email], []
            else:
                return [], []
    except Exception as e:
        print(f"Error scraping emails from {url}: {e}")  # Log any exceptions that occur
        return [], []


def create_vcf(emails, output_file):
    with open(output_file, 'w') as vcf_file:
        for email in emails:
            vcf_file.write('BEGIN:VCARD\n')
            vcf_file.write(f'EMAIL;TYPE=INTERNET:{email}\n')
            vcf_file.write(f'FN:{email}\n')
            vcf_file.write('END:VCARD\n')

class MyApp(App):
    def build(self):
        return MyBoxLayout()

if __name__ == '__main__':
    MyApp().run()
