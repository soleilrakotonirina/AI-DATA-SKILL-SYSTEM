---
name: data-pipeline-skill
description: >
  Assistant Data Science complet : ETL + Visualisation EDA dans un seul modèle.
  Déclencher ETL quand l'utilisateur mentionne : nettoyer, préparer, transformer,
  doublons, valeurs manquantes, outliers, encodage, normalisation, star schema, ETL.
  Déclencher Viz quand l'utilisateur mentionne : graphiques, visualiser, analyser,
  EDA, distributions, corrélations, histogramme, boxplot, heatmap, dashboard, KPIs.
  Déclencher les deux quand : "nettoie et visualise", "prépare et analyse".
  Trigger EN: clean and visualize, ETL pipeline, EDA charts, data analysis, full pipeline.
metadata:
  version: "1.0"
  mcp_servers:
    etl: http://localhost:8001/mcp
    viz: http://localhost:8002/mcp
  tools_etl: etl_auto, read_report, read_dataset, list_all_results
  tools_viz: viz_auto, read_viz_report, list_charts, list_all_results
---

# Data Pipeline Skill — ETL + Visualisation

## Description

Skill combiné capable d'exécuter le pipeline ETL et la visualisation EDA
en fonction de la demande de l'utilisateur.

---

## ROUTING — Comment choisir le bon outil

### L'utilisateur demande du nettoyage / préparation

Mots clés : nettoyer, préparer, transformer, doublons, valeurs manquantes,
outliers, encodage, normalisation, star schema, ETL, pipeline de données

→ **Appelle `etl_auto()`**

### L'utilisateur demande des graphiques / analyse

Mots clés : graphiques, visualiser, analyser, EDA, distributions, corrélations,
histogramme, boxplot, heatmap, dashboard, KPIs, statistiques, explorer les données

→ **Appelle `viz_auto()`**

### L'utilisateur demande les deux

Exemples : "nettoie et visualise", "prépare et analyse",
"pipeline complet", "ETL puis graphiques"

→ **Enchaîne les 2 :**
1. `etl_auto()` → récupérer `clean_path` et `dataset_name`
2. `viz_auto()` sur le fichier nettoyé

### L'utilisateur demande ses fichiers disponibles

Exemples : "quels fichiers j'ai ?", "mes résultats", "datasets disponibles"

→ **Appelle `list_all_results()`**

---

## Séquence pipeline complet ETL → Viz

```
APPEL 1 : etl_auto()
  → récupère : dataset_name, clean_path, status

APPEL 2 : viz_auto()
  → avec le dataset nettoyé issu de l'ETL
  → les liens téléchargement sont inclus automatiquement
```

---

## Paramètres etl_auto

| Paramètre | Défaut | Valeurs |
|-----------|--------|---------|
| `target_column` | `""` | colonne ML à protéger |
| `missing_strategy` | `auto` | `auto` · `constant` · `drop` |
| `outlier_action` | `cap` | `cap` · `remove` · `flag` |
| `encode_method` | `auto` | `auto` · `label` · `onehot` |
| `scale_method` | `standard` | `standard` · `minmax` |
| `columns_to_exclude` | `""` | noms séparés par virgule |

## Paramètres viz_auto

| Paramètre | Défaut | Valeurs |
|-----------|--------|---------|
| `target_column` | `""` | colonne cible ML à analyser |
| `question` | `""` | question analytique |
| `export_png` | `false` | exporter en PNG aussi |

---

## Traduction langage naturel → paramètres

| L'utilisateur dit | Tool + paramètre |
|-------------------|-----------------|
| "nettoie ce fichier" | `etl_auto()` |
| "visualise ce fichier" | `viz_auto()` |
| "nettoie et visualise" | `etl_auto()` puis `viz_auto()` |
| "cible = churn" | `target_column="churn"` dans les 2 |
| "impact du salaire ?" | `viz_auto(question="impact du salaire")` |
| "supprimer les outliers" | `etl_auto(outlier_action="remove")` |
| "one-hot encoding" | `etl_auto(encode_method="onehot")` |
| "mes fichiers disponibles" | `list_all_results()` |
| "rapport ETL complet" | `read_report(report_path)` |
| "rapport EDA complet" | `read_viz_report(report_path)` |

---

## Règles

- ETL demande → etl_auto EN PREMIER
- Viz demande → viz_auto EN PREMIER
- Pipeline complet → etl_auto PUIS viz_auto
- JAMAIS inventer des métriques
- TOUJOURS utiliser les valeurs retournées par les tools
- Après ETL → proposer la visualisation
- Après Viz → proposer le Modeling Skill
- Répondre en français