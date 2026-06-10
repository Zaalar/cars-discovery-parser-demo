import json
from bs4 import BeautifulSoup

file_path = 'Текстовый документ.txt'
content = open(file_path, encoding='utf-8').read()
soup = BeautifulSoup(content, 'html.parser')
tag = soup.find('script', {'type': 'application/json', 'id': 'CarsWeb.SearchController.index'})

if tag:
    data = json.loads(tag.string or tag.text)
    makes = []
    sections = data.get('srp_filters', {}).get('sections', [])
    for section in sections:
        for item in section.get('items', []):
            if item.get('listing_search_filter_input_key') == 'makes':
                for group in item['listing_search_filter']['options']:
                    for opt in group['options']:
                        if opt['value'] != 'all':
                            makes.append(opt)
    print(f'Found {len(makes)} makes')
    for m in makes[:10]:
        print(f'  {m["name"]} -> {m["value"]}')
    print('  ...')
else:
    print('Tag not found')
