# Pages de test hors ligne (non versionnées, src/test-*.html) :
# - test-real : vraies prévisions et vraie météo actuelle ;
# - test-synth : gel fort, rafales, canicule injectés, été simulé pour l'arrosage, neige faible actuelle ;
# - test-<ambiance> : une heure et une météo de l'instant forcées (VIGIE_FORCE_NOW + current), pour voir chaque ambiance.
import copy, datetime, json, pathlib, urllib.request
root = pathlib.Path(__file__).resolve().parent.parent
url = "https://api.open-meteo.com/v1/forecast?latitude=47.639&longitude=7.1127&hourly=temperature_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m,weather_code,precipitation&daily=precipitation_sum,et0_fao_evapotranspiration,sunrise,sunset&past_days=14&timezone=Europe%2FParis&forecast_days=14&current=temperature_2m,apparent_temperature,weather_code,cloud_cover,precipitation,rain,showers,snowfall,wind_speed_10m,wind_gusts_10m,is_day"
j = json.load(urllib.request.urlopen(url))
src = (root / "index.html").read_text()

def write(name, data, pre=""):
    stub = pre + "<script>window.fetch=async()=>({ok:true,json:async()=>(%s)});</script>" % json.dumps(data)
    (root / "src" / name).write_text(src.replace('<script type="text/markdown"', stub + '<script type="text/markdown"', 1))

write("test-real.html", j)

# --- Synthèse : alertes et arrosage ---
s = copy.deepcopy(j); H = s["hourly"]
s["current"] = {"time": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"), "interval": 900, "temperature_2m": -1.0, "apparent_temperature": -5.2,
                "weather_code": 71, "cloud_cover": 100, "precipitation": 0.3, "rain": 0.0, "showers": 0.0, "snowfall": 0.21,
                "wind_speed_10m": 14.0, "wind_gusts_10m": 28.0, "is_day": 1}
for i, t in enumerate(H["time"]):
    hr = int(t[11:13]); day = i // 24 - 14  # 14 jours passés en tête
    if day in (3, 4) and (hr >= 21 or hr <= 8): H["temperature_2m"][i] = -12 + abs(hr - 4) * 0.4
    if day == 6 and 11 <= hr <= 19: H["wind_gusts_10m"][i] = 55 + (hr == 15) * 20; H["wind_speed_10m"][i] = 28
    if day in (10, 11): H["temperature_2m"][i] = 16 + 18 * max(0, 1 - abs(hr - 16) / 10)
D = s["daily"]
for k in range(len(D["time"])):
    D["et0_fao_evapotranspiration"][k] = 5.0
    D["precipitation_sum"][k] = 14.0 if k == 6 else (12.0 if k == 14 + 5 else 0.0)
write("test-synth.html", s, "<script>window.VIGIE_FORCE_SEASON=true;</script>")

# --- Ambiances : heure forcée + météo de l'instant + quelques heures injectées pour « prochaines heures » ---
today = datetime.date.today().isoformat()
ti = j["daily"]["time"].index(today)
rise = datetime.datetime.fromisoformat(j["daily"]["sunrise"][ti]); sset = datetime.datetime.fromisoformat(j["daily"]["sunset"][ti])

def amb(name, now, cur, hours=None):
    a = copy.deepcopy(j); now_s = now.strftime("%Y-%m-%dT%H:%M")
    a["current"] = dict({"time": now_s, "interval": 900, "apparent_temperature": cur.get("temperature_2m", 5) - 3, "cloud_cover": 50,
                         "precipitation": 0.0, "rain": 0.0, "showers": 0.0, "snowfall": 0.0, "wind_speed_10m": 8.0, "wind_gusts_10m": 15.0}, **cur)
    Hh = a["hourly"]; i0 = Hh["time"].index(now.strftime("%Y-%m-%dT%H:00"))
    for off, vals in (hours or {}).items():
        for k, v in vals.items(): Hh[k][i0 + off] = v
    write("test-" + name + ".html", a, "<script>window.VIGIE_FORCE_NOW=%s;</script>" % json.dumps(now_s))

at = lambda h, m=0: datetime.datetime.fromisoformat(today + "T%02d:%02d" % (h, m))
def mg(*ds):
    out = {}
    for d in ds:
        for k, v in d.items(): out.setdefault(k, {}).update(v)
    return out
dry = {k: {"precipitation": 0.0, "weather_code": 1} for k in range(1, 13)}
amb("dawn", rise - datetime.timedelta(minutes=20), {"temperature_2m": -3.0, "weather_code": 0, "is_day": 0}, dry)
amb("dusk", sset - datetime.timedelta(minutes=25), {"temperature_2m": 6.0, "weather_code": 2, "is_day": 1},
    mg(dry, {k: {"temperature_2m": -0.5} for k in range(5, 13)}))
amb("night", at(22), {"temperature_2m": 3.0, "weather_code": 0, "is_day": 0}, mg(dry, {4: {"temperature_2m": -0.4}}))
amb("sun", at(12, 30), {"temperature_2m": 9.0, "weather_code": 0, "is_day": 1},
    mg(dry, {k: {"wind_gusts_10m": 48 + k} for k in range(4, 9)}))
amb("hot", at(15), {"temperature_2m": 33.0, "weather_code": 0, "is_day": 1, "wind_gusts_10m": 12.0},
    {k: {"temperature_2m": 33 - k, "precipitation": 0.0, "weather_code": 1, "wind_gusts_10m": 12} for k in range(1, 13)})
amb("rain", at(10), {"temperature_2m": 7.0, "weather_code": 63, "precipitation": 1.4, "is_day": 1},
    mg({k: {"precipitation": 1.2, "weather_code": 63} for k in range(1, 4)}, {k: {"precipitation": 0.0, "weather_code": 3} for k in range(4, 13)}))
amb("storm", at(16), {"temperature_2m": 12.0, "weather_code": 95, "precipitation": 4.0, "is_day": 1, "wind_gusts_10m": 72.0},
    mg({k: {"precipitation": 3.0, "weather_code": 95, "wind_gusts_10m": 70} for k in range(1, 3)},
         {k: {"precipitation": 0.0, "weather_code": 3, "wind_gusts_10m": 25} for k in range(3, 13)}))
amb("snow", at(9), {"temperature_2m": -4.0, "weather_code": 73, "precipitation": 0.8, "snowfall": 0.6, "is_day": 1, "wind_gusts_10m": 44.0},
    {k: {"precipitation": 0.6, "weather_code": 73, "temperature_2m": -4 + k * 0.5, "wind_gusts_10m": 44 - k * 3} for k in range(1, 13)})
amb("fog", at(8, 30), {"temperature_2m": 1.0, "weather_code": 45, "is_day": 1}, dry)
print("tests ok")
