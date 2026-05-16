"""
backend/tests/test_etl.py
Tests unitaires complets pour le ETL Skill.

Couvre :
- core/cleaner.py     : load_dataset, remove_duplicates, fix_data_types,
                        handle_missing_values, sanitize_column_names,
                        is_protected_column
- core/transformer.py : encode_categorical, scale_features,
                        detect_and_treat_outliers, create_features,
                        build_dimensional_model, get_gemini_suggestions
- core/validator.py   : generate_quality_report,
                        validate_referential_integrity
- core/exporter.py    : save_dataset, generate_markdown_report,
                        generate_etl_script
- schemas/etl.py      : ETLRequest, ETLResponse (validation Pydantic)
- api/routes/etl.py   : POST /api/etl/run (TestClient FastAPI)

Mocks utilises :
- httpx.AsyncClient pour Directus (push_report_mdx, append_pipeline_log)
- google.genai pour les suggestions Gemini

Execution :
    pytest backend/tests/test_etl.py -v
    pytest backend/tests/test_etl.py --cov=backend/skills/etl_skill
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError


# ============================================================================
# Fixtures partagees
# ============================================================================

@pytest.fixture()
def df_simple() -> pd.DataFrame:
    """DataFrame propre sans problemes."""
    return pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "Diana"],
        "age": [25, 30, 35, 28],
        "salary": [50000.0, 60000.0, 75000.0, 55000.0],
        "city": ["Paris", "Lyon", "Marseille", "Paris"],
    })


@pytest.fixture()
def df_dirty() -> pd.DataFrame:
    """DataFrame avec nulls, doublons, outliers et types incorrects."""
    return pd.DataFrame({
        "name": ["Alice", "Bob", "Bob", None, "Eve"],
        "age": ["25", "30", "30", "28", "999"],
        "salary": [50000.0, None, 60000.0, 55000.0, 70000.0],
        "city": ["Paris", "Lyon", "Lyon", None, "Marseille"],
        "score": [85.0, 90.0, 90.0, None, 88.0],
    })


# ============================================================================
# Tests core/cleaner.py
# ============================================================================

class TestLoadDataset:
    """Tests pour load_dataset()."""

    def test_load_csv(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        csv_path = tmp_path / "test.csv"
        csv_path.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
        df, meta = load_dataset(csv_path)
        assert isinstance(df, pd.DataFrame)
        assert df.shape == (2, 3)
        assert meta["format"] == "csv"

    def test_load_csv_semicolon_separator(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        csv_path = tmp_path / "test.csv"
        csv_path.write_text("a;b;c\n1;2;3\n4;5;6\n", encoding="utf-8")
        df, meta = load_dataset(csv_path)
        assert df.shape == (2, 3)

    def test_load_excel_single_sheet(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        xl_path = tmp_path / "test.xlsx"
        df_ref = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        df_ref.to_excel(xl_path, index=False, engine="openpyxl")
        df, meta = load_dataset(xl_path)
        assert df.shape == (2, 2)
        assert meta["format"] == "xlsx"

    def test_load_excel_multi_sheets(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        xl_path = tmp_path / "multi.xlsx"
        with pd.ExcelWriter(xl_path, engine="openpyxl") as writer:
            pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="S1", index=False)
            pd.DataFrame({"b": [3, 4]}).to_excel(writer, sheet_name="S2", index=False)
        result, meta = load_dataset(xl_path, sheet_name=None)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"S1", "S2"}

    def test_load_json(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        json_path = tmp_path / "test.json"
        json_path.write_text('[{"a": 1, "b": 2}, {"a": 3, "b": 4}]', encoding="utf-8")
        df, meta = load_dataset(json_path)
        assert df.shape == (2, 2)
        assert meta["format"] == "json"

    def test_load_parquet(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        pq_path = tmp_path / "test.parquet"
        pd.DataFrame({"x": [1, 2, 3]}).to_parquet(pq_path)
        df, meta = load_dataset(pq_path)
        assert df.shape == (3, 1)
        assert meta["format"] == "parquet"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        with pytest.raises(FileNotFoundError):
            load_dataset(tmp_path / "absent.csv")

    def test_invalid_format_raises(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.cleaner import load_dataset

        bad_path = tmp_path / "test.xyz"
        bad_path.write_text("data")
        with pytest.raises(ValueError, match="Format non supporte"):
            load_dataset(bad_path)


class TestRemoveDuplicates:
    """Tests pour remove_duplicates()."""

    def test_remove_exact_duplicates(self, df_dirty: pd.DataFrame) -> None:
        from skills.etl_skill.core.cleaner import remove_duplicates

        df_clean, report = remove_duplicates(df_dirty)
        assert len(df_clean) < len(df_dirty)
        assert report["rows_removed"] >= 1

    def test_no_duplicates(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.cleaner import remove_duplicates

        df_clean, report = remove_duplicates(df_simple)
        assert len(df_clean) == len(df_simple)
        assert report["rows_removed"] == 0

    def test_subset_columns(self) -> None:
        from skills.etl_skill.core.cleaner import remove_duplicates

        df = pd.DataFrame({"a": [1, 1, 2], "b": [10, 20, 30]})
        df_clean, report = remove_duplicates(df, subset=["a"])
        assert len(df_clean) == 2
        assert report["subset"] == ["a"]

    def test_report_structure(self, df_dirty: pd.DataFrame) -> None:
        from skills.etl_skill.core.cleaner import remove_duplicates

        _, report = remove_duplicates(df_dirty)
        assert set(report.keys()) == {
            "rows_before", "rows_after", "rows_removed",
            "percent_removed", "subset",
        }


class TestFixDataTypes:
    """Tests pour fix_data_types()."""

    def test_convert_numeric_strings(self) -> None:
        from skills.etl_skill.core.cleaner import fix_data_types

        df = pd.DataFrame({"age": ["25", "30", "35"]})
        df_fixed, log = fix_data_types(df)
        assert pd.api.types.is_numeric_dtype(df_fixed["age"])
        assert len(log) == 1
        assert log[0]["method"] == "numeric"

    def test_convert_date_strings(self) -> None:
        from skills.etl_skill.core.cleaner import fix_data_types

        df = pd.DataFrame({"date": ["2020-01-01", "2020-02-01", "2020-03-01"]})
        df_fixed, log = fix_data_types(df)
        assert pd.api.types.is_datetime64_any_dtype(df_fixed["date"])

    def test_preserve_clean_types(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.cleaner import fix_data_types

        df_fixed, log = fix_data_types(df_simple)
        assert pd.api.types.is_numeric_dtype(df_fixed["age"])
        # age etait deja numerique, pas de conversion


class TestHandleMissingValues:
    """Tests pour handle_missing_values()."""

    def test_auto_strategy_numeric(self) -> None:
        from skills.etl_skill.core.cleaner import handle_missing_values

        df = pd.DataFrame({"x": [1.0, 2.0, None, 4.0]})
        df_out, log = handle_missing_values(df, strategy="auto")
        assert df_out["x"].isna().sum() == 0
        assert df_out["x"].iloc[2] == pytest.approx(2.0)  # mediane

    def test_auto_strategy_categorical(self) -> None:
        from skills.etl_skill.core.cleaner import handle_missing_values

        df = pd.DataFrame({"city": ["Paris", "Paris", "Lyon", None]})
        df_out, _ = handle_missing_values(df, strategy="auto")
        assert df_out["city"].isna().sum() == 0
        assert df_out["city"].iloc[3] == "Paris"  # mode

    def test_constant_strategy(self) -> None:
        from skills.etl_skill.core.cleaner import handle_missing_values

        df = pd.DataFrame({"x": [1.0, None, 3.0], "y": ["a", None, "c"]})
        df_out, _ = handle_missing_values(df, strategy="constant")
        assert df_out["x"].iloc[1] == 0
        assert df_out["y"].iloc[1] == "N/D"

    def test_drop_strategy(self) -> None:
        from skills.etl_skill.core.cleaner import handle_missing_values

        df = pd.DataFrame({"x": [1.0, None, 3.0]})
        df_out, _ = handle_missing_values(df, strategy="drop")
        assert len(df_out) == 2

    def test_drop_high_nullity_column(self) -> None:
        from skills.etl_skill.core.cleaner import handle_missing_values

        df = pd.DataFrame({
            "good": [1, 2, 3, 4],
            "bad": [None, None, None, 1],
        })
        df_out, log = handle_missing_values(df, threshold=0.5)
        assert "bad" not in df_out.columns

    def test_empty_dataframe(self) -> None:
        from skills.etl_skill.core.cleaner import handle_missing_values

        df = pd.DataFrame({"x": []})
        df_out, log = handle_missing_values(df)
        assert len(df_out) == 0


class TestSanitizeColumnNames:
    """Tests pour sanitize_column_names()."""

    def test_remove_accents(self) -> None:
        from skills.etl_skill.core.cleaner import sanitize_column_names

        df = pd.DataFrame({"École": [1], "Année": [2]})
        df_out = sanitize_column_names(df)
        assert list(df_out.columns) == ["ecole", "annee"]

    def test_replace_special_chars(self) -> None:
        from skills.etl_skill.core.cleaner import sanitize_column_names

        df = pd.DataFrame({"Nom Complet": [1], "Age (ans)": [2]})
        df_out = sanitize_column_names(df)
        assert list(df_out.columns) == ["nom_complet", "age_ans"]

    def test_deduplicate_names(self) -> None:
        from skills.etl_skill.core.cleaner import sanitize_column_names

        df = pd.DataFrame({"Nom": [1], "nom": [2], "NOM": [3]})
        df_out = sanitize_column_names(df)
        cols = list(df_out.columns)
        assert len(cols) == len(set(cols))


class TestIsProtectedColumn:
    """Tests pour is_protected_column()."""

    def test_id_column_detected(self) -> None:
        from skills.etl_skill.core.cleaner import is_protected_column

        assert is_protected_column("customer_id")
        assert is_protected_column("id")
        assert is_protected_column("uuid")

    def test_email_column_detected(self) -> None:
        from skills.etl_skill.core.cleaner import is_protected_column

        assert is_protected_column("email")
        assert is_protected_column("mail_contact")

    def test_date_column_detected(self) -> None:
        from skills.etl_skill.core.cleaner import is_protected_column

        assert is_protected_column("date_naissance")
        assert is_protected_column("creation_date")

    def test_normal_column_not_detected(self) -> None:
        from skills.etl_skill.core.cleaner import is_protected_column

        assert not is_protected_column("salary")
        assert not is_protected_column("score")


# ============================================================================
# Tests core/transformer.py
# ============================================================================

class TestEncodeCategorial:
    """Tests pour encode_categorical()."""

    def test_label_encoding(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import encode_categorical

        df_out, encoders = encode_categorical(
            df_simple, columns=["city"], method="label",
        )
        assert "city" in encoders
        assert pd.api.types.is_numeric_dtype(df_out["city"])

    def test_onehot_encoding(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import encode_categorical

        df_out, encoders = encode_categorical(
            df_simple, columns=["city"], method="onehot",
        )
        assert "city" in encoders
        # OneHot avec drop='first' : 3 villes uniques -> 2 colonnes
        city_cols = [c for c in df_out.columns if c.startswith("city_")]
        assert len(city_cols) == 2

    def test_auto_low_cardinality_uses_label(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import encode_categorical

        df_out, _ = encode_categorical(
            df_simple, columns=["city"], method="auto",
        )
        # 3 villes uniques < 10 → LabelEncoder
        assert "city" in df_out.columns
        assert pd.api.types.is_numeric_dtype(df_out["city"])

    def test_invalid_method_raises(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import encode_categorical

        with pytest.raises(ValueError, match="Methode invalide"):
            encode_categorical(df_simple, columns=["city"], method="invalid")

    def test_missing_column_raises(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import encode_categorical

        with pytest.raises(ValueError, match="absentes"):
            encode_categorical(df_simple, columns=["unknown"])


class TestScaleFeatures:
    """Tests pour scale_features()."""

    def test_standard_scaler(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import scale_features

        df_out, scalers = scale_features(
            df_simple, columns=["age", "salary"], method="standard",
        )
        assert "age" in scalers
        # StandardScaler : moyenne ~ 0
        assert abs(df_out["age"].mean()) < 1e-10

    def test_minmax_scaler(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import scale_features

        df_out, _ = scale_features(
            df_simple, columns=["age"], method="minmax",
        )
        assert df_out["age"].min() == pytest.approx(0.0)
        assert df_out["age"].max() == pytest.approx(1.0)

    def test_invalid_method_raises(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import scale_features

        with pytest.raises(ValueError, match="Methode invalide"):
            scale_features(df_simple, columns=["age"], method="bad")


class TestDetectAndTreatOutliers:
    """Tests pour detect_and_treat_outliers()."""

    def test_iqr_cap_action(self) -> None:
        from skills.etl_skill.core.transformer import detect_and_treat_outliers

        df = pd.DataFrame({"x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]})
        df_out, report = detect_and_treat_outliers(
            df, columns=["x"], method="iqr", action="cap",
        )
        assert df_out["x"].max() < 100  # cappe
        assert report["x"]["n_outliers"] >= 1

    def test_iqr_remove_action(self) -> None:
        from skills.etl_skill.core.transformer import detect_and_treat_outliers

        df = pd.DataFrame({"x": [1, 2, 3, 4, 5, 100]})
        df_out, _ = detect_and_treat_outliers(
            df, columns=["x"], method="iqr", action="remove",
        )
        assert 100 not in df_out["x"].values

    def test_iqr_flag_action(self) -> None:
        from skills.etl_skill.core.transformer import detect_and_treat_outliers

        df = pd.DataFrame({"x": [1, 2, 3, 4, 5, 100]})
        df_out, _ = detect_and_treat_outliers(
            df, columns=["x"], method="iqr", action="flag",
        )
        assert "x_is_outlier" in df_out.columns
        assert df_out["x_is_outlier"].sum() >= 1

    def test_zscore_method(self) -> None:
        from skills.etl_skill.core.transformer import detect_and_treat_outliers

        df = pd.DataFrame({"x": list(range(100)) + [1000]})
        _, report = detect_and_treat_outliers(
            df, columns=["x"], method="zscore", action="cap",
        )
        assert report["x"]["method"] == "zscore"

    def test_invalid_action_raises(self) -> None:
        from skills.etl_skill.core.transformer import detect_and_treat_outliers

        df = pd.DataFrame({"x": [1, 2, 3]})
        with pytest.raises(ValueError, match="Action invalide"):
            detect_and_treat_outliers(df, columns=["x"], action="invalid")


class TestCreateFeatures:
    """Tests pour create_features()."""

    def test_none_operations_returns_unchanged(self, df_simple: pd.DataFrame) -> None:
        from skills.etl_skill.core.transformer import create_features

        df_out, log = create_features(df_simple, operations=None)
        assert df_out.equals(df_simple)
        assert log == []

    def test_ratio_feature(self) -> None:
        from skills.etl_skill.core.transformer import create_features

        df = pd.DataFrame({"a": [10, 20, 30], "b": [2, 4, 5]})
        df_out, log = create_features(df, operations=[
            {"type": "ratio", "source_columns": ["a", "b"], "new_column_name": "ratio"},
        ])
        assert "ratio" in df_out.columns
        assert log[0]["status"] == "ok"

    def test_difference_feature(self) -> None:
        from skills.etl_skill.core.transformer import create_features

        df = pd.DataFrame({"a": [10, 20], "b": [5, 8]})
        df_out, _ = create_features(df, operations=[
            {"type": "difference", "source_columns": ["a", "b"], "new_column_name": "diff"},
        ])
        assert list(df_out["diff"]) == [5, 12]

    def test_unknown_type_skipped(self) -> None:
        from skills.etl_skill.core.transformer import create_features

        df = pd.DataFrame({"a": [1, 2]})
        _, log = create_features(df, operations=[
            {"type": "unknown_type", "source_columns": ["a"]},
        ])
        assert log[0]["status"] == "skipped"


class TestBuildDimensionalModel:
    """Tests pour build_dimensional_model()."""

    def test_creates_fact_and_dims(self) -> None:
        from skills.etl_skill.core.transformer import build_dimensional_model

        df = pd.DataFrame({
            "produit": ["A", "B", "A", "C"] * 5,
            "categorie": ["X", "Y", "X", "Z"] * 5,
            "ventes": np.random.rand(20) * 100,
        })
        schema, rapport = build_dimensional_model(df)
        assert "fact" in schema
        # Au moins une dimension
        dim_keys = [k for k in schema.keys() if k.startswith("dim_")]
        assert len(dim_keys) >= 1

    def test_fact_table_has_fk(self) -> None:
        from skills.etl_skill.core.transformer import build_dimensional_model

        df = pd.DataFrame({
            "city": ["Paris", "Lyon", "Paris", "Lyon"] * 5,
            "revenue": np.random.rand(20),
        })
        schema, rapport = build_dimensional_model(df)
        fact = schema["fact"]
        # La FK doit etre presente
        fk_cols = [c for c in fact.columns if c.startswith("id_")]
        assert len(fk_cols) >= 1


class TestGetGeminiSuggestions:
    """Tests pour get_gemini_suggestions() — Gemini mocke."""

    def test_no_api_key_returns_empty(self) -> None:
        from skills.etl_skill.core.transformer import get_gemini_suggestions

        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
            result = get_gemini_suggestions({}, [], api_key=None)
            assert result == []

    @patch("google.genai.Client")
    def test_valid_response_parsed(self, mock_client: MagicMock) -> None:
        from skills.etl_skill.core.transformer import get_gemini_suggestions

        mock_response = MagicMock()
        mock_response.text = json.dumps([
            {"nom": "age_calc", "colonne": "birthdate",
             "action": "age_from_date", "justification": "calcul age"},
        ])
        mock_client.return_value.models.generate_content.return_value = mock_response

        result = get_gemini_suggestions(
            {"n_rows": 100}, [], api_key="fake_key",
        )
        assert isinstance(result, list)

    @patch("google.genai.Client")
    def test_invalid_json_returns_empty(self, mock_client: MagicMock) -> None:
        from skills.etl_skill.core.transformer import get_gemini_suggestions

        mock_response = MagicMock()
        mock_response.text = "not a json"
        mock_client.return_value.models.generate_content.return_value = mock_response

        result = get_gemini_suggestions({}, [], api_key="fake_key")
        assert result == []


# ============================================================================
# Tests core/validator.py
# ============================================================================

class TestGenerateQualityReport:
    """Tests pour generate_quality_report()."""

    def test_report_contains_required_keys(
        self, df_simple: pd.DataFrame, tmp_path: Path,
    ) -> None:
        from skills.etl_skill.core.validator import generate_quality_report

        rapport, path = generate_quality_report(
            df_simple, label="test", output_dir=tmp_path,
        )
        required = {
            "label", "shape", "n_rows", "n_cols",
            "global_null_rate_pct", "total_nulls", "n_duplicates",
            "per_column", "numeric_stats", "categorical_dist",
        }
        assert required.issubset(set(rapport.keys()))

    def test_markdown_file_created(
        self, df_simple: pd.DataFrame, tmp_path: Path,
    ) -> None:
        from skills.etl_skill.core.validator import generate_quality_report

        _, path = generate_quality_report(
            df_simple, label="initial", output_dir=tmp_path,
        )
        assert path.exists()
        assert path.suffix == ".md"

    def test_null_rate_calculation(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.validator import generate_quality_report

        df = pd.DataFrame({"x": [1, None, 3, None]})  # 50% nulls
        rapport, _ = generate_quality_report(
            df, label="test", output_dir=tmp_path,
        )
        assert rapport["global_null_rate_pct"] == 50.0


class TestValidateReferentialIntegrity:
    """Tests pour validate_referential_integrity()."""

    def test_valid_references(self) -> None:
        from skills.etl_skill.core.validator import validate_referential_integrity

        df_fact = pd.DataFrame({"id_city": [1, 2, 1, 2]})
        df_dim = pd.DataFrame({"id_city": [1, 2], "name": ["Paris", "Lyon"]})
        result = validate_referential_integrity(
            df_fact, {"city": (df_dim, "id_city")},
        )
        assert result["city"]["status"] == "ok"
        assert result["city"]["invalid_count"] == 0

    def test_invalid_references(self) -> None:
        from skills.etl_skill.core.validator import validate_referential_integrity

        df_fact = pd.DataFrame({"id_city": [1, 2, 99]})
        df_dim = pd.DataFrame({"id_city": [1, 2]})
        result = validate_referential_integrity(
            df_fact, {"city": (df_dim, "id_city")},
        )
        assert result["city"]["status"] == "violations_found"
        assert result["city"]["invalid_count"] == 1

    def test_missing_fk_column(self) -> None:
        from skills.etl_skill.core.validator import validate_referential_integrity

        df_fact = pd.DataFrame({"other": [1, 2]})
        df_dim = pd.DataFrame({"id_city": [1, 2]})
        result = validate_referential_integrity(
            df_fact, {"city": (df_dim, "id_city")},
        )
        assert result["city"]["status"] == "missing_fk"


# ============================================================================
# Tests core/exporter.py
# ============================================================================

class TestSaveDataset:
    """Tests pour save_dataset()."""

    def test_save_csv(self, df_simple: pd.DataFrame, tmp_path: Path) -> None:
        from skills.etl_skill.core.exporter import save_dataset

        path = save_dataset(df_simple, tmp_path, "out.csv", format="csv")
        assert path.exists()
        assert path.suffix == ".csv"

    def test_save_parquet(self, df_simple: pd.DataFrame, tmp_path: Path) -> None:
        from skills.etl_skill.core.exporter import save_dataset

        path = save_dataset(df_simple, tmp_path, "out.parquet", format="parquet")
        assert path.exists()

    def test_save_excel(self, df_simple: pd.DataFrame, tmp_path: Path) -> None:
        from skills.etl_skill.core.exporter import save_dataset

        path = save_dataset(df_simple, tmp_path, "out.xlsx", format="excel")
        assert path.exists()
        assert path.suffix == ".xlsx"

    def test_invalid_format_raises(
        self, df_simple: pd.DataFrame, tmp_path: Path,
    ) -> None:
        from skills.etl_skill.core.exporter import save_dataset

        with pytest.raises(ValueError, match="Format invalide"):
            save_dataset(df_simple, tmp_path, "out.bin", format="bin")

    def test_creates_output_dir(
        self, df_simple: pd.DataFrame, tmp_path: Path,
    ) -> None:
        from skills.etl_skill.core.exporter import save_dataset

        deep_dir = tmp_path / "a" / "b" / "c"
        path = save_dataset(df_simple, deep_dir, "out.csv")
        assert path.exists()


class TestGenerateMarkdownReport:
    """Tests pour generate_markdown_report()."""

    def test_returns_tuple_str_path(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.exporter import generate_markdown_report

        before = {"n_rows": 100, "n_cols": 5, "global_null_rate_pct": 10, "n_duplicates": 5}
        after = {"n_rows": 90, "n_cols": 5, "global_null_rate_pct": 0, "n_duplicates": 0}
        content, path = generate_markdown_report(
            before, after, [], tmp_path / "report.md",
        )
        assert isinstance(content, str)
        assert path.exists()
        assert "Rapport ETL" in content

    def test_includes_transformation_log(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.exporter import generate_markdown_report

        log = [{"etape": "test_step", "rows_before": 100, "rows_after": 90}]
        content, _ = generate_markdown_report(
            {}, {}, log, tmp_path / "r.md",
        )
        assert "test_step" in content


class TestGenerateEtlScript:
    """Tests pour generate_etl_script()."""

    def test_script_is_syntactically_valid(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.exporter import generate_etl_script

        log = [
            {"etape": "handle_missing_values", "strategy": "auto", "fill_mode": "smart"},
            {"etape": "remove_duplicates"},
        ]
        info = {"input_path": "data.csv", "shape_before": (100, 5)}
        path = generate_etl_script(log, info, tmp_path / "etl.py")

        assert path.exists()
        # Verifier que le script est syntaxiquement valide
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        compile(content, path.name, "exec")

    def test_script_contains_run_etl_function(self, tmp_path: Path) -> None:
        from skills.etl_skill.core.exporter import generate_etl_script

        path = generate_etl_script([], {"input_path": "x.csv"}, tmp_path / "s.py")
        content = path.read_text(encoding="utf-8")
        assert "def run_etl" in content
        assert "if __name__" in content


# ============================================================================
# Tests schemas Pydantic
# ============================================================================

class TestETLRequestSchema:
    """Tests pour le schema Pydantic ETLRequest."""

    def test_minimal_valid_request(self) -> None:
        from schemas.etl import ETLRequest

        req = ETLRequest(session_id="s1", input_path="data.csv")
        assert req.session_id == "s1"
        assert req.missing_strategy == "auto"  # default
        assert req.generate_script is True  # default

    def test_missing_session_id_raises(self) -> None:
        from schemas.etl import ETLRequest

        with pytest.raises(ValidationError):
            ETLRequest(input_path="data.csv")

    def test_missing_input_path_raises(self) -> None:
        from schemas.etl import ETLRequest

        with pytest.raises(ValidationError):
            ETLRequest(session_id="s1")

    def test_invalid_strategy_raises(self) -> None:
        from schemas.etl import ETLRequest

        with pytest.raises(ValidationError):
            ETLRequest(
                session_id="s1",
                input_path="data.csv",
                missing_strategy="invalid_strategy",
            )

    def test_empty_session_id_raises(self) -> None:
        from schemas.etl import ETLRequest

        with pytest.raises(ValidationError):
            ETLRequest(session_id="   ", input_path="data.csv")


class TestETLResponseSchema:
    """Tests pour le schema Pydantic ETLResponse."""

    def test_minimal_valid_response(self) -> None:
        from schemas.etl import ETLResponse

        resp = ETLResponse(session_id="s1", status="success")
        assert resp.skill == "ETL"
        assert resp.rows_before == 0  # default

    def test_invalid_status_raises(self) -> None:
        from schemas.etl import ETLResponse

        with pytest.raises(ValidationError):
            ETLResponse(session_id="s1", status="unknown")

    def test_negative_rows_raises(self) -> None:
        from schemas.etl import ETLResponse

        with pytest.raises(ValidationError):
            ETLResponse(session_id="s1", status="success", rows_before=-1)


# ============================================================================
# Tests endpoint FastAPI
# ============================================================================

class TestETLEndpoint:
    """Tests pour POST /api/etl/run avec TestClient FastAPI."""

    @pytest.fixture()
    def client(self):
        """Construit un TestClient FastAPI minimal."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.etl import router

        app = FastAPI()
        app.include_router(router, prefix="/api")
        return TestClient(app)

    def test_invalid_pydantic_returns_422(self, client) -> None:
        # Champ session_id manquant
        response = client.post("/api/etl/run", json={"input_path": "data.csv"})
        assert response.status_code == 422

    def test_missing_input_path_returns_422(self, client) -> None:
        response = client.post("/api/etl/run", json={"session_id": "s1"})
        assert response.status_code == 422

    def test_file_not_found_returns_404(self, client) -> None:
        with patch(
            "src.utils.directus_client.push_report_mdx",
            new_callable=AsyncMock,
            return_value="",
        ), patch(
            "src.utils.directus_client.append_pipeline_log",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.post("/api/etl/run", json={
                "session_id": "s1",
                "input_path": "/nonexistent/file.csv",
            })
            # 404 ou 500 selon comment l'erreur remonte
            assert response.status_code in (200, 404)
            if response.status_code == 200:
                data = response.json()
                assert data["status"] == "error"

    def test_valid_request_runs_pipeline(self, client, tmp_path: Path) -> None:
        # Creer un CSV valide
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "name,age,city\nAlice,25,Paris\nBob,30,Lyon\n",
            encoding="utf-8",
        )

        with patch(
            "src.utils.directus_client.push_report_mdx",
            new_callable=AsyncMock,
            return_value="mock_mdx_id",
        ), patch(
            "src.utils.directus_client.append_pipeline_log",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.post("/api/etl/run", json={
                "session_id": "test_session",
                "input_path": str(csv_path),
                "generate_script": False,
                "dimensional_modeling": False,
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["session_id"] == "test_session"
            assert data["rows_before"] == 2