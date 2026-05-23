# Output Attendu — Visualization Skill

## Dataset de reference

**exportations_madagascar.xlsx** (apres ETL Skill)
- 1 400 lignes × 10 colonnes
- 3 colonnes numeriques : `quantite`, `prix_unitaire_usd`, `revenu_total_usd`
- 6 colonnes categorielles : `produit`, `categorie`, `region`, `pays_destination`, `transport`, `entreprise`
- 1 colonne temporelle : `date`

---

## Graphiques generes (attendus)

| N° | Titre                                      | Type       | Colonnes               | chart_id Directus |
|----|-------------------------------------------|------------|------------------------|-------------------|
| 1  | Distribution de quantite                  | histogram  | quantite               | uuid-1            |
| 2  | Distribution de prix_unitaire_usd         | histogram  | prix_unitaire_usd      | uuid-2            |
| 3  | Distribution de revenu_total_usd          | histogram  | revenu_total_usd       | uuid-3            |
| 4  | Boxplot — 3 variables                     | boxplot    | quantite, prix, revenu | uuid-4            |
| 5  | Distribution de produit                   | bar_chart  | produit                | uuid-5            |
| 6  | Distribution de categorie                 | bar_chart  | categorie              | uuid-6            |
| 7  | Distribution de region                    | bar_chart  | region                 | uuid-7            |
| 8  | Distribution de pays_destination          | bar_chart  | pays_destination       | uuid-8            |
| 9  | Distribution de transport                 | bar_chart  | transport              | uuid-9            |
| 10 | Distribution de entreprise                | bar_chart  | entreprise             | uuid-10           |
| 11 | Matrice de Correlation                    | heatmap    | numeriques             | uuid-11           |
| 12 | Evolution temporelle                      | line_chart | date, quantite...      | uuid-12           |
| 13 | Scatter : prix_unitaire_usd vs revenu     | scatter    | prix, revenu           | uuid-13           |
| 14 | Pairplot — variables numeriques           | pairplot   | 3 colonnes num.        | uuid-14           |

**Total attendu** : 12 a 14 graphiques selon les colonnes disponibles.

---

## VisualizationResponse exemple

```json
{
  "skill":       "Visualization",
  "session_id":  "user_42_2025-06-01_14-30-22",
  "status":      "success",
  "charts": [
    {
      "chart_id":           "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title":              "Distribution de quantite",
      "chart_type":         "histogram",
      "columns_involved":   ["quantite"]
    }
  ],
  "report_mdx_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "eda_report_path": "outputs/rapport_eda/exportations_dirty/eda_report_exportations_dirty.md",
  "errors": []
}
```

---

## Structure du rapport MDX genere

```markdown
---
title: Rapport EDA — exportations_dirty
date: 17/05/2026 18:30
n_rows: 1400
n_cols: 10
n_charts: 14
---

# Rapport EDA — exportations_dirty

## Resume Executif

<KeyPoints>
- Le dataset contient 1 400 transactions d'exportation avec 10 variables.
- Le revenu total presente une forte asymetrie positive (skewness = 1.82).
- Forte correlation entre quantite et revenu_total_usd (r = 0.87).
- Madagascar exporte principalement vers la France (26%) et la Chine (22%).
- 6 regions identifiees, Analamanga representant 30% des exportations.
- Transport maritime dominant (85% des transactions).
</KeyPoints>

## Statistiques Numeriques

| Colonne           | Mean    | Std     | Min  | Mediane | Max    |
|-------------------|---------|---------|------|---------|--------|
| quantite          | 524.3   | 278.6   | 52   | 515     | 1000   |
| prix_unitaire_usd | 63.2    | 66.9    | 2    | 30      | 201    |
| revenu_total_usd  | 29103   | 32285   | -2378| 14420   | 97658  |

## Graphiques EDA

### 1. Distribution de quantite

**Type** : `histogram` | **Colonnes** : `quantite`

<ChartEmbed chartId="a1b2c3d4-..." title="Distribution de quantite" />

> La distribution des quantites exportees est bimodale avec deux pics autour de
> 200 et 800 unites. Cette pattern suggere deux segments de clients distincts.

...
```

---

## Commentaires Gemini exemples

**Distribution de quantite** :
> La distribution des quantites exportees est bimodale avec deux pics autour de 200 et 800 unites. Cette structure suggere deux segments de clients distincts — petits exportateurs et grands exportateurs. Une analyse par segment pourrait reveler des comportements tarifaires differents.

**Matrice de Correlation** :
> La matrice revele une forte correlation positive (r=0.87) entre quantite et revenu_total_usd, ce qui est attendu. La correlation modere entre prix_unitaire_usd et revenu (r=0.52) suggere que le volume prime sur le prix dans la generation de revenu.

---

## Resume executif Gemini (5-8 points)

1. Le dataset contient 1 400 transactions d'exportation couvrant 6 regions et 6 pays de destination.
2. Le revenu total presente une forte asymetrie positive — quelques transactions a tres haut revenu tirent la moyenne.
3. Forte correlation quantite/revenu (r=0.87) — le volume est le principal driver du chiffre d'affaires.
4. Madagascar exporte principalement vers la France (26%) et la Chine (22%).
5. Transport maritime dominant (85%) — potentiel d'optimisation logistique pour le transport aerien.
6. Outliers detectes sur prix_unitaire_usd (12.3% cappés) — a investiguer avec l'equipe metier.

---

## Fichiers produits

```
outputs/
  charts/
    01_histogram_quantite.html
    01_histogram_quantite.png
    02_histogram_prix_unitaire_usd.html
    ...
    11_heatmap_numeriques.html
    ...

  rapport_eda/
    exportations_dirty/
      eda_report_exportations_dirty.md
```

**Directus** :
- 14 items dans la collection `charts` (Plotly JSON)
- 1 item dans la collection `reports_mdx` (rapport EDA MDX complet)