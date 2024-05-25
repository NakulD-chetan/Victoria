import random

import requests
from loguru import logger


def get_bhg_slok(chapter, slok):
    url = f"https://bhagavadgitaapi.in/slok/{chapter}/{slok}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print("Failed to fetch data from API")
        return None

def get_slok_verse_data(chapter_number, slok_number):
    verse_data = get_bhg_slok(chapter_number, slok_number)
    if verse_data:

        return verse_data
    else:
        return None


def get_total_chapters():
    url = "https://bhagavadgitaapi.in/chapters"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        return len(data)
    else:
        print("Failed to fetch chapter data from API")
        return None



def get_total_slokas_in_chapter_with_name_summary(chapter_number):
    url = f"https://bhagavadgitaapi.in/chapter/{chapter_number}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        return data['verses_count'],data['meaning']['hi'],data['summary']['hi']
    else:
        print(f"Failed to fetch sloka data for chapter {chapter_number} from API")
        return None,None,None
# if verse_data:
#     print("Chapter:", verse_data["chapter"])
#     print("Verse:", verse_data["verse"])
#     print("Slok:", verse_data["slok"])
#     print("Transliteration:", verse_data["transliteration"])
#     print("Tej Commentary:", verse_data["chinmay"]["hc"])
#     # You can access other commentaries similarly, such as "siva", "purohit", etc.
# else:
#     print("Failed to retrieve verse data.")
def get_gita_slokh_with_name_summary():
    total_chapters_count= get_total_chapters()
    if total_chapters_count:
        random_chapter = random.randint(1, total_chapters_count)
        total_count_slokh_in_chapter, name_of_ch, summary_of_chapter = get_total_slokas_in_chapter_with_name_summary(random_chapter)
        random_slokh = random.randint(1, total_count_slokh_in_chapter)
        verse_data=get_slok_verse_data(random_chapter, random_slokh)
        logger.info("Random gita Slok succesfully fetched")

        return name_of_ch,summary_of_chapter,verse_data['slok'],verse_data['chinmay']['hc']

    else:
     logger.info("total_chapters_count is empty")
     return None,None,None

