#!/usr/bin/env python3
"""Vigie : notifications ntfy pour Wolfersdorf.

Lancé par GitHub Actions le matin et le soir. Applique les mêmes règles et les
mêmes seuils par défaut que l'app (voir #appSpec, sections 2 et 2 bis) et
envoie une notification ntfy quand il y a quelque chose à faire.

Deux sortes de messages :
- Anticipation : un épisode (gel, chaleur, vent) qui commence dans les 7 jours,
  envoyé une fois, puis de nouveau seulement s'il s'aggrave.
- Rappel du jour : le matin pour aujourd'hui (rafales, chaleur, eau, arrosage),
  le soir pour la nuit et demain (couper l'eau ce soir, fortes rafales demain).

Usage :
  python3 notify.py                 # envoie (NTFY_TOPIC requis)
  python3 notify.py --dry-run       # affiche sans envoyer
  python3 notify.py --test          # envoie une notification de test
  python3 notify.py --data f.json --now 2026-11-25T07:00 --dry-run
Stdlib uniquement.
"""
import argparse, datetime as dt, json, os, sys, urllib.request
from zoneinfo import ZoneInfo

LAT, LON = 47.639, 7.1127
TZ = ZoneInfo("Europe/Paris")
APP_URL = "https://damienburglin-cyber.github.io/Freeze/"
API = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
       "&hourly=temperature_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m"
       "&daily=precipitation_sum,et0_fao_evapotranspiration,sunrise&past_days=14"
       "&timezone=Europe%%2FParis&forecast_days=14") % (LAT, LON)

# Mêmes seuils par défaut que l'app (DEFAULTS dans src/template.html)
S = dict(cold=-5, cut=-10, hot=28, wave=33, fresh=22, wind=20, gust=40, strong=60, storm=80)
ANTICIPATE_DAYS = 7          # au-delà, l'app parle de tendance : pas de notification
PLANTS = [  # mêmes paramètres que PLANTS dans l'app
    dict(id="succ", name="plantes grasses", cap=25, kc=0.3, trigger=3, minGap=10, rainWait=3, morningOnly=True),
    dict(id="albizia", name="albizia", cap=60, kc=0.6, trigger=15, minGap=5, rainWait=8, morningOnly=False),
    dict(id="rest", name="pots et massifs", cap=20, kc=0.8, trigger=5, minGap=1, rainWait=4, morningOnly=False),
]
DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def d_of(s): return dt.date.fromisoformat(s)
def day_fr(s): d = d_of(s); return "%s %d %s" % (DAYS_FR[d.weekday()], d.day, MONTHS_FR[d.month - 1])
def wday(s): return DAYS_FR[d_of(s).weekday()]
def h(n): return "%d h" % n
def t_fr(v): return ("%.1f" % v).replace(".0", "").replace(".", ",") + " °C"
def r0(v): return int(round(v))


def span(hrs):
    if not hrs: return ""
    if len(hrs) >= 23: return "toute la journée"
    rs = []
    for x in hrs:
        if rs and x["h"] == rs[-1][1] + 1: rs[-1][1] = x["h"]
        else: rs.append([x["h"], x["h"]])
    return " et ".join("de %s à %s" % (h(a), "minuit" if b >= 23 else h(b + 1)) for a, b in rs)


def build_days(hourly, now):
    today = now.date().isoformat()
    days = {}
    for i, t in enumerate(hourly["time"]):
        date, hr = t[:10], int(t[11:13])
        if date < today or hourly["temperature_2m"][i] is None: continue
        days.setdefault(date, []).append(dict(h=hr, t=hourly["temperature_2m"][i], w=hourly["wind_speed_10m"][i],
                                              g=hourly["wind_gusts_10m"][i], past=(date == today and hr < now.hour)))
    out = []
    for date in sorted(days):
        hs = days[date]
        live = [x for x in hs if not x["past"]] or hs
        out.append(dict(date=date, hours=hs, live=live, tmin=min(x["t"] for x in live), tmax=max(x["t"] for x in live),
                        wmax=max(x["w"] for x in live), gmax=max(x["g"] for x in live)))
    for a, b in zip(out, out[1:]): a["next"] = b
    for d in out: d["alerts"] = eval_day(d)
    return out


def eval_day(d):
    out = []
    if d["tmin"] <= S["cold"]:
        lvl = 2 if d["tmin"] <= S["cut"] else 1
        below = [x for x in d["live"] if x["t"] <= (S["cut"] if lvl == 2 else S["cold"])]
        out.append(dict(fam="cold", lvl=lvl, value=d["tmin"], first=below[0]["h"], span=span(below)))
    if d["tmax"] >= S["hot"]:
        lvl = 2 if d["tmax"] >= S["wave"] else 1
        close = next((x for x in d["hours"] if 6 <= x["h"] <= 14 and x["t"] >= S["fresh"]), None)
        nxt = d.get("next")
        night = [x for x in d["hours"] if x["h"] >= 17] + ([dict(x, n=True) for x in nxt["hours"] if x["h"] < 12] if nxt else [])
        ev = next((x for x in night if x["t"] < S["fresh"] and (not x.get("n") or x["h"] <= 7)), None)
        out.append(dict(fam="heat", lvl=lvl, value=d["tmax"], close=close["h"] if close else None,
                        open=(ev["h"], bool(ev.get("n"))) if ev else None))
    if d["gmax"] >= S["gust"] or d["wmax"] >= S["wind"]:
        lvl = 3 if d["gmax"] >= S["storm"] else 2 if d["gmax"] >= S["strong"] else 1
        windy = [x for x in d["live"] if x["g"] >= S["gust"] or x["w"] >= S["wind"]]
        gusty = [x for x in d["live"] if x["g"] >= S["gust"]]
        peak = max(d["live"], key=lambda x: x["g"])
        out.append(dict(fam="wind", lvl=lvl, value=d["gmax"], peak=peak["h"], first=(gusty or windy)[0]["h"], span=span(windy)))
    return out


def episodes(days):
    eps = []
    for fam in ("cold", "heat", "wind"):
        cur = None
        for d in days:
            a = next((x for x in d["alerts"] if x["fam"] == fam), None)
            if a:
                if not cur:
                    cur = dict(fam=fam, days=[], lvl=0, value=a["value"]); eps.append(cur)
                cur["days"].append((d, a)); cur["lvl"] = max(cur["lvl"], a["lvl"])
                cur["value"] = min(cur["value"], a["value"]) if fam == "cold" else max(cur["value"], a["value"])
            else:
                cur = None
    for e in eps: e["start"] = e["days"][0][0]["date"]
    return eps


TITLES = dict(cold=["", "Grand froid", "Gel fort, couper l'eau"], heat=["", "Coup de chaud", "Canicule"],
              wind=["", "Vent", "Fortes rafales", "Tempête"])
TAGS = dict(cold="snowflake", heat="sunny", wind="dash", water="droplet")


def when_fr(date, today):
    n = (d_of(date) - today).days
    return "aujourd'hui" if n == 0 else "demain" if n == 1 else "après-demain" if n == 2 else "dans %d jours" % n


def anticipation(e, today, worse):
    d0 = e["start"]; n = (d_of(d0) - today).days
    unit = "km/h" if e["fam"] == "wind" else "°C"
    title = ("Ça s'aggrave : " if worse else "") + TITLES[e["fam"]][e["lvl"]] + " " + when_fr(d0, today)
    lines = []
    for d, a in e["days"][:3]:
        if a["fam"] == "cold": lines.append("%s : %s (sous %d °C %s)" % (day_fr(d["date"]), t_fr(a["value"]), S["cut"] if a["lvl"] == 2 else S["cold"], a["span"]))
        elif a["fam"] == "heat": lines.append("%s : %s" % (day_fr(d["date"]), t_fr(a["value"])))
        else: lines.append("%s : rafales %d km/h vers %s" % (day_fr(d["date"]), r0(a["value"]), h(a["peak"])))
    if len(e["days"]) > 3: lines.append("… %d jours en tout" % len(e["days"]))
    if e["fam"] == "cold" and e["lvl"] == 2:
        first = next(d for d, a in e["days"] if a["lvl"] == 2)
        eve = (d_of(first["date"]) - dt.timedelta(days=1))
        lines.append("Couper l'eau %s soir." % ("ce" if eve <= today else DAYS_FR[eve.weekday()]))
    if e["fam"] == "wind" and e["value"] >= S["gust"]: lines.append("Prévoir de rentrer la chatte.")
    conf = "fiable" if n <= 2 else "probable"
    lines.append("Fiabilité : %s. Pire valeur : %d %s." % (conf, r0(e["value"]), unit))
    prio = 4 if e["lvl"] >= 2 else 3
    return dict(title=title, body="\n".join(lines), tags=TAGS[e["fam"]], prio=prio)


def water_plan(pl, daily, today, watered):
    T = daily["time"]; rain = daily["precipitation_sum"]; et = daily["et0_fao_evapotranspiration"]
    ts = today.isoformat()
    if ts not in T: return None
    ti = T.index(ts); w = watered.get(pl["id"])
    si = T.index(w) if w in T else (ti if w and w > T[0] else 0)
    R = pl["cap"]
    for i in range(si, ti + 1):
        if not (w and i == T.index(w) if w in T else False):
            R = min(pl["cap"], R + (rain[i] or 0) - pl["kc"] * (et[i] or 0))
    gap = (today - d_of(w)).days if w else 99
    soon_rain = (rain[ti + 1] or 0) >= pl["rainWait"] if ti + 1 < len(rain) else False
    sr = daily["sunrise"][ti]; srh = int(sr[11:13]) + (1 if int(sr[14:16]) > 0 else 0)
    return dict(need=R <= pl["trigger"] and gap >= pl["minGap"] and not soon_rain, morning=max(5, srh))


def in_season(today):
    if os.environ.get("VIGIE_FORCE_SEASON"): return True   # tests
    md = today.strftime("%m-%d"); return "04-15" <= md <= "10-15"


def build_messages(data, now, state):
    today = now.date(); ts = today.isoformat(); morning = now.hour < 12
    days = build_days(data["hourly"], now)
    msgs = []
    sent = state.setdefault("sent", {}); known = state.setdefault("episodes", {})

    def once(key, msg):
        if key not in sent: sent[key] = ts; msgs.append(msg)

    # 1. Anticipation : épisodes qui commencent dans les 7 jours
    for e in episodes(days):
        n = (d_of(e["start"]) - today).days
        if n > ANTICIPATE_DAYS or n < 1: continue   # le jour même : rappels ci-dessous
        key = e["fam"] + ":" + e["start"]
        prev = known.get(key, 0)
        if e["lvl"] > prev:
            known[key] = e["lvl"]; msgs.append(anticipation(e, today, worse=prev > 0))

    by_date = {d["date"]: d for d in days}
    tdy = by_date.get(ts); tmw = by_date.get((today + dt.timedelta(days=1)).isoformat())

    def alert(d, fam): return next((a for a in d["alerts"] if a["fam"] == fam), None) if d else None

    if morning:
        a = alert(tdy, "cold")
        if a and a["lvl"] == 2:
            once(ts + ":cut", dict(title="Couper l'eau aujourd'hui", body="Sous %d °C %s (min %s)." % (S["cut"], a["span"], t_fr(a["value"])), tags="snowflake", prio=5))
        a = alert(tdy, "wind")
        if a and a["value"] >= S["gust"]:
            before = max(0, a["first"] - 1)
            once(ts + ":wind", dict(title="Rafales aujourd'hui : rentrer la chatte avant %s" % h(before),
                                    body="Rafales %d km/h vers %s, agité %s." % (r0(a["value"]), h(a["peak"]), a["span"]),
                                    tags="dash", prio=4 if a["lvl"] >= 2 else 3))
        a = alert(tdy, "heat")
        if a:
            parts = ["Fermer fenêtres et volets vers %s." % h(a["close"]) if a["close"] is not None else "Fermer fenêtres et volets dès maintenant."]
            if a["open"]: parts.append("Rouvrir dès %s%s." % (h(a["open"][0]), " (dans la nuit)" if a["open"][1] else ""))
            else: parts.append("Nuit chaude : garder fermé.")
            once(ts + ":heat", dict(title="%s aujourd'hui : %s" % (TITLES["heat"][a["lvl"]], t_fr(a["value"])), body=" ".join(parts), tags="sunny", prio=4 if a["lvl"] == 2 else 3))
        if in_season(today) and data.get("daily"):
            watered = state.setdefault("watered", {}); due = []
            for pl in PLANTS:
                p = water_plan(pl, data["daily"], today, watered)
                if p and p["need"]: due.append((pl, p)); watered[pl["id"]] = ts   # on suppose que le conseil est suivi
            if due:
                hour = due[0][1]["morning"]
                once(ts + ":water", dict(title="Arroser aujourd'hui : " + ", ".join(pl["name"] for pl, _ in due),
                                         body="Idéal entre %s et %s, au pied, sans mouiller les feuilles. Dans l'app, touche « Arrosé aujourd'hui »." % (h(hour), h(hour + 2)),
                                         tags="droplet", prio=3))
    else:
        # Soir : la nuit qui vient et demain
        night_cut = [x for x in (tdy["live"] if tdy else []) if x["h"] >= 18 and x["t"] <= S["cut"]]
        a = alert(tmw, "cold")
        if night_cut or (a and a["lvl"] == 2):
            low = min([x["t"] for x in night_cut] + ([a["value"]] if a and a["lvl"] == 2 else []))
            once(ts + ":cut-eve", dict(title="Ce soir : couper l'eau", body="Jusqu'à %s cette nuit ou demain (%s)." % (t_fr(low), a["span"] if a and a["lvl"] == 2 else "dès ce soir"), tags="snowflake", prio=5))
        a = alert(tmw, "wind")
        if a and a["value"] >= S["gust"]:
            once(ts + ":wind-eve", dict(title="Demain : rafales %d km/h, rentrer la chatte avant %s" % (r0(a["value"]), h(max(0, a["first"] - 1))),
                                        body="Pic vers %s, agité %s." % (h(a["peak"]), a["span"]), tags="dash", prio=4 if a["lvl"] >= 2 else 3))
    return msgs


def prune(state, today):
    lim = (today - dt.timedelta(days=21)).isoformat()
    state["sent"] = {k: v for k, v in state.get("sent", {}).items() if v >= lim}
    state["episodes"] = {k: v for k, v in state.get("episodes", {}).items() if k.split(":")[1] >= lim}


def send(topic, m):
    req = urllib.request.Request("https://ntfy.sh/" + topic, data=m["body"].encode("utf-8"), method="POST",
                                 headers={"Title": m["title"].encode("utf-8"), "Tags": m["tags"], "Priority": str(m["prio"]),
                                          "Click": APP_URL})
    urllib.request.urlopen(req, timeout=20).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--test", action="store_true")
    ap.add_argument("--data"); ap.add_argument("--now"); ap.add_argument("--state", default="state/vigie-state.json")
    o = ap.parse_args()
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not o.dry_run and not topic: sys.exit("NTFY_TOPIC manquant")
    if o.test:
        send(topic, dict(title="Vigie est branchée", body="Les alertes gel, chaleur, vent et arrosage arriveront ici, matin et soir. Touchez pour ouvrir l'app.", tags="white_check_mark", prio=3))
        print("test envoyé"); return
    now = dt.datetime.fromisoformat(o.now) if o.now else dt.datetime.now(TZ).replace(tzinfo=None)
    data = json.load(open(o.data)) if o.data else json.load(urllib.request.urlopen(API, timeout=30))
    try: state = json.load(open(o.state))
    except (OSError, ValueError): state = {}
    msgs = build_messages(data, now, state)
    prune(state, now.date())
    for m in msgs:
        print("—", m["title"], "|", m["body"].replace("\n", " / "), "| prio", m["prio"])
        if not o.dry_run: send(topic, m)
    if not msgs: print("rien à signaler (%s)" % now.strftime("%Y-%m-%d %H:%M"))
    os.makedirs(os.path.dirname(o.state) or ".", exist_ok=True)
    json.dump(state, open(o.state, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
