# Pages de test hors ligne : src/test-real.html (vraies prévisions) et src/test-synth.html (gel fort, rafales, canicule injectés).
import json, sys, pathlib, urllib.request
root = pathlib.Path(__file__).resolve().parent.parent
url = "https://api.open-meteo.com/v1/forecast?latitude=47.639&longitude=7.1127&hourly=temperature_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m&daily=precipitation_sum,et0_fao_evapotranspiration,sunrise&past_days=14&timezone=Europe%2FParis&forecast_days=14"
j = json.load(urllib.request.urlopen(url)); real = json.dumps(j); H = j["hourly"]
for i, t in enumerate(H["time"]):
    hr = int(t[11:13]); day = i // 24 - 14  # 14 jours passés en tête
    if day in (3, 4) and (hr >= 21 or hr <= 8): H["temperature_2m"][i] = -12 + abs(hr - 4) * 0.4
    if day == 6 and 11 <= hr <= 19: H["wind_gusts_10m"][i] = 55 + (hr == 15) * 20; H["wind_speed_10m"][i] = 28
    if day in (10, 11): H["temperature_2m"][i] = 16 + 18 * max(0, 1 - abs(hr - 16) / 10)
# Été simulé pour l'arrosage : sol qui sèche, une averse à J+5
D = j["daily"]
for k in range(len(D["time"])):
    D["et0_fao_evapotranspiration"][k] = 5.0
    D["precipitation_sum"][k] = 14.0 if k == 6 else (12.0 if k == 14 + 5 else 0.0)
src = (root / "index.html").read_text()
for name, data in (("test-real.html", real), ("test-synth.html", json.dumps(j))):
    stub = ("<script>window.VIGIE_FORCE_SEASON=true;</script>" if name == "test-synth.html" else "") + "<script>window.fetch=async()=>({ok:true,json:async()=>(%s)});</script>" % data
    (root / "src" / name).write_text(src.replace('<script type="text/markdown"', stub + '<script type="text/markdown"', 1))
print("tests ok")
