import requests
import json
config = ""
with open("config.json","r") as config_file:
    config = json.load(config_file)

session = requests.session()
cookies = {
    'XSRF-TOKEN':f"{config['xsrf']}",
    'hellcase_session':f"{config['session']}"
}

session.cookies.update(cookies)

url = "https://api.hellcase.com/open/newbie"
response = session.get(url)
try:
    data = response.json()
    print(data.get("status"), data.get("casename"), data.get("case_is_opened"), data.get("need_refill"))
except ValueError:
    print(response.status_code)
