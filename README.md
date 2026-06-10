# Cars Discovery Parser Demo

Selenium/BeautifulSoup parser demo for discovering automotive makes and models.

## What it does

- Reads source pages from an input file.
- Uses Selenium to load pages.
- Parses loaded HTML with BeautifulSoup.
- Extracts make/model data.
- Saves structured output as JSON.

## Stack

- Python
- Selenium
- webdriver-manager
- BeautifulSoup

## Security cleanup

The original local script used `.env` and proxy settings. Public credentials were removed from this prepared version. Use `.env.example` if proxy configuration is needed.

## Run

```bash
pip install -r requirements.txt
python discovery_parser.py
```

## What I would improve

- Replace ad-hoc `.env` parsing with `python-dotenv`.
- Add clearer CLI arguments.
- Add logs and output validation.
- Add a smaller deterministic demo input.
