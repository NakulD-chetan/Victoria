import requests

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




# if verse_data:
#     print("Chapter:", verse_data["chapter"])
#     print("Verse:", verse_data["verse"])
#     print("Slok:", verse_data["slok"])
#     print("Transliteration:", verse_data["transliteration"])
#     print("Tej Commentary:", verse_data["chinmay"]["hc"])
#     # You can access other commentaries similarly, such as "siva", "purohit", etc.
# else:
#     print("Failed to retrieve verse data.")
