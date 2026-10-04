# Backend des prix (gratuit, sans serveur, sans clé d'API)

L'app ne parle jamais à un fournisseur de prix : elle télécharge un simple fichier `prices.json`.
Ce dossier contient ce qui fabrique ce fichier.

```
fichiers publics Cardmarket ──> build_feed.py ──> prices.json ──> app PokeWorth
(produits + price guide, mis à jour     GitHub Actions, chaque jour     (dépôt GitHub)
 chaque jour)
```

Cardmarket publie chaque jour, pour Pokémon (jeu n° 6), la liste de ses produits non-cartes et un « price guide »
(avg, low, trend, avg7, avg30 en euros) : `downloads.s3.cardmarket.com/productCatalog/…`. Aucun compte ni clé n'est nécessaire.

## Prix lissés multi-sources

`build_feed.py` mélange jusqu'à trois sources par produit (`blend.py`), puis lisse le résultat avec le prix précédent
(±25 % maximum entre deux exécutions) pour qu'une annonce aberrante ne fasse pas sauter la courbe :

| Source | Poids | Données | Clé |
|---|---|---|---|
| Cardmarket | 60 % | price guide public (tendance, bas, moyenne 30 j) | aucune |
| eBay France, ventes réalisées | 30 % | médiane des ventes conclues des 60 derniers jours, versions françaises uniquement (API Marketplace Insights, **accès restreint** : à demander à eBay) | `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` |
| eBay France, annonces | 25 % | repli si l'accès aux ventes n'est pas accordé : médiane des annonces neuves à prix fixe, versions françaises uniquement (API Browse) | mêmes clés (gratuites, developer.ebay.com) |
| TCGplayer | 15 % | miroir public tcgcsv.com, USD converti en EUR | aucune |

Une source indisponible est ignorée (le prix repose sur les autres). Le champ `sources` de chaque prix indique
lesquelles ont été retenues. `python3 build_feed.py --no-extra` = Cardmarket seul.
Fichiers à copier dans le dépôt : `build_feed.py`, `blend.py`, `cardmarket_source.py`, `market_sources.py`, `ebay_sold.py`, `fr_filter.py`, `requirements.txt`, `cardmarket_map.json`, `backfill_history.py` (historique, facultatif).
Pour eBay, ajoutez les deux secrets dans GitHub (Settings ▸ Secrets and variables ▸ Actions).

Limites à connaître :
- Les noms de produits Cardmarket sont **en anglais** : `cardmarket_source.py` associe chaque produit du catalogue français
  à son `idProduct` (extension + type de produit). Ce qui n'est pas trouvé automatiquement se règle à la main dans `cardmarket_map.json`.
- Le price guide ne distingue pas les langues : `low_fr` contient le prix « low » toutes langues confondues, `trend` la tendance Cardmarket.
- Vérifiez les conditions d'utilisation de Cardmarket avant une publication commerciale de l'app.

## Mise en place (10 minutes)

1. Créez un dépôt GitHub `pokeworth-prices` (public : le fichier ne contient que des prix).
2. À la racine du dépôt, copiez : `build_feed.py`, `blend.py`, `cardmarket_source.py`, `market_sources.py`, `cardmarket_map.json`, `items_pokemon_fr.json`
   (depuis `PokeWorth/Resources/`), et `update-prices.yml` dans `.github/workflows/`.
3. Testez en local (Python 3.10+, aucune dépendance) :
   ```
   python3 build_feed.py --report      # liste les produits non associés, avec des candidats
   python3 build_feed.py               # écrit prices.json
   ```
   Pour chaque produit de `--report`, copiez le bon `idProduct` dans `cardmarket_map.json` :
   `{"coffret-ev07-coffret-ultra-premium-terapagos-ex": 123456}` (l'identifiant est dans l'URL de la fiche Cardmarket ou dans le fichier produits).
4. Poussez le dépôt, puis Actions → *Update prices* → *Run workflow* : `prices.json` apparaît, puis se met à jour chaque jour.
5. Dans l'app, renseignez `AppConfig.priceFeedURL` avec
   `https://raw.githubusercontent.com/<compte>/pokeworth-prices/main/prices.json`.

Quand vous enrichissez le catalogue, recopiez `items_pokemon_fr.json` dans le dépôt.

## Contrat de `prices.json`

```json
{
  "version": 1,
  "updated_at": "2026-09-28T18:00:00Z",
  "currency": "EUR",
  "prices": [
    {
      "id": "display-eb07-evolution-celeste",
      "trend": 655.0,
      "low_fr": 615.5,
      "avg_30d": 640.2,
      "history": [{ "date": "2026-09-27T18:00:00Z", "trend": 651.3 }]
    }
  ]
}
```

- `id` : l'`id` du catalogue (aucun identifiant Cardmarket côté app).
- Tout champ peut être `null` : l'app garde alors le dernier prix connu. Un produit non associé reste sans prix (« Prix indisponible »).
- `history` : un point par jour pendant 90 jours, puis un par semaine jusqu'à 400 jours, construit au fil des exécutions (le script relit l'ancien `prices.json`).
  Un point `"est": true` est une estimation reconstituée (voir ci-dessous) ; l'app la trace en pointillés.
- `avg_30d` : si Cardmarket ne la fournit pas (cas des produits scellés), elle est calculée sur les relevés réels des 30 derniers jours (3 relevés minimum).

## Filtre marché français

- **eBay** : `fr_filter.py` ne garde une annonce ou une vente que si aucune autre langue n'est mentionnée (anglais, japonais, coréen…)
  ET qu'elle indique « FR / VF / français » ou porte le nom français de l'extension.
- **Cardmarket et TCGplayer ne distinguent pas la langue d'un produit scellé** : leurs prix ne peuvent pas être filtrés. TCGplayer (États-Unis,
  produits anglais) n'a donc que 15 % du poids et est écarté dès qu'il s'éloigne de plus de 45 % des autres sources ; sur les produits qui ont
  des ventes eBay.fr, la cote française pèse 30 % et `low_fr` devient le plus bas prix réellement payé en France.
- Le champ `n_sales` du flux indique le nombre de ventes françaises retenues (absent sans accès Marketplace Insights).
- Aucun point d'historique n'est conservé avant la date de sortie officielle (`date_sortie` du catalogue).

## Historique des prix (courbes)

**Cardmarket ne publie aucun historique** pour les produits scellés, seulement le prix du jour : la courbe réelle se construit donc
jour après jour (un point à chaque exécution). Pour que les courbes ne soient pas vides au lancement de l'app, `backfill_history.py`
reconstitue l'historique des 12 derniers mois à partir des archives quotidiennes **TCGplayer** de tcgcsv.com
(`https://tcgcsv.com/archive/tcgplayer/prices-AAAA-MM-JJ.ppmd.7z`) : la forme de la courbe vient de TCGplayer (en dollars, converti au
taux du jour concerné), calée sur le prix actuel du flux. Ces points portent `"est": true` ; chaque vrai relevé quotidien remplace
l'estimation du jour. Seuls les produits associés à TCGplayer sont enrichis.

À lancer une fois : copiez `backfill_history.py` et `backfill-history.yml` (dans `.github/workflows/`) dans le dépôt, puis
Actions > *Backfill history* > *Run workflow* (≈ 15 à 40 min). En local : `pip install py7zr && python3 backfill_history.py`
(`--dry-run` pour voir le bilan sans écrire). `python3 test_history.py` vérifie la logique sans réseau.

## Changer de fournisseur

Seule la fonction `fetch_quote()` de `build_feed.py` connaît la source. Pour utiliser une API tierce, réécrivez-la : l'app n'est pas touchée.

## Tester sans backend

En build Debug, si `AppConfig.priceFeedURL` est `nil`, l'app lit `prices_sample.json` (prix **fictifs**, marqués `is_sample`).

## Actualités (`news.json`)
Fichier statique du même type que `prices.json`, à héberger au même endroit et à renseigner dans `AppConfig.newsFeedURL`.
Format : voir `news.example.json` (`kind` = `release`, `announcement` ou `visual` ; `releaseDate` déclenche le compte à rebours et le rappel du jour J ;
`isMajor` met l'actualité à la une et l'envoie en notification individuelle). Prévoir un ETag (GitHub Pages / raw le fait) : l'app ne retélécharge que si le fichier change.
