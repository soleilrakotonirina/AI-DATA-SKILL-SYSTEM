"""
backend/tests/test_visualization.py
Tests unitaires du Visualization Skill v2.0

Valide :
- classify_columns() : detection phone, email, name, id, constant, year, numeric
- compute_descriptive_stats() : filtre colonnes non visualisables
- compute_correlation_matrix() : utilise uniquement colonnes 'numeric'
- build_eda_charts() : pas de graphiques absurdes (telephone, noms, emails)
- Boxplots individuels (pas de melange d'echelles)
- Scatters uniquement entre variables numeriques reelles
- Pairplot uniquement sur variables numeriques reelles
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ajouter backend/ au path Python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skills.visualization_skill.core.eda import (
    analyze_target_variable,
    classify_columns,
    compute_correlation_matrix,
    compute_descriptive_stats,
    detect_data_patterns,
    get_visualizable_columns,
)
from skills.visualization_skill.core.dashboard_builder import (
    build_eda_charts,
    _pick_color_col,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def df_universitaire() -> pd.DataFrame:
    """
    Dataset simulant les Donnees_Universitaires_JOINTE avec les colonnes
    problematiques identifiees lors du test reel.
    """
    np.random.seed(42)
    n = 100
    return pd.DataFrame({
        # Colonnes qui DOIVENT etre exclues
        "telephone":          np.random.randint(610_000_000, 699_999_999, n),  # phone
        "email":              [f"user{i}@universite.fr" for i in range(n)],     # email
        "email_Enseignants":  [f"prof{i}@univ-prof.fr" for i in range(n)],      # email
        "nom":                [f"Nom{i % 50}" for i in range(n)],               # name
        "prenom":             [f"Prenom{i % 40}" for i in range(n)],            # name
        "nom_Enseignants":    [f"ProfNom{i % 12}" for i in range(n)],           # name
        "prenom_Enseignants": [f"ProfPre{i % 12}" for i in range(n)],           # name
        "id_inscription":     [f"INS{i:04d}" for i in range(n)],               # id_high
        "id_etudiant":        [f"ETU{i:04d}" for i in range(n // 2 * 2)[:n]],  # id_high
        "filiere":            ["Gestion"] * n,                                  # constant
        "departement":        ["Gestion"] * n,                                  # constant

        # Colonnes qui DOIVENT etre incluses comme numeriques REELLES
        "credits_ects":       np.random.uniform(0, 8.625, n),
        "volume_horaire":     np.random.choice([75, 100, 125, 150], n).astype(float),
        "salaire":            np.random.normal(60_000, 10_000, n),

        # Annees → year (bar chart, pas histogram)
        "annee_inscription":  np.random.choice([2019, 2020, 2021, 2022, 2023], n),

        # Colonnes categorielles → bar chart
        "statut":             np.random.choice(["Inscrit", "En cours", "Valide", "Abandonne"], n),
        "sexe":               np.random.choice(["M", "F"], n),
        "niveau_etude":       np.random.choice(["L1", "L2", "L3", "M1", "M2"], n),
        "ville":              np.random.choice(["Paris", "Lyon", "Bordeaux", "Rennes", "Lille"], n),
        "grade":              np.random.choice(["Professeur", "Maitre de Conferences", "Charge de Cours"], n),
        "specialisation":     np.random.choice(["RH", "Finance", "Marketing", "Management"], n),

        # ID avec faible cardinalite → id_low → gardees comme categorielle
        "id_cours":           [f"CRS{(i % 20) + 1:03d}" for i in range(n)],
        "id_enseignant":      [f"ENS{(i % 12) + 1:03d}" for i in range(n)],

        # Dates → excludes des visualisations standard
        "date_inscription":   pd.date_range("2020-01-01", periods=n, freq="3D").strftime("%Y-%m-%d").tolist(),
        "date_naissance":     pd.date_range("2000-01-01", periods=n, freq="60D").strftime("%Y-%m-%d").tolist(),
    })


@pytest.fixture
def df_simple() -> pd.DataFrame:
    """Dataset simple pour tests de base."""
    np.random.seed(0)
    n = 200
    return pd.DataFrame({
        "age":    np.random.normal(35, 10, n).clip(18, 80),
        "salaire": np.random.normal(50_000, 15_000, n),
        "score":   np.random.uniform(0, 100, n),
        "region":  np.random.choice(["Nord", "Sud", "Est", "Ouest"], n),
        "churn":   np.random.choice(["Oui", "Non"], n, p=[0.2, 0.8]),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Tests : classify_columns()
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyColumns:
    """Valide la classification intelligente des colonnes."""

    def test_telephone_classifie_phone(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["telephone"] == "phone", (
            "telephone doit etre classifie 'phone' (valeur moyenne ~650M)"
        )

    def test_email_classifie_email(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["email"] == "email", "email etudiant doit etre 'email'"
        assert classes["email_Enseignants"] == "email", "email enseignant doit etre 'email'"

    def test_noms_classifies_name(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["nom"] == "name", "nom doit etre 'name'"
        assert classes["prenom"] == "name", "prenom doit etre 'name'"
        assert classes["nom_Enseignants"] == "name", "nom_Enseignants doit etre 'name'"
        assert classes["prenom_Enseignants"] == "name", "prenom_Enseignants doit etre 'name'"

    def test_ids_haute_cardinalite_classifies_id_high(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["id_inscription"] == "id_high", (
            "id_inscription (100 uniques) doit etre 'id_high'"
        )

    def test_ids_basse_cardinalite_classifies_id_low(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["id_cours"] == "id_low", (
            "id_cours (20 uniques) doit etre 'id_low' (conserve pour bar chart)"
        )
        assert classes["id_enseignant"] == "id_low", (
            "id_enseignant (12 uniques) doit etre 'id_low'"
        )

    def test_constantes_classifiees_constant(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["filiere"] == "constant", "filiere (1 unique) doit etre 'constant'"
        assert classes["departement"] == "constant", "departement doit etre 'constant'"

    def test_numeriques_reels_classifies_numeric(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["credits_ects"] == "numeric", "credits_ects doit etre 'numeric'"
        assert classes["volume_horaire"] == "numeric", "volume_horaire doit etre 'numeric'"
        assert classes["salaire"] == "numeric", "salaire doit etre 'numeric'"

    def test_annee_classifiee_year_pas_numeric(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["annee_inscription"] == "year", (
            "annee_inscription (2019-2023) doit etre 'year', pas 'numeric'"
        )

    def test_categorielles_classifiees_categorical(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        for col in ["statut", "sexe", "niveau_etude", "ville", "grade", "specialisation"]:
            assert classes[col] == "categorical", (
                f"{col} doit etre 'categorical', obtenu '{classes[col]}'"
            )

    def test_dates_classifiees_date(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        assert classes["date_inscription"] == "date", "date_inscription doit etre 'date'"
        assert classes["date_naissance"] == "date", "date_naissance doit etre 'date'"

    def test_simple_dataset(self, df_simple):
        classes = classify_columns(df_simple)
        assert classes["age"] == "numeric"
        assert classes["salaire"] == "numeric"
        assert classes["score"] == "numeric"
        assert classes["region"] == "categorical"
        assert classes["churn"] == "categorical"


# ─────────────────────────────────────────────────────────────────────────────
# Tests : get_visualizable_columns()
# ─────────────────────────────────────────────────────────────────────────────

class TestGetVisualizableColumns:
    """Valide la separation des colonnes par groupe de visualisation."""

    def test_numeric_ne_contient_pas_telephone(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        groups = get_visualizable_columns(df_universitaire, classes)
        assert "telephone" not in groups["numeric"], (
            "telephone NE DOIT PAS etre dans numeric"
        )

    def test_numeric_contient_credits_salaire_volume(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        groups = get_visualizable_columns(df_universitaire, classes)
        for col in ["credits_ects", "volume_horaire", "salaire"]:
            assert col in groups["numeric"], f"{col} DOIT etre dans numeric"

    def test_numeric_ne_contient_pas_annee(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        groups = get_visualizable_columns(df_universitaire, classes)
        assert "annee_inscription" not in groups["numeric"], (
            "annee_inscription (year) NE DOIT PAS etre dans numeric"
        )

    def test_annee_dans_year(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        groups = get_visualizable_columns(df_universitaire, classes)
        assert "annee_inscription" in groups["year"]

    def test_exclus_contient_colonnes_problematiques(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        groups = get_visualizable_columns(df_universitaire, classes)
        exclus = groups["excluded"]
        for col in ["telephone", "email", "nom", "prenom", "id_inscription", "filiere"]:
            assert col in exclus, f"{col} DOIT etre exclu"


# ─────────────────────────────────────────────────────────────────────────────
# Tests : compute_descriptive_stats()
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeDescriptiveStats:
    """Valide que les stats EDA excluent les colonnes non visualisables."""

    def test_telephone_absent_numeric_stats(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        stats = compute_descriptive_stats(df_universitaire, col_classes=classes)
        assert "telephone" not in stats["numeric_stats"], (
            "telephone NE DOIT PAS apparaitre dans numeric_stats"
        )

    def test_credits_present_numeric_stats(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        stats = compute_descriptive_stats(df_universitaire, col_classes=classes)
        assert "credits_ects" in stats["numeric_stats"]
        assert stats["numeric_stats"]["credits_ects"]["mean"] is not None

    def test_noms_absents_stats(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        stats = compute_descriptive_stats(df_universitaire, col_classes=classes)
        for col in ["nom", "prenom", "nom_Enseignants"]:
            assert col not in stats["numeric_stats"]
            assert col not in stats["categorical_stats"]

    def test_statut_present_categorical_stats(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        stats = compute_descriptive_stats(df_universitaire, col_classes=classes)
        assert "statut" in stats["categorical_stats"]
        assert len(stats["categorical_stats"]["statut"]["top_values"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests : compute_correlation_matrix()
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeCorrelationMatrix:
    """Valide que la matrice de correlation exclut telephone et annees."""

    def test_telephone_absent_matrice_correlation(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        corr, pairs = compute_correlation_matrix(df_universitaire, col_classes=classes)
        if not corr.empty:
            assert "telephone" not in corr.columns, (
                "telephone NE DOIT PAS apparaitre dans la matrice de correlation"
            )

    def test_annee_inscription_absente_matrice(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        corr, pairs = compute_correlation_matrix(df_universitaire, col_classes=classes)
        if not corr.empty:
            assert "annee_inscription" not in corr.columns, (
                "annee_inscription (year) NE DOIT PAS etre dans la correlation"
            )

    def test_numeriques_reels_presents_matrice(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        corr, pairs = compute_correlation_matrix(df_universitaire, col_classes=classes)
        for col in ["credits_ects", "volume_horaire", "salaire"]:
            assert col in corr.columns, f"{col} DOIT etre dans la matrice"

    def test_simple_dataset_correlation(self, df_simple):
        classes = classify_columns(df_simple)
        corr, pairs = compute_correlation_matrix(df_simple, col_classes=classes)
        assert not corr.empty
        assert "age" in corr.columns
        assert "salaire" in corr.columns


# ─────────────────────────────────────────────────────────────────────────────
# Tests : build_eda_charts()
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildEdaCharts:
    """Valide que les graphiques generes sont pertinents et sans absurdites."""

    @pytest.fixture
    def charts_universitaire(self, df_universitaire):
        """Pre-calcule les graphiques pour le dataset universitaire."""
        from skills.visualization_skill.core.eda import (
            compute_descriptive_stats,
            compute_correlation_matrix,
            detect_data_patterns,
            classify_columns,
        )
        col_classes = classify_columns(df_universitaire)
        stats = compute_descriptive_stats(df_universitaire, col_classes=col_classes)
        corr, _ = compute_correlation_matrix(df_universitaire, col_classes=col_classes)
        patterns = detect_data_patterns(df_universitaire, col_classes=col_classes)
        charts = build_eda_charts(
            df=df_universitaire,
            stats=stats,
            patterns=patterns,
            corr_matrix=corr if not corr.empty else None,
        )
        return charts

    def _get_titles(self, charts):
        return [c["title"] for c in charts]

    def _get_cols(self, charts):
        """Retourne toutes les colonnes impliquees dans tous les graphiques."""
        cols = set()
        for c in charts:
            cols.update(c["columns_involved"])
        return cols

    # ── Colonnes exclues ─────────────────────────────────────────────────────

    def test_telephone_absent_de_tous_graphiques(self, charts_universitaire):
        cols_used = self._get_cols(charts_universitaire)
        assert "telephone" not in cols_used, (
            "telephone NE DOIT PAS apparaitre dans aucun graphique"
        )

    def test_noms_absents_graphiques(self, charts_universitaire):
        cols_used = self._get_cols(charts_universitaire)
        for col in ["nom", "prenom", "nom_Enseignants", "prenom_Enseignants"]:
            assert col not in cols_used, (
                f"{col} (nom de personne) NE DOIT PAS etre dans un graphique"
            )

    def test_emails_absents_graphiques(self, charts_universitaire):
        cols_used = self._get_cols(charts_universitaire)
        for col in ["email", "email_Enseignants"]:
            assert col not in cols_used, f"{col} NE DOIT PAS etre dans un graphique"

    def test_constantes_absentes_graphiques(self, charts_universitaire):
        cols_used = self._get_cols(charts_universitaire)
        for col in ["filiere", "departement"]:
            assert col not in cols_used, f"{col} (constant) NE DOIT PAS etre graphe"

    def test_ids_haute_cardinalite_absents(self, charts_universitaire):
        cols_used = self._get_cols(charts_universitaire)
        for col in ["id_inscription", "id_etudiant"]:
            assert col not in cols_used, (
                f"{col} (id_high) NE DOIT PAS etre dans un graphique"
            )

    # ── Colonnes incluses ────────────────────────────────────────────────────

    def test_numeriques_reels_presents(self, charts_universitaire):
        cols_used = self._get_cols(charts_universitaire)
        for col in ["credits_ects", "volume_horaire", "salaire"]:
            assert col in cols_used, f"{col} DOIT etre dans au moins un graphique"

    def test_categorielles_importantes_presentes(self, charts_universitaire):
        cols_used = self._get_cols(charts_universitaire)
        for col in ["statut", "sexe", "niveau_etude", "grade"]:
            assert col in cols_used, f"{col} DOIT etre dans au moins un graphique"

    # ── Types de graphiques ──────────────────────────────────────────────────

    def test_histogrammes_generes_pour_numeriques(self, charts_universitaire):
        hist_cols = [
            c["columns_involved"][0]
            for c in charts_universitaire
            if c["chart_type"] == "histogram"
        ]
        for col in ["credits_ects", "volume_horaire", "salaire"]:
            assert col in hist_cols, f"Histogramme manquant pour {col}"
        assert "telephone" not in hist_cols, "Pas d'histogramme pour telephone"

    def test_boxplots_individuels_par_colonne(self, charts_universitaire):
        boxplot_charts = [c for c in charts_universitaire if c["chart_type"] == "boxplot"]
        for chart in boxplot_charts:
            assert len(chart["columns_involved"]) == 1, (
                f"Boxplot DOIT etre individuel (1 colonne), "
                f"obtenu {chart['columns_involved']}"
            )
        boxplot_cols = [c["columns_involved"][0] for c in boxplot_charts]
        assert "telephone" not in boxplot_cols, "Pas de boxplot pour telephone"

    def test_scatter_uniquement_entre_numeriques_reels(self, charts_universitaire):
        scatter_charts = [c for c in charts_universitaire if c["chart_type"] == "scatter"]
        from skills.visualization_skill.core.eda import classify_columns
        classes = classify_columns(
            pd.DataFrame({
                "credits_ects": [], "volume_horaire": [], "salaire": [],
                "telephone": [], "annee_inscription": [],
            })
        )
        for chart in scatter_charts:
            cols = chart["columns_involved"]
            for col in cols:
                if col in ["telephone", "annee_inscription"]:
                    pytest.fail(
                        f"Scatter avec colonne non-numerique : {col} dans {cols}"
                    )

    def test_pairplot_uniquement_sur_numeriques_reels(self, charts_universitaire):
        pairplot_charts = [c for c in charts_universitaire if c["chart_type"] == "pairplot"]
        for chart in pairplot_charts:
            for col in chart["columns_involved"]:
                assert col not in ["telephone", "annee_inscription", "id_inscription"], (
                    f"Pairplot NE DOIT PAS inclure {col}"
                )

    def test_heatmap_sans_telephone(self, charts_universitaire):
        heatmap_charts = [c for c in charts_universitaire if c["chart_type"] == "heatmap"]
        for chart in heatmap_charts:
            assert "telephone" not in chart["columns_involved"], (
                "Heatmap NE DOIT PAS inclure telephone"
            )

    def test_nombre_graphiques_raisonnable(self, charts_universitaire):
        n = len(charts_universitaire)
        assert n >= 5, f"Trop peu de graphiques generes : {n}"
        assert n <= 50, f"Trop de graphiques generes : {n}"

    # ── Dataset simple ───────────────────────────────────────────────────────

    def test_simple_dataset_graphiques_corrects(self, df_simple):
        from skills.visualization_skill.core.eda import (
            compute_descriptive_stats,
            compute_correlation_matrix,
            detect_data_patterns,
            classify_columns,
        )
        classes = classify_columns(df_simple)
        stats = compute_descriptive_stats(df_simple, col_classes=classes)
        corr, _ = compute_correlation_matrix(df_simple, col_classes=classes)
        patterns = detect_data_patterns(df_simple, col_classes=classes)
        charts = build_eda_charts(
            df=df_simple,
            stats=stats,
            patterns=patterns,
            corr_matrix=corr if not corr.empty else None,
        )
        chart_types = {c["chart_type"] for c in charts}
        assert "histogram" in chart_types, "Doit avoir des histogrammes"
        assert "bar_chart" in chart_types, "Doit avoir des bar charts"
        assert len(charts) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# Tests : _pick_color_col()
# ─────────────────────────────────────────────────────────────────────────────

class TestPickColorCol:
    def test_prefere_statut(self, df_universitaire):
        cat_cols = ["ville", "statut", "sexe", "niveau_etude"]
        result = _pick_color_col(df_universitaire, cat_cols)
        assert result == "statut", "statut doit etre prefere pour la couleur"

    def test_fallback_si_pas_de_prefere(self):
        df = pd.DataFrame({
            "categorie": ["A", "B", "C"] * 10,
            "groupe":    ["X", "Y"] * 15,
        })
        result = _pick_color_col(df, ["categorie", "groupe"])
        assert result in ["categorie", "groupe"]

    def test_none_si_cardinalite_trop_haute(self):
        df = pd.DataFrame({
            "id_col": [f"X{i}" for i in range(100)],
        })
        result = _pick_color_col(df, ["id_col"], max_unique=8)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests : detect_data_patterns()
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectDataPatterns:
    def test_telephone_absent_patterns(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        patterns = detect_data_patterns(df_universitaire, col_classes=classes)
        all_pattern_cols = (
            patterns["time_series_columns"]
            + patterns["geo_columns"]
            + patterns["text_columns"]
        )
        assert "telephone" not in all_pattern_cols

    def test_ville_dans_geo(self, df_universitaire):
        classes = classify_columns(df_universitaire)
        patterns = detect_data_patterns(df_universitaire, col_classes=classes)
        assert "ville" in patterns["geo_columns"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests d'integration rapide
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    """Validation end-to-end sans FastAPI."""

    def test_pipeline_complet_sans_erreur(self, df_universitaire):
        """Le pipeline complet doit tourner sans lever d'exception."""
        from skills.visualization_skill.core.eda import (
            analyze_target_variable,
            classify_columns,
            compute_correlation_matrix,
            compute_descriptive_stats,
            detect_data_patterns,
        )

        classes = classify_columns(df_universitaire)
        stats = compute_descriptive_stats(df_universitaire, col_classes=classes)
        corr, pairs = compute_correlation_matrix(df_universitaire, col_classes=classes)
        target = analyze_target_variable(df_universitaire, "statut")
        patterns = detect_data_patterns(df_universitaire, col_classes=classes)

        charts = build_eda_charts(
            df=df_universitaire,
            stats=stats,
            patterns=patterns,
            target_column="statut",
            corr_matrix=corr if not corr.empty else None,
        )

        # Assertions de base
        assert isinstance(charts, list)
        assert len(charts) > 0
        assert all("figure" in c for c in charts)
        assert all("title" in c for c in charts)
        assert all("chart_type" in c for c in charts)
        assert all("columns_involved" in c for c in charts)

        # Aucune colonne problematique dans aucun graphique
        all_cols_used = set()
        for c in charts:
            all_cols_used.update(c["columns_involved"])

        forbidden = {
            "telephone", "email", "email_Enseignants",
            "nom", "prenom", "nom_Enseignants", "prenom_Enseignants",
            "id_inscription", "id_etudiant",
            "filiere", "departement",
        }
        found_forbidden = forbidden & all_cols_used
        assert not found_forbidden, (
            f"Colonnes interdites trouvees dans les graphiques : {found_forbidden}"
        )

    def test_dataset_vide_ne_plante_pas(self):
        """Dataset vide doit retourner liste vide sans exception."""
        df_empty = pd.DataFrame({"col_a": [], "col_b": []})
        classes = classify_columns(df_empty)
        # classify_columns ne doit pas lever d'exception
        assert isinstance(classes, dict)

    def test_dataset_une_seule_colonne(self):
        """Dataset avec une seule colonne numerique."""
        df_one = pd.DataFrame({"age": np.random.normal(35, 5, 50)})
        classes = classify_columns(df_one)
        assert classes["age"] == "numeric"
        stats = compute_descriptive_stats(df_one, col_classes=classes)
        assert "age" in stats["numeric_stats"]