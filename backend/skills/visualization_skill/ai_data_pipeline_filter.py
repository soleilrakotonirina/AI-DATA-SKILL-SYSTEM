"""
Open WebUI Filter — AI Data Pipeline (ETL + Visualization)
============================================================
Intercepte les messages, détecte les fichiers uploadés, et injecte
des instructions directes à Mistral pour appeler les MCP tools.

INSTALLATION :
    Open WebUI → Admin Panel → Functions → + Add Function
    → Coller ce code → Enable → Save

    Puis activer ce Filter sur le modèle Assistant-AI-DA-Pipeline :
    Workspace → Models → Assistant-AI-DA-Pipeline
    → Filters → ☑ AI Data Pipeline Filter

FONCTIONNEMENT :
    1. Utilisateur uploade un fichier + tape "nettoie" ou "dashboard"
    2. Le Filter détecte le fichier et le sauvegarde dans data/uploads/
    3. Le Filter injecte une instruction à Mistral :
       "APPELER IMMÉDIATEMENT : etl_auto()" ou "APPELER IMMÉDIATEMENT : viz_auto()"
    4. Mistral appelle le tool MCP directement sans hésiter
    5. Le résultat s'affiche dans le chat
"""

import json
import re
import shutil
from pathlib import Path
from pydantic import BaseModel, Field


class Filter:
    # file_handler = True : dit à Open WebUI de ne PAS faire de RAG sur le fichier
    # C'est CRITIQUE — sans ça, Open WebUI traite le fichier comme contexte
    # et Mistral répond directement sans appeler les tools
    file_handler = True

    class Valves(BaseModel):
        data_uploads_dir: str = Field(
            default="/home/sun/Formations/AI_DATA_SKILL_SYSTEM/backend/data/uploads",
            description="Dossier partagé entre Open WebUI et le serveur MCP. "
                        "DOIT être le même dossier que UPLOAD_DIR dans .env",
        )
        default_action: str = Field(
            default="viz",
            description="Action par défaut si aucun mot-clé détecté : 'etl' ou 'viz'",
        )
        debug: bool = Field(
            default=False,
            description="Mode debug : affiche les informations de détection",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ─────────────────────────────────────────────────────────────────────────
    # Inlet — intercepte le message AVANT Mistral
    # ─────────────────────────────────────────────────────────────────────────

    async def inlet(self, body: dict, __user__: dict | None = None) -> dict:
        messages   = body.get("messages", [])
        files_meta = body.get("files", [])

        if not messages:
            return body

        last_msg = messages[-1]
        content  = last_msg.get("content", "")
        user_text = self._text(content)

        dbg: dict = {}

        # Collecter les fichiers depuis toutes les clés Open WebUI
        metadata_files = []
        if isinstance(body.get("metadata"), dict):
            metadata_files = body["metadata"].get("files") or []
        all_files = files_meta or metadata_files

        # ── Fichier uploadé détecté ───────────────────────────────────────────
        if all_files:
            # VIDER les fichiers pour stopper le pipeline RAG d'Open WebUI
            body["files"] = []
            if isinstance(body.get("metadata"), dict):
                body["metadata"]["files"] = []

            detected = await self._detect_file(all_files, dbg)
            if detected:
                fname, raw_content, raw_path = detected

                # Sauvegarder le fichier
                saved_path = self._save_file(raw_content, fname, raw_path, dbg)

                # Détecter l'action demandée
                action = self._detect_action(user_text)

                # Générer l'instruction à injecter
                instruction = self._build_instruction(
                    saved_path=saved_path,
                    filename=fname,
                    action=action,
                    user_text=user_text,
                )

                if self.valves.debug:
                    instruction = self._debug_prefix(dbg) + "\n\n" + instruction

                last_msg["content"] = instruction + "\n\n" + user_text
                return body

        # ── Contenu CSV dans le message (sans upload) ────────────────────────
        if isinstance(content, str) and self._looks_tabular(content):
            saved = self._save_text(content, "uploaded_data.csv")
            action = self._detect_action(user_text)
            instruction = self._build_instruction(
                saved_path=saved,
                filename="uploaded_data.csv",
                action=action,
                user_text=user_text,
            )
            last_msg["content"] = instruction + "\n\n" + user_text

        return body

    async def outlet(self, body: dict, __user__: dict | None = None) -> dict:
        """
        Intercepte la réponse de Mistral.
        Ajoute les images PNG inline après la réponse — bypass le reformatage Mistral.
        """
        messages = body.get("messages", [])
        if not messages:
            return body

        # Chercher la dernière réponse de l'assistant
        last_assistant = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                last_assistant = msg
                break

        if not last_assistant:
            return body

        content = last_assistant.get("content", "")
        if not isinstance(content, str):
            return body

        # Vérifier si la réponse mentionne une visualisation
        viz_keywords = ["dashboard", "graphique", "visualis", "viz_auto", "inscription",
                        "kpi", "chart", "eda", "donnees_universitaires"]
        has_viz = any(kw.lower() in content.lower() for kw in viz_keywords)

        if not has_viz:
            return body

        # Chercher les PNG du dernier dataset visualisé
        try:
            backend = Path(self.valves.data_uploads_dir).parent.parent
            viz_dir = backend / "outputs" / "viz"

            if not viz_dir.exists():
                return body

            # Trouver le dernier dossier viz avec des PNG
            dataset_name = ""
            png_files_found = []

            for d in sorted(viz_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if not d.is_dir():
                    continue
                charts_dir = d / "charts"
                if charts_dir.exists():
                    pngs = sorted(charts_dir.glob("*.png"))
                    if pngs:
                        dataset_name = d.name
                        png_files_found = pngs
                        break

            if not png_files_found:
                return body

            # Construire les images markdown
            file_server = f"http://localhost:8090"
            img_lines = []
            for png in png_files_found:
                title = png.stem.replace("_", " ").title()
                url   = f"{file_server}/files/viz/{dataset_name}/charts/{png.name}"
                img_lines.append(f"![{title}]({url})")

            dashboard_url = f"{file_server}/files/viz/{dataset_name}/dashboard.html"

            last_assistant["content"] = (
                content.rstrip()
                + f"\n\n---\n"
                + "\n".join(img_lines)
                + f"\n\n[➡ Dashboard interactif]({dashboard_url})"
            )

        except Exception as exc:
            if self.valves.debug:
                last_assistant["content"] = content + f"\n\n[outlet error: {exc}]"

        return body

    # ─────────────────────────────────────────────────────────────────────────
    # Détection du fichier
    # ─────────────────────────────────────────────────────────────────────────

    async def _detect_file(
        self, files_meta: list, dbg: dict
    ) -> tuple[str, str, str | None] | None:
        """Retourne (filename, content, raw_path) ou None."""
        SUPPORTED = {".csv", ".xlsx", ".xls", ".xlsm", ".json", ".parquet"}

        for i, f in enumerate(files_meta):
            if not isinstance(f, dict):
                continue

            fc = f.get("file", {}) or {}

            # Récupérer le nom du fichier
            fname = (
                fc.get("filename", "")
                or fc.get("name", "")
                or (fc.get("meta") or {}).get("name", "")
                or f.get("filename", "")
                or f.get("name", "")
                or ""
            )
            file_id   = fc.get("id", "") or f.get("id", "") or ""
            ext = Path(fname).suffix.lower() if fname else ""

            if self.valves.debug:
                dbg[f"file_{i}"] = {"fname": fname, "ext": ext, "file_id": file_id}

            if ext not in SUPPORTED:
                continue

            raw_content   = ""
            raw_file_path = None

            # Couche A : base de données Open WebUI (async)
            if file_id:
                db = await self._read_owui_db(file_id, dbg)
                if db:
                    raw_content, raw_file_path = db

            # Couche B : contenu dans body["files"]
            if not raw_content:
                raw_content = (
                    (fc.get("data") or {}).get("content", "")
                    or fc.get("content", "")
                    or fc.get("text", "")
                    or f.get("content", "")
                    or ""
                )

            if self.valves.debug:
                dbg["detected"] = {
                    "fname": fname,
                    "content_len": len(raw_content),
                    "raw_path": raw_file_path,
                }

            return fname, raw_content, raw_file_path

        return None

    async def _read_owui_db(
        self, file_id: str, dbg: dict
    ) -> tuple[str, str | None] | None:
        """Lit le fichier depuis la base interne Open WebUI."""
        try:
            from open_webui.models.files import Files  # type: ignore
            fobj = await Files.get_file_by_id(file_id)
            if not fobj:
                return None
            text_content  = (fobj.data or {}).get("content", "") or ""
            raw_file_path = fobj.path or None
            return text_content, raw_file_path
        except Exception as exc:
            if self.valves.debug:
                dbg["db_error"] = str(exc)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Sauvegarde du fichier
    # ─────────────────────────────────────────────────────────────────────────

    def _save_file(
        self,
        content: str,
        filename: str,
        raw_path: str | None,
        dbg: dict,
    ) -> str:
        """Sauvegarde le fichier dans data/uploads/ et retourne son chemin."""
        ext = Path(filename).suffix.lower()
        is_binary = ext in {".xlsx", ".xls", ".xlsm", ".parquet"}

        # Cas 1 : fichier binaire avec chemin connu → copier directement
        if raw_path and Path(raw_path).exists() and is_binary:
            saved = self._copy_binary(raw_path, filename, dbg)
            if saved:
                return saved

        # Cas 2 : lire le fichier texte depuis le chemin brut
        if raw_path and Path(raw_path).exists() and not is_binary and not content:
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    content = Path(raw_path).read_text(encoding=enc, errors="replace")
                    if content:
                        break
                except Exception:
                    continue

        # Cas 3 : sauvegarder le contenu texte
        if content:
            return self._save_text(content, filename)

        # Cas 4 : rien disponible → utiliser le chemin brut ou le nom
        if raw_path and Path(raw_path).exists():
            return raw_path

        return filename

    def _save_text(self, content: str, filename: str) -> str:
        """
        Sauvegarde du contenu texte dans uploads/.
        Vérifie que le contenu est un CSV valide avant d'écrire.
        """
        try:
            # Vérifier que c'est un CSV valide (pas du HTML, Markdown ou texte corrompu)
            stripped = content.strip()

            # Rejeter si c'est du HTML, Markdown ou réponse LLM
            if stripped.startswith(("<", "#", "✅", "📊", "##", "-", "*")):
                if self.valves.debug:
                    pass
                return ""

            # Compter les colonnes de la première ligne
            lines = stripped.splitlines()
            if not lines:
                return ""

            first_line = lines[0]
            n_cols = first_line.count(",") + 1

            # Rejeter si moins de 3 colonnes — probablement corrompu
            if n_cols < 3:
                if self.valves.debug:
                    pass
                return ""

            upload_dir = Path(self.valves.data_uploads_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            fname = Path(filename).name or "uploaded_data.csv"

            # Convertir Excel/Parquet → CSV si nécessaire
            if Path(fname).suffix.lower() in {".xlsx", ".xls", ".xlsm", ".parquet"}:
                fname = Path(fname).stem + ".csv"

            content_clean = self._md_to_csv(stripped)
            target = upload_dir / fname
            target.write_text(content_clean, encoding="utf-8")
            return str(target)

        except Exception:
            return ""

    def _copy_binary(self, raw_path: str, filename: str, dbg: dict) -> str | None:
        """Copie un fichier binaire dans uploads/."""
        try:
            upload_dir = Path(self.valves.data_uploads_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            fname  = Path(filename).name or Path(raw_path).name
            target = upload_dir / fname
            shutil.copy2(raw_path, target)
            return str(target)
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Détection de l'action
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_action(self, text: str) -> str:
        """Détermine l'action : 'etl', 'viz', ou 'etl_then_viz'."""
        t = text.lower()

        etl_kw = [
            "nettoie", "nettoy", "prépare", "preparer", "transformer",
            "etl", "doublons", "valeurs manquantes", "outliers",
            "encodage", "normalisation", "star schema", "clean",
        ]
        viz_kw = [
            "dashboard", "graphique", "visualis", "eda", "analys",
            "chart", "distribution", "corrélation", "histogramme",
            "boxplot", "heatmap", "kpi", "explore",
        ]
        both_kw = [
            "nettoie et visualise", "nettoyer et visualiser",
            "prépare et analyse", "pipeline complet",
            "etl puis", "puis dashboard",
        ]

        for kw in both_kw:
            if kw in t:
                return "etl_then_viz"

        has_etl = any(kw in t for kw in etl_kw)
        has_viz = any(kw in t for kw in viz_kw)

        if has_etl and has_viz:
            return "etl_then_viz"
        if has_etl:
            return "etl"
        if has_viz:
            return "viz"

        return self.valves.default_action

    # ─────────────────────────────────────────────────────────────────────────
    # Construction de l'instruction pour Mistral
    # ─────────────────────────────────────────────────────────────────────────

    def _build_instruction(
        self,
        saved_path: str,
        filename: str,
        action: str,
        user_text: str,
    ) -> str:
        """
        Génère l'instruction injectée en tête du message.
        Mistral la lit et appelle le tool immédiatement.
        """
        if action == "etl":
            return (
                f"[INSTRUCTION SYSTÈME — NE PAS AFFICHER À L'UTILISATEUR]\n"
                f"Fichier '{filename}' sauvegardé : {saved_path}\n"
                f"APPELER IMMÉDIATEMENT : etl_auto()\n"
                f"Ne pas demander de confirmation. Ne pas écrire de code.\n"
                f"[FIN INSTRUCTION]"
            )

        elif action == "viz":
            return (
                f"[INSTRUCTION SYSTÈME — NE PAS AFFICHER À L'UTILISATEUR]\n"
                f"Fichier '{filename}' sauvegardé : {saved_path}\n"
                f"APPELER IMMÉDIATEMENT : viz_auto()\n"
                f"Ne pas demander de confirmation. Ne pas écrire de code.\n"
                f"[FIN INSTRUCTION]"
            )

        elif action == "etl_then_viz":
            return (
                f"[INSTRUCTION SYSTÈME — NE PAS AFFICHER À L'UTILISATEUR]\n"
                f"Fichier '{filename}' sauvegardé : {saved_path}\n"
                f"APPELER DANS L'ORDRE :\n"
                f"1. etl_auto() — attendre le résultat\n"
                f"2. viz_auto() — sur le fichier nettoyé\n"
                f"Ne pas demander de confirmation. Ne pas écrire de code.\n"
                f"[FIN INSTRUCTION]"
            )

        return ""

    # ─────────────────────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────────────────────

    def _text(self, content) -> str:
        if isinstance(content, list):
            return " ".join(
                p.get("text", "") for p in content if p.get("type") == "text"
            )
        return str(content or "")

    def _looks_tabular(self, text: str) -> bool:
        s = text.strip()
        if s.startswith(("{", "[")):
            return True
        lines = s.split("\n")
        return len(lines) >= 3 and sum(1 for l in lines[:5] if "," in l) >= 2

    def _md_to_csv(self, text: str) -> str:
        """Convertit un tableau Markdown en CSV si détecté."""
        lines = text.strip().split("\n")
        if not lines or not lines[0].strip().startswith("|"):
            return text
        csv_lines = []
        for line in lines:
            line = line.strip()
            if re.match(r"^\|[-| ]+\|$", line):
                continue
            if line.startswith("|") and line.endswith("|"):
                cells = [c.strip() for c in line[1:-1].split("|")]
                csv_lines.append(",".join(f'"{c}"' for c in cells))
        return "\n".join(csv_lines) if csv_lines else text

    def _debug_prefix(self, dbg: dict) -> str:
        return (
            "[FILTER_DEBUG — NE PAS AFFICHER]\n"
            + json.dumps(dbg, ensure_ascii=False, indent=2)
            + "\n[/FILTER_DEBUG]"
        )