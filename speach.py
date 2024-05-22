import requests


def convert_text_to_speech(text, voice_id, xi_api_key, output_file='output.mp3', model_id='eleven_monolingual_v1',
                           stability=0.5, similarity_boost=0.5):
    CHUNK_SIZE = 1024
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": xi_api_key
    }

    data = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code == 200:
        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        print("Text to speech conversion complete!")
        print("Output saved as:", output_file)
    else:
        print("Error:", response.text)


# Example usage:
text = "Born and raised in the charming south, I can add a touch of sweet southern hospitality to your audiobooks and podcasts"
voice_id = "<voice-id>"
xi_api_key = "<xi-api-key>"
output_file = "output.mp3"

