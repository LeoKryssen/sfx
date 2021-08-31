import urllib.parse

from .voices import voices


class SpeedConverters:
    Naver = {
        0: 5,
        1: 4,
        2: 3,
        3: 2,
        4: 1,
        5: 0,
        6: -1,
        7: -2,
        8: -3,
        9: -4,
        10: -5,
    }
    # easily extendable for more voices that support speed options


def _split_text(voice: str, text: str):
    """
    Input: voice: str, text: str
    Output: list of str
    """
    limit = voices[voice]["limit"]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _convert_speed(voice: str, config_speed: int):
    """
    Input: voice: str, config_speed: int
    Output: config_speed: int
    """
    provider = voices[voice]["provider"]
    if provider == "naver":
        return SpeedConverters.Naver[config_speed]
    return int(config_speed)


def generate_urls(voice: str, text: str, speed: int):
    """
    Input: voice: str, text: str, speed: int
    Output: list of str (urls)
    """
    texts = _split_text(voice, text)
    url = voices[voice]["url"]
    speed_bool = voices[voice]["speed"]
    urls = []
    for segment in texts:
        if speed_bool:
            url.replace("{speed}", _convert_speed(voice, speed))
        url.replace("{text}", urllib.parse.quote(segment))
        urls.append(url)
    return urls
