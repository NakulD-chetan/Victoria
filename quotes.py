import requests
from googletrans import Translator



def fetch_and_translate_quote():
    def fetch_random_quote():
        url = "https://api.quotable.io/random"
        response = requests.get(url)
        if response.status_code == 200:
            quote_data = response.json()
            return quote_data['content']
        else:
            return None

    def translate_to_hindi(text):
        translator = Translator()
        translation = translator.translate(text=text, src='en', dest='hi')
        return translation.text

    quote = fetch_random_quote()
    if quote:
        hindi_quote = translate_to_hindi(quote)
        return hindi_quote
    else:
        return "Error fetching quote."

if __name__ == "__main__":
    Quotes = fetch_and_translate_quote()
    print("Translated Quote in Hindi:", Quotes)
