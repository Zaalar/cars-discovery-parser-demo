# Cars Discovery Parser

Парсер для сбора марок и моделей автомобилей.

## Что делает

- читает исходные страницы из файла;
- открывает страницы через Selenium;
- разбирает HTML через BeautifulSoup;
- достает марки и модели;
- сохраняет результат в JSON.

## Стек

- Python
- Selenium
- webdriver-manager
- BeautifulSoup

## Настройка

Если нужны прокси или другие параметры запуска, их можно указать в `.env` по примеру `.env.example`.

## Запуск

```bash
pip install -r requirements.txt
python discovery_parser.py
```

## Что показывает проект

Проект показывает работу с Selenium, HTML-разбором и сохранением результата в структурированный файл.
