# Guide pas à pas : pipeline de prix PokeWorth (dépôt GitHub)

Durée : environ 30 minutes la première fois. Coût : 0 euro (GitHub Actions gratuit pour un dépôt public).

## 1. Structure du dépôt

```
pokeworth-prices/
├── build_feed.py          agrégation quotidienne -> prices.json
├── blend.py               mélange pondéré, rejet des valeurs aberrantes, lissage
├── cardmarket_source.py   price guide Cardmarket + association des produits
├── market_sources.py      TCGplayer (tcgcsv.com) et eBay.fr (annonces)
├── ebay_sold.py           eBay.fr, ventes réalisées (accès Marketplace Insights)
├── fr_filter.py           filtre « versions françaises uniquement »
├── backfill_history.py    reconstitution de l'historique (une fois)
├── cardmarket_map.json    associations manuelles produit -> idProduct
├── items_pokemon_fr.json  catalogue (copie de PokeWorth/Resources/)
├── requirements.txt       dépendances (py7zr, uniquement pour backfill_history.py)
├── test_*.py              tests hors réseau
└── .github/workflows/
    ├── update-prices.yml      tâche quotidienne (cron 04 h 17 UTC)
    └── backfill-history.yml   historique, lancement manuel
```

## 2. Créer le dépôt et envoyer les fichiers
1. github.com ▸ **New repository** ▸ nom `pokeworth-prices`, **Public**, sans README.
2. **uploading an existing file** : glissez tous les fichiers de ce dossier (sauf `.github`, créé à l'étape suivante).
3. **Add file ▸ Create new file** : tapez `.github/workflows/update-prices.yml`, collez le contenu de `update-prices.yml`, validez.
   Recommencez avec `.github/workflows/backfill-history.yml`.
4. **Settings ▸ Actions ▸ General ▸ Workflow permissions** : *Read and write permissions* ▸ Save.

## 3. Clés d'API
| Source | Clé | Où l'obtenir |
|---|---|---|
| Cardmarket (price guide) | aucune | fichiers publics |
| TCGplayer (via tcgcsv.com) | aucune | miroir public |
| eBay.fr annonces actives | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | developer.ebay.com ▸ créer un compte ▸ *Application Keys* (production) |
| eBay.fr ventes réalisées | mêmes clés, **accès Marketplace Insights à faire accorder** | developer.ebay.com ▸ *Application Growth Check* ; accès restreint, accordé à la discrétion d'eBay |

Ajoutez les deux clés : dépôt GitHub ▸ **Settings ▸ Secrets and variables ▸ Actions ▸ New repository secret**
(`EBAY_CLIENT_ID`, puis `EBAY_CLIENT_SECRET`). Sans clé, le pipeline fonctionne avec Cardmarket et TCGplayer seuls.
Sans accès Insights, il utilise les annonces actives eBay.fr à la place des ventes réalisées.

## 4. Premier lancement
1. Onglet **Actions ▸ Update prices ▸ Run workflow**. Après 1 à 3 minutes, `prices.json` apparaît.
2. Onglet **Actions ▸ Backfill history ▸ Run workflow** (12 mois, 15 à 40 minutes) : crée l'historique estimé en pointillés.
3. Ouvrez `https://raw.githubusercontent.com/<compte>/pokeworth-prices/main/prices.json` dans Safari pour vérifier.

## 5. Exécution en local (facultatif)
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export EBAY_CLIENT_ID=...  EBAY_CLIENT_SECRET=...      # facultatif
python3 build_feed.py --report      # produits sans association Cardmarket
python3 build_feed.py               # écrit prices.json
python3 backfill_history.py --dry-run
for t in test_*.py; do python3 $t; done
```

## 6. Automatisation
`update-prices.yml` s'exécute chaque jour (cron `17 4 * * *`). Pour deux passages par jour, ajoutez `- cron: "17 16 * * *"`.
GitHub suspend les tâches d'un dépôt sans activité pendant 60 jours : onglet Actions ▸ *Enable workflow*.

## 7. Limites à connaître
- Cardmarket ne publie **aucun historique** des produits scellés : la courbe réelle se construit jour après jour ; avant, elle est estimée
  (TCGplayer, tirets dans l'app) et ne remonte pas au-delà de février 2024.
- Cardmarket et TCGplayer ne distinguent pas la langue : le filtre FR strict ne s'applique qu'aux données eBay.
- Pas de collecte de pages web (scraping) de Cardmarket ni d'eBay : leurs conditions l'interdisent. Vérifiez les conditions d'usage des
  fichiers publics Cardmarket avant la publication commerciale de l'app.
