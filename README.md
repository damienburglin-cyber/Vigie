# Vigie

Petite app web pour téléphone : prévient plusieurs jours à l'avance du gel (couper l'eau sous -10 °C), de la chaleur (quand fermer les volets, quand ouvrir) et des rafales de vent à Wolfersdorf (Haut-Rhin).

Prévisions : [Open-Meteo](https://open-meteo.com) (gratuit, sans clé).

- `src/template.html` + `src/ds.css` → `python3 src/build.py` → `index.html`
- Le dossier produit complet (règles de calcul, décisions) est dans la page, onglet Réglages.
