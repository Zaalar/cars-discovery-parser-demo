import time
print("⭐ Скрипт запускается, пожалуйста, подождите...")
import random
import os
import json
import zipfile
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
#  LOAD CONFIG FROM .env
# ─────────────────────────────────────────────
def load_env(env_path='.env'):
    config = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        except Exception as e:
            print(f"⚠️  Ошибка при чтении .env: {e}")
    return config

ENV_CONFIG = load_env()

# Script directory — all relative paths are resolved from here
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_FILE  = ENV_CONFIG.get('INPUT_FILE',  'Текстовый документ.txt')
OUTPUT_FILE = ENV_CONFIG.get('OUTPUT_FILE', 'makes_and_models.json')
CONCURRENCY = int(ENV_CONFIG.get('CONCURRENCY', 3))

MAKES_LIMIT = ENV_CONFIG.get('MAKES_LIMIT', 'None')
MAKES_LIMIT = None if MAKES_LIMIT.lower() == 'none' else int(MAKES_LIMIT)

PROXY_LIST_RAW = [p.strip() for p in ENV_CONFIG.get('PROXY_LIST', '').split(',') if p.strip()]
if not PROXY_LIST_RAW:
    PROXY_LIST_RAW = []  # Fill PROXY_LIST in .env if proxies are needed

# Resolve paths relative to script directory
INPUT_FILE  = os.path.join(SCRIPT_DIR, INPUT_FILE)
OUTPUT_FILE = os.path.join(SCRIPT_DIR, OUTPUT_FILE)

# ─────────────────────────────────────────────
#  CHROMEDRIVER SETUP
# ─────────────────────────────────────────────
try:
    DRIVER_PATH = ChromeDriverManager().install()
except Exception as e:
    print(f"⚠️  ChromeDriverManager: {e}. Falling back to chromedriver.exe")
    DRIVER_PATH = 'chromedriver.exe'

# ─────────────────────────────────────────────
#  PROXY EXTENSION BUILDER
# ─────────────────────────────────────────────
def create_proxy_extension(proxy_str: str, worker_id: int) -> str:
    """Пакует SOCKS5-прокси с авторизацией в zip-расширение Chrome."""
    ip, port, user, pwd = proxy_str.split(':')
    manifest = """{
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": ["proxy","tabs","unlimitedStorage","storage","<all_urls>","webRequest","webRequestBlocking"],
        "background": {"scripts": ["bg.js"]},
        "minimum_chrome_version": "22.0.0"
    }"""
    bg = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{scheme:"socks5", host:"{ip}", port:parseInt({port})}},
            bypassList: ["localhost"]
        }}
    }};
    chrome.proxy.settings.set({{value:config, scope:"regular"}}, function(){{}});
    chrome.webRequest.onAuthRequired.addListener(
        function(details){{ return {{authCredentials:{{username:"{user}",password:"{pwd}"}}}}; }},
        {{urls:["<all_urls>"]}}, ["blocking"]
    );
    """
    plugin_dir = os.path.join(SCRIPT_DIR, 'proxy_plugins')
    os.makedirs(plugin_dir, exist_ok=True)
    path = os.path.join(plugin_dir, f'plugin_{worker_id}.zip')
    with zipfile.ZipFile(path, 'w') as zp:
        zp.writestr('manifest.json', manifest)
        zp.writestr('bg.js', bg)
    return os.path.abspath(path)

# ─────────────────────────────────────────────
#  DRIVER FACTORY
# ─────────────────────────────────────────────
def get_driver(worker_id: int):
    proxy_str = random.choice(PROXY_LIST_RAW)
    plugin_path = create_proxy_extension(proxy_str, worker_id)
    opts = Options()
    opts.add_extension(plugin_path)
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=opts)
    driver.set_page_load_timeout(60)
    return driver, plugin_path

# ─────────────────────────────────────────────
#  PHASE 1 — EXTRACT MAKES FROM LOCAL HTML
# ─────────────────────────────────────────────
def extract_makes_from_local() -> list:
    """
    Reads the local Cars.com HTML snapshot and extracts all car makes
    from the embedded JSON inside <script id="CarsWeb.SearchController.index">.
    Returns a list of {"name": "...", "value": "..."} dicts.
    """
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Файл не найден: {INPUT_FILE}")
        return []

    content = ''
    for enc in ('utf-8', 'cp1251', 'utf-16'):
        try:
            with open(INPUT_FILE, 'r', encoding=enc) as f:
                content = f.read()
            print(f"📖 Файл прочитан в кодировке: {enc}")
            break
        except Exception:
            continue

    if not content:
        print("❌ Не удалось прочитать файл (проблема с кодировкой).")
        return []

    soup = BeautifulSoup(content, 'html.parser')

    # Primary: look for the JSON script tag
    tag = soup.find('script', {'type': 'application/json', 'id': 'CarsWeb.SearchController.index'})
    if not tag:
        tag = soup.find('script', id='CarsWeb.SearchController.index')

    if tag:
        try:
            data = json.loads(tag.string or tag.text)
            if data:
                return _parse_makes_from_srp_json(data)
        except Exception as e:
            print(f"⚠️  Ошибка разбора JSON из <script>: {e}")

    # Fallback: scrape makes from footer HTML links
    print("ℹ️  JSON-тег не найден или пуст. Пробую парсить марки из подвала страницы…")
    return _extract_makes_from_footer(soup)


def _parse_makes_from_srp_json(data: dict) -> list:
    """Извлекает марки из структуры srp_filters."""
    makes = []
    sections = data.get('srp_filters', {}).get('sections', [])
    for section in sections:
        for item in section.get('items', []):
            if item.get('listing_search_filter_input_key') == 'makes':
                opts_groups = item.get('listing_search_filter', {}).get('options', [])
                for group in opts_groups:
                    for opt in group.get('options', []):
                        if opt.get('value') and opt['value'] != 'all':
                            makes.append({'name': opt['name'], 'value': opt['value']})
    if makes:
        print(f"✅ Из JSON-фильтра извлечено {len(makes)} марок.")
    return makes


def _extract_makes_from_footer(soup: BeautifulSoup) -> list:
    """Парсит марки из HTML-ссылок подвала страницы."""
    makes = []
    seen = set()
    for a in soup.find_all('a', {'data-linkname': 'research-make'}):
        slug = (a.get('data-slugs') or '').strip()
        name = a.get_text(strip=True)
        if slug and name and slug not in seen:
            seen.add(slug)
            makes.append({'name': name, 'value': slug})
    print(f"✅ Из подвала страницы извлечено {len(makes)} марок.")
    return makes

# ─────────────────────────────────────────────
#  PHASE 2 — FETCH MODELS PER MAKE
# ─────────────────────────────────────────────
def get_models_for_make(make: dict, worker_id: int) -> tuple:
    """
    Visits https://www.cars.com/research/{make_value}/ and scrapes model names.
    Returns (make_name, list_of_model_names).
    """
    make_name  = make['name']
    make_value = make['value']
    print(f"🚀 [W{worker_id}] Загрузка моделей: {make_name}")

    driver = plugin_path = None
    models = []
    try:
        driver, plugin_path = get_driver(worker_id)
        url = f'https://www.cars.com/research/{make_value}/'
        driver.get(url)
        time.sleep(3)

        title = driver.title
        if 'Access Denied' in title or 'Cloudflare' in title or '403' in title:
            print(f"🛑 [W{worker_id}] Заблокировано для {make_name}: {title}")
            return make_name, []

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Method 1: links like /research/acura-mdx/ or /research/acura-mdx-2024/
        pattern = re.compile(rf'/research/{re.escape(make_value)}-([^/]+)/')
        seen = set()
        for a in soup.find_all('a', href=pattern):
            raw = a.get_text(strip=True)
            # Strip leading year tokens like "2024 " and the make name
            clean = re.sub(r'^\d{4}\s+', '', raw)
            clean = clean.replace(make_name, '').strip(' -–—')
            if clean and clean not in seen:
                seen.add(clean)
                models.append(clean)

        # Method 2: common CSS selectors used in research pages
        if not models:
            for el in soup.select('.mmy-model-name, .model-card h3, [data-linkname="model-year-select"]'):
                raw = el.get_text(strip=True)
                clean = re.sub(r'^\d{4}\s+', '', raw).replace(make_name, '').strip(' -–—')
                if clean and clean not in seen:
                    seen.add(clean)
                    models.append(clean)

        print(f"✅ [W{worker_id}] {make_name}: {len(models)} моделей")
    except Exception as exc:
        print(f"❌ [W{worker_id}] Ошибка для {make_name}: {exc}")
    finally:
        if driver:
            try: driver.quit()
            except: pass
        if plugin_path and os.path.exists(plugin_path):
            try: os.remove(plugin_path)
            except: pass

    return make_name, models

# ─────────────────────────────────────────────
#  SAVE RESULTS
# ─────────────────────────────────────────────
def save_to_json(data: dict):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"💾 JSON сохранён: {OUTPUT_FILE}")


def save_to_env(data: dict):
    """Appends MAKE_XXX=model1,model2,... lines to the .env file."""
    env_path = os.path.join(SCRIPT_DIR, '.env')
    base_lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '# --- SCRAPED DATA' in line:
                    break
                base_lines.append(line)

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(base_lines)
        f.write(f'\n# --- SCRAPED DATA ({time.strftime("%Y-%m-%d %H:%M:%S")}) ---\n')
        for make, models in data.items():
            key = 'MAKE_' + make.upper().replace(' ', '_').replace('-', '_')
            f.write(f'{key}={",".join(models)}\n')
    print(f"📊 Данные сохранены в .env (ключ-значение)")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    makes = extract_makes_from_local()
    if not makes:
        print("❌ Не удалось получить список марок. Выход.")
        return

    if MAKES_LIMIT:
        makes = makes[:MAKES_LIMIT]
        print(f"ℹ️  Лимит: обрабатываем {len(makes)} марок")

    print(f"📋 Всего марок для обработки: {len(makes)}")
    all_data = {}

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {}
        for i, make in enumerate(makes):
            wid = (i % CONCURRENCY) + 1
            fut = pool.submit(get_models_for_make, make, wid)
            futures[fut] = make['name']
            time.sleep(1.5)   # stagger launches slightly

        for fut in as_completed(futures):
            name, models = fut.result()
            if models:
                all_data[name] = models

    if not all_data:
        print("⚠️  Данные не получены. Проверьте прокси и доступ к сайту.")
        return

    save_to_json(all_data)
    save_to_env(all_data)

    # Cleanup proxy plugin directory
    plugin_dir = os.path.join(SCRIPT_DIR, 'proxy_plugins')
    if os.path.isdir(plugin_dir):
        import shutil
        try: shutil.rmtree(plugin_dir)
        except: pass

    print(f"\n🏁 Готово! Обработано марок: {len(all_data)}")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n🛑 Остановлено пользователем.')
    except Exception:
        import traceback
        print('\n💥 КРИТИЧЕСКАЯ ОШИБКА:')
        print(traceback.format_exc())
        input('Нажмите Enter для закрытия...')

